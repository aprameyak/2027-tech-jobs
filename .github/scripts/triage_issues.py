#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from scope_rules import is_out_of_scope_title, is_in_scope_listing_title
from claude_board_prompts import build_triage_prompt

CLAUDE_MODEL = os.environ.get('GROQ_MODEL', 'openai/gpt-oss-20b')
LLM_API_URL = os.environ.get(
    'LLM_API_URL', 'https://api.groq.com/openai/v1/chat/completions'
)
REPO = os.environ.get('GITHUB_REPOSITORY', '')
TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('REPO_PAT') or ''
API = 'https://api.github.com'

STRIP_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id',
    'source', 'src', 'ref', 'referer', 'lever-source', 'lever-origin', 'gh_src',
}


def gh_headers():
    return {
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def _get_llm_api_key():
    return (
        os.environ.get('GROQ_API_KEY')
        or os.environ.get('ANTHROPIC_API_KEY')
        or ''
    ).strip() or None


def _get_client():
    return _get_llm_api_key()


def _llm_complete(prompt, max_tokens):
    api_key = _get_llm_api_key()
    if not api_key:
        return None
    resp = requests.post(
        LLM_API_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': '2027-tech-jobs/1.0',
        },
        json={
            'model': CLAUDE_MODEL,
            'temperature': 0,
            'max_tokens': max_tokens,
            'messages': [
                {
                    'role': 'system',
                    'content': 'Respond with JSON only. No markdown fences.',
                },
                {'role': 'user', 'content': prompt},
            ],
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f'LLM HTTP {resp.status_code}: {resp.text[:300]}')
    msg = resp.json()['choices'][0]['message']
    text = (msg.get('content') or '').strip()
    if not text:
        raise RuntimeError('LLM empty content')
    return text


def _is_listing_issue(issue):
    labels = {lbl.get('name', '').lower() for lbl in (issue.get('labels') or [])}
    if 'new listing' in labels or 'approved' in labels:
        return True
    body = issue.get('body') or ''
    return '### Company Name' in body and '### Direct Application Link' in body


def list_open_listing_issues():
    issues = []
    page = 1
    while True:
        resp = requests.get(
            f'{API}/repos/{REPO}/issues',
            headers=gh_headers(),
            params={'state': 'open', 'per_page': 50, 'page': page},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f'GitHub list error {resp.status_code}: {resp.text[:200]}')
            break
        batch = resp.json()
        if not batch:
            break
        for issue in batch:
            if 'pull_request' in issue:
                continue
            if _is_listing_issue(issue):
                issues.append(issue)
        page += 1
    return issues


def parse_issue_fields(body):
    fields = {}
    for section in re.split(r'^### ', body or '', flags=re.M):
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        key = lines[0].strip()
        value = '\n'.join(lines[1:]).strip()
        if value == '_No response_':
            value = ''
        fields[key] = value
    return fields


def normalize_url(url):
    if not url:
        return ''
    try:
        p = urlparse(url.strip())
        params = {}
        for k, v in parse_qs(p.query, keep_blank_values=True).items():
            kl = k.lower()
            if kl in STRIP_PARAMS:
                continue
            cleaned = [x for x in v if x not in ('', 'gh_src=', 'gh_src')]
            if kl == 't' and (not cleaned or all(str(x).startswith('gh_src') for x in cleaned)):
                continue
            if not cleaned and kl != 'gh_jid':
                continue
            params[k] = cleaned if cleaned else v
        if any(h in p.netloc.lower() for h in (
            'greenhouse', 'lever.co', 'ashbyhq', 'myworkdayjobs', 'workdaysite',
            'oraclecloud', 'smartrecruiters', 'icims', 'applytojob',
        )):
            params['utm_source'] = ['aprameyak']
        return urlunparse(p._replace(
            scheme=p.scheme.lower() or 'https',
            netloc=p.netloc.lower(),
            query=urlencode(sorted(params.items()), doseq=True),
            fragment='',
        ))
    except Exception:
        return url


def existing_urls():
    listings = json.loads(Path('listings.json').read_text())
    out = set()
    for e in listings:
        u = (e.get('url') or '').split('?')[0].rstrip('/').lower()
        out.add(u)
    return out


def claude_decide_batch(items):
    client = _get_client()
    if not client or not items:
        return {}

    lines = []
    for i, it in enumerate(items):
        fields = it['fields']
        lines.append(
            f'{i + 1}. title={it["issue"].get("title","")[:120]} | '
            f'company={fields.get("Company Name","")[:60]} | '
            f'role={fields.get("Role / Job Title","")[:80]} | '
            f'type={fields.get("Listing Type","")} | '
            f'loc={fields.get("Location","")[:60]}'
        )
    n = len(items)
    prompt = build_triage_prompt(lines, n)
    text = _llm_complete(prompt, max(min(400 * n + 800, 8000), 1200))
    if not text:
        raise RuntimeError('LLM unavailable')
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    start, end = text.find('['), text.rfind(']')
    if start >= 0 and end > start:
        text = text[start:end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, list) or len(parsed) != n:
        raise ValueError(f'expected {n} decisions, got {type(parsed).__name__}')
    return {items[i]['issue']['number']: parsed[i] for i in range(n)}


def comment(issue_number, body):
    requests.post(
        f'{API}/repos/{REPO}/issues/{issue_number}/comments',
        headers=gh_headers(),
        json={'body': body},
        timeout=30,
    )


def close_issue(issue_number):
    requests.patch(
        f'{API}/repos/{REPO}/issues/{issue_number}',
        headers=gh_headers(),
        json={'state': 'closed'},
        timeout=30,
    )


def add_via_script(decision, url):
    body = f'''### Company Name
{decision.get("company","").strip()}

### Role / Job Title
{decision.get("role","").strip()}

### Listing Type
{decision.get("type","Internship")}

### Season / Term
{decision.get("season","Summer 2027")}

### Location
{decision.get("location","").strip()}

### Visa Sponsorship?
{decision.get("sponsorship","Unknown")}

### U.S. Citizenship Required?
{decision.get("citizenship","Unknown")}

### Education Level
{decision.get("education","Undergrad")}

### Direct Application Link
{url}

### Application Deadline (Optional)
_No response_

### Additional Notes (Optional)
Auto-triaged.

### Checklist
- [x] The role is in the United States, Canada, or is Remote (North America).
- [x] The application link is publicly accessible (no login required to view the posting).
- [x] I checked that this listing does not already exist in the repository.
- [x] The information I provided is accurate to the best of my knowledge.'''
    env = os.environ.copy()
    env['ISSUE_BODY'] = body
    result = subprocess.run(
        ['python3', '.github/scripts/add_listing.py'],
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr[-500:])
        return False
    return 'Successfully' in (result.stdout or '')


def main():
    if not TOKEN or not REPO:
        print('GITHUB_TOKEN/REPO_PAT and GITHUB_REPOSITORY required')
        sys.exit(1)
    if not _get_llm_api_key():
        print('GROQ_API_KEY or ANTHROPIC_API_KEY required')
        sys.exit(1)

    issues = list_open_listing_issues()
    print(f'Open listing issues: {len(issues)}')
    known = existing_urls()
    added = rejected = skipped = 0

    needs_claude = []
    for issue in issues:
        number = issue['number']
        fields = parse_issue_fields(issue.get('body') or '')
        url = normalize_url(fields.get('Direct Application Link', ''))
        role = fields.get('Role / Job Title', '') or issue.get('title', '')
        print(f'\n#{number}: {issue.get("title")}')

        if url and url.split('?')[0].rstrip('/').lower() in known:
            comment(number, 'Duplicate of an existing listing — closing.')
            close_issue(number)
            skipped += 1
            continue

        if is_out_of_scope_title(role):
            comment(number, 'Out of scope for this board — closing.')
            close_issue(number)
            rejected += 1
            print('  local reject (out of scope)')
            continue

        listing_type = fields.get('Listing Type', '')
        season = fields.get('Season / Term', '')
        if 'New Grad' in listing_type or '2027 (New Grad' in season:
            table = 'newgrad'
        elif season == 'Summer 2027':
            table = 'summer'
        else:
            table = 'offcycle'
        if role and not is_in_scope_listing_title(role, table=table):
            comment(
                number,
                'Out of scope (not SWE / CS / information science / information systems '
                'adjacent campus role) — closing.',
            )
            close_issue(number)
            rejected += 1
            print('  local reject (not CS/IS-adjacent)')
            continue

        needs_claude.append({'issue': issue, 'fields': fields, 'url': url})

    decisions = {}
    if needs_claude:
        print(f'\n[Claude] Batch-triaging {len(needs_claude)} issue(s) in one call...')
        try:
            decisions = claude_decide_batch(needs_claude)
        except Exception as e:
            print(f'  Claude batch error: {e}')
            for it in needs_claude:
                skipped += 1
            print(f'\nDone. added={added} rejected={rejected} skipped={skipped}')
            return

    for it in needs_claude:
        issue = it['issue']
        fields = it['fields']
        url = it['url']
        number = issue['number']
        decision = decisions.get(number) or {}
        if not isinstance(decision, dict):
            skipped += 1
            continue

        action = (decision.get('action') or 'skip').lower()
        reason = decision.get('reason') or ''
        print(f'#{number} decision={action} ({reason})')

        if action == 'reject':
            comment(number, f'Out of scope / not a fit for this board — closing.\n\n{reason}')
            close_issue(number)
            rejected += 1
            continue

        if action != 'add':
            skipped += 1
            continue

        if not url:
            url = normalize_url(decision.get('url', ''))
        if not url:
            comment(number, 'Needs a direct application URL before it can be added.')
            skipped += 1
            continue

        for key, field in (
            ('company', 'Company Name'),
            ('role', 'Role / Job Title'),
            ('location', 'Location'),
            ('type', 'Listing Type'),
            ('season', 'Season / Term'),
            ('education', 'Education Level'),
            ('sponsorship', 'Visa Sponsorship?'),
            ('citizenship', 'U.S. Citizenship Required?'),
        ):
            if fields.get(field):
                decision[key] = fields[field]

        if is_out_of_scope_title(decision.get('role') or ''):
            comment(number, 'Out of scope for this board — closing.')
            close_issue(number)
            rejected += 1
            continue

        if add_via_script(decision, url):
            subprocess.run(['python3', '.github/scripts/rebuild_readme.py'], check=False)
            subprocess.run(
                ['git', 'add', 'listings.json', 'SUMMER.md', 'OFFCYCLE.md', 'NEWGRAD.md', 'README.md'],
                check=False,
            )
            msg = f"add {decision.get('company','')} — {decision.get('role','')}"[:90]
            subprocess.run(['git', 'commit', '-m', msg], check=False)
            comment(number, 'Added to the repo automatically. Thanks for contributing!')
            close_issue(number)
            known.add(url.split('?')[0].rstrip('/').lower())
            added += 1
        else:
            comment(number, 'Approved, but auto-add failed — leaving open for manual review.')
            skipped += 1

    print(f'\nDone. added={added} rejected={rejected} skipped={skipped}')


if __name__ == '__main__':
    main()
