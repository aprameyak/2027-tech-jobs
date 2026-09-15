#!/usr/bin/env python3
\
\
\
\
\
   

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import anthropic
import requests

CLAUDE_MODEL = 'claude-haiku-4-5-20251001'
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

def _is_listing_issue(issue: dict) -> bool:
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
            params={
                'state': 'open',
                'per_page': 50,
                'page': page,
            },
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

def parse_issue_fields(body: str) -> dict:
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

def normalize_url(url: str) -> str:
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

def claude_decide(issue: dict, fields: dict) -> dict:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return {'action': 'skip', 'reason': 'no API key'}

    prompt = (
        'You triage GitHub issues for a US/Canada CS internship + new-grad job board.\n'
        'Return JSON only: {"action":"add"|"reject"|"skip","reason":"short",'
        '"company":"","role":"","type":"Internship"|"New Grad (Full-Time)",'
        '"season":"","location":"","education":"Undergrad"|"Masters"|"PhD",'
        '"citizenship":"Unknown"|"Yes — U.S. citizenship required",'
        '"sponsorship":"Unknown"|"No — sponsorship not offered"}\n'
        'Rules:\n'
        '- add: SWE/data/ML/quant/cyber/DevOps/platform/tech-PM campus roles, US/Canada\n'
        '- reject: marketing/HR/people/sales, NetSuite or risk consulting, generic BA, '
        'research associate (non-CS), systems eng without software, hardware/firmware/'
        'manufacturing, senior, international-only\n'
        '- skip: missing URL, unclear timing, needs human judgment\n'
        f'Title: {issue.get("title","")}\n'
        f'Fields: {json.dumps(fields)[:2500]}\n'
    )
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        messages=[{'role': 'user', 'content': prompt}],
    )
    text = msg.content[0].text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)

def comment(issue_number: int, body: str):
    requests.post(
        f'{API}/repos/{REPO}/issues/{issue_number}/comments',
        headers=gh_headers(),
        json={'body': body},
        timeout=30,
    )

def close_issue(issue_number: int):
    requests.patch(
        f'{API}/repos/{REPO}/issues/{issue_number}',
        headers=gh_headers(),
        json={'state': 'closed'},
        timeout=30,
    )

def add_via_script(decision: dict, url: str) -> bool:
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
Auto-triaged by Claude.

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
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY required')
        sys.exit(1)

    issues = list_open_listing_issues()
    print(f'Open listing issues: {len(issues)}')
    known = existing_urls()
    added = rejected = skipped = 0

    for issue in issues:
        number = issue['number']
        fields = parse_issue_fields(issue.get('body') or '')
        url = normalize_url(fields.get('Direct Application Link', ''))
        print(f'\n#{number}: {issue.get("title")}')

        if url and url.split('?')[0].rstrip('/').lower() in known:
            comment(number, 'Duplicate of an existing listing — closing.')
            close_issue(number)
            skipped += 1
            continue

        try:
            decision = claude_decide(issue, fields)
        except Exception as e:
            print(f'  Claude error: {e}')
            skipped += 1
            continue

        action = (decision.get('action') or 'skip').lower()
        reason = decision.get('reason') or ''
        print(f'  decision={action} ({reason})')

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

        if add_via_script(decision, url):
            subprocess.run(
                ['python3', '.github/scripts/rebuild_readme.py'],
                check=False,
            )
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
            comment(number, 'Claude approved this, but auto-add failed — leaving open for manual review.')
            skipped += 1

    print(f'\nDone. added={added} rejected={rejected} skipped={skipped}')

if __name__ == '__main__':
    main()
