#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from grad_date import infer_grad_date

LISTINGS_FILE = Path('listings.json')

STRIP_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id',
    'source', 'src', 'ref', 'referer',
    'lever-source', 'lever-origin',
    'gh_src',
}


def normalize_url(url):
    try:
        p = urlparse(url.strip())
        params = {k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
                  if k.lower() not in STRIP_PARAMS}
        u = urlunparse(p._replace(
            scheme=p.scheme.lower(),
            netloc=p.netloc.lower(),
            query=urlencode(sorted(params.items()), doseq=True),
            fragment='',
        ))
        u = re.sub(r'(myworkdayjobs\.com)/en-[A-Z]{2}/[^/]+/job/', r'\1/job/', u)
        return u
    except Exception:
        return url


def existing_normalized_urls(listings):
    return {normalize_url(l.get('url', '')) for l in listings}


def get_approved_issues(token, repo):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    issues = []
    page = 1
    while True:
        resp = requests.get(
            f'https://api.github.com/repos/{repo}/issues',
            headers=headers,
            params={'state': 'open', 'labels': 'approved', 'per_page': 100, 'page': page},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f'GitHub API error: {resp.status_code}')
            break
        batch = resp.json()
        if not batch:
            break
        issues.extend(batch)
        page += 1
    return issues


def comment_and_close(token, repo, issue_number, message=None):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    body = message or '✅ Listing added to the repo! Thanks for contributing.'
    requests.post(
        f'https://api.github.com/repos/{repo}/issues/{issue_number}/comments',
        headers=headers,
        json={'body': body},
        timeout=10,
    )
    requests.patch(
        f'https://api.github.com/repos/{repo}/issues/{issue_number}',
        headers=headers,
        json={'state': 'closed'},
        timeout=10,
    )


def parse_issue_body(body):
    fields = {}
    sections = re.split(r'^### ', body, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        key = lines[0].strip()
        value = '\n'.join(lines[1:]).strip()
        if value == '_No response_':
            value = ''
        fields[key] = value
    return fields


def determine_table(fields):
    listing_type = fields.get('Listing Type', '')
    season = fields.get('Season / Term', '')
    role = fields.get('Role / Job Title', '').lower()

    if 'New Grad' in listing_type or '2027 (New Grad' in season:
        return 'newgrad'

    # Graduate full-time roles (e.g. IMC) are often mislabeled as internships
    if re.search(r'\bgraduate\b', role) and 'intern' not in role:
        return 'newgrad'

    if season == 'Summer 2027':
        return 'summer'
    return 'offcycle'


def load_listings():
    if LISTINGS_FILE.exists():
        with open(LISTINGS_FILE) as f:
            return json.load(f)
    return []


def save_listings(listings):
    with open(LISTINGS_FILE, 'w') as f:
        json.dump(listings, f, indent=2)


def normalize_location(location):
    """Normalize issue-form locations to City, ST / City, Province."""
    if not location:
        return location
    US = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
        'illinois': 'IL', 'indiana': 'IN', 'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN',
        'new york': 'NY', 'north carolina': 'NC', 'ohio': 'OH', 'oregon': 'OR', 'pennsylvania': 'PA',
        'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'virginia': 'VA', 'washington': 'WA',
        'district of columbia': 'DC',
    }
    CA = {'ontario': 'ON', 'quebec': 'QC', 'british columbia': 'BC', 'alberta': 'AB'}
    CITY = {
        'ottawa': 'Ottawa, ON', 'toronto': 'Toronto, ON', 'atlanta': 'Atlanta, GA',
        'chicago': 'Chicago, IL', 'seattle': 'Seattle, WA', 'austin': 'Austin, TX',
    }

    def part(p):
        p = p.strip()
        if not p:
            return p
        pl = p.lower()
        if pl.startswith('remote'):
            return 'Remote (US)' if 'canada' not in pl else 'Remote (Canada)'
        m = re.match(r'^US,\s*([^,]+),\s*(.+)$', p, re.I)
        if m:
            ab = US.get(m.group(1).strip().lower()) or CA.get(m.group(1).strip().lower())
            if ab:
                return f'{m.group(2).strip()}, {ab}'
        bits = [b.strip() for b in p.split(',')]
        if len(bits) == 2:
            ab = US.get(bits[1].lower()) or CA.get(bits[1].lower())
            if ab:
                return f'{bits[0]}, {ab}'
        if len(bits) == 3 and bits[2].upper() == 'USA':
            ab = US.get(bits[1].lower())
            if ab:
                return f'{bits[0]}, {ab}'
        return CITY.get(pl, p)

    location = location.replace('•', ';')
    return '; '.join(part(p) for p in re.split(r'[;\n]', location) if p.strip())


def listing_to_json(fields, table_type):
    entry = {
        'company': fields.get('Company Name', '').strip(),
        'role': fields.get('Role / Job Title', '').strip(),
        'location': normalize_location(fields.get('Location', '').strip()),
        'type': table_type,
        'season': fields.get('Season / Term', '').strip(),
        'education': fields.get('Education Level', 'Undergrad').strip(),
        'url': fields.get('Direct Application Link', '').strip(),
        'sponsorship': fields.get('Visa Sponsorship?', '').strip(),
        'citizenship': fields.get('U.S. Citizenship Required?', '').strip(),
        'date_added': datetime.now().strftime('%Y-%m-%d'),
    }
    if table_type == 'newgrad':
        entry['grad_date'] = infer_grad_date(entry['role'], entry.get('url', ''))
    return entry


def rebuild_readme():
    result = subprocess.run(
        ['python3', '.github/scripts/rebuild_readme.py'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f'ERROR: rebuild_readme.py failed: {result.stderr[:500]}')
        sys.exit(1)
    print(result.stdout.strip())


def main():
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        print('GITHUB_TOKEN or GITHUB_REPOSITORY not set — skipping')
        sys.exit(0)

    issues = get_approved_issues(token, repo)
    print(f'Found {len(issues)} approved issue(s) to process')

    if not issues:
        return

    listings = load_listings()
    seen_normalized = existing_normalized_urls(listings)
    added = 0

    for issue in issues:
        body = issue.get('body', '')
        number = issue.get('number')
        fields = parse_issue_body(body)
        apply_link = fields.get('Direct Application Link', '').strip()

        if not apply_link:
            print(f'  Issue #{number}: no apply link, skipping')
            continue

        if normalize_url(apply_link) in seen_normalized:
            print(f'  Issue #{number}: already in repo, closing')
            comment_and_close(
                token, repo, number,
                '✅ This listing is already in the repo — closing without adding a duplicate.',
            )
            time.sleep(0.5)
            continue

        table_type = determine_table(fields)
        listings.append(listing_to_json(fields, table_type))
        seen_normalized.add(normalize_url(apply_link))
        comment_and_close(token, repo, number)
        print(f'  Issue #{number}: added "{fields.get("Role / Job Title", "")}" at {fields.get("Company Name", "")}')
        added += 1
        time.sleep(0.5)

    if added > 0:
        save_listings(listings)
        rebuild_readme()
        print(f'\nAdded {added} listing(s)')
    else:
        print('\nNo new listings to add')


if __name__ == '__main__':
    main()
