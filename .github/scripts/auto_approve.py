#!/usr/bin/env python3
"""
Fetches open issues tagged auto-discovered and adds them directly to README.md
and listings.json without requiring manual approval.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

LISTINGS_FILE = Path('listings.json')


def get_auto_discovered_issues(token, repo):
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
            params={'state': 'open', 'labels': 'auto-discovered', 'per_page': 100, 'page': page},
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


def close_issue(token, repo, issue_number):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
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


def format_location(location):
    location = location.strip()
    if ';' in location:
        parts = [p.strip() for p in location.split(';') if p.strip()]
    elif '\n' in location:
        parts = [p.strip() for p in location.split('\n') if p.strip()]
    else:
        return location
    if len(parts) <= 1:
        return parts[0] if parts else location
    inner = '</br>'.join(parts)
    return f'<details><summary>**{len(parts)} locations**</summary>{inner}</details>'


def determine_table(fields):
    listing_type = fields.get('Listing Type', '')
    season = fields.get('Season / Term', '')
    if 'New Grad' in listing_type or '2027 (New Grad' in season:
        return 'newgrad'
    elif season == 'Summer 2027':
        return 'summer'
    else:
        return 'offcycle'


def format_row(fields, table_type):
    company = fields.get('Company Name', '').strip()
    sponsorship = fields.get('Visa Sponsorship?', '')
    citizenship = fields.get('U.S. Citizenship Required?', '')
    if 'not' in sponsorship.lower() or 'no —' in sponsorship.lower():
        company += ' 🛂'
    if 'yes —' in citizenship.lower():
        company += ' 🇺🇸'

    role = fields.get('Role / Job Title', '').strip()
    location = format_location(fields.get('Location', ''))
    education = fields.get('Education Level', 'Undergrad').strip()
    apply_link = fields.get('Direct Application Link', '').strip()
    date = datetime.now().strftime('%b %-d')

    apply_btn = (
        f'<a href="{apply_link}">'
        f'<img src="https://i.imgur.com/u1KNU8z.png" width="118" alt="Apply">'
        f'</a>'
    )

    if table_type == 'offcycle':
        season = fields.get('Season / Term', '').strip()
        return f'| {company} | {role} | {location} | {season} | {education} | {apply_btn} | {date} |'
    else:
        return f'| {company} | {role} | {location} | {education} | {apply_btn} | {date} |'


def insert_row(content, table_marker, row):
    start_marker = f'<!-- TABLE_START {table_marker} -->'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f'ERROR: Could not find table marker: {start_marker}')
        return None
    after_start = content[start_idx:]
    sep_match = re.search(r'\| [-| :]+\|\n', after_start)
    if not sep_match:
        print('ERROR: Could not find table separator row')
        return None
    insert_pos = start_idx + sep_match.end()
    return content[:insert_pos] + row + '\n' + content[insert_pos:]


def load_listings():
    if LISTINGS_FILE.exists():
        with open(LISTINGS_FILE) as f:
            return json.load(f)
    return []


def save_listings(listings):
    with open(LISTINGS_FILE, 'w') as f:
        json.dump(listings, f, indent=2)


def listing_to_json(fields, table_type):
    return {
        'company': fields.get('Company Name', '').strip(),
        'role': fields.get('Role / Job Title', '').strip(),
        'location': fields.get('Location', '').strip(),
        'type': table_type,
        'season': fields.get('Season / Term', '').strip(),
        'education': fields.get('Education Level', 'Undergrad').strip(),
        'url': fields.get('Direct Application Link', '').strip(),
        'sponsorship': fields.get('Visa Sponsorship?', '').strip(),
        'citizenship': fields.get('U.S. Citizenship Required?', '').strip(),
        'date_added': datetime.now().strftime('%Y-%m-%d'),
    }


def main():
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        print('GITHUB_TOKEN or GITHUB_REPOSITORY not set — skipping auto-approve')
        sys.exit(0)

    issues = get_auto_discovered_issues(token, repo)
    print(f'Found {len(issues)} auto-discovered issue(s) to process')

    if not issues:
        return

    with open('README.md', 'r') as f:
        content = f.read()

    listings = load_listings()
    existing_urls = {l.get('url') for l in listings}
    added = 0

    for issue in issues:
        body = issue.get('body', '')
        number = issue.get('number')
        fields = parse_issue_body(body)
        apply_link = fields.get('Direct Application Link', '').strip()

        if not apply_link:
            print(f'  Issue #{number}: no apply link, skipping')
            continue

        if apply_link in content or apply_link in existing_urls:
            print(f'  Issue #{number}: already in repo, closing')
            close_issue(token, repo, number)
            time.sleep(0.5)
            continue

        table_type = determine_table(fields)
        row = format_row(fields, table_type)
        new_content = insert_row(content, table_type, row)
        if new_content is None:
            print(f'  Issue #{number}: failed to insert row')
            continue

        content = new_content
        listings.append(listing_to_json(fields, table_type))
        existing_urls.add(apply_link)
        close_issue(token, repo, number)
        print(f'  Issue #{number}: added "{fields.get("Role / Job Title", "")}" at {fields.get("Company Name", "")}')
        added += 1
        time.sleep(0.5)

    if added > 0:
        with open('README.md', 'w') as f:
            f.write(content)
        save_listings(listings)
        print(f'\nAdded {added} listing(s)')
    else:
        print('\nNo new listings to add')


if __name__ == '__main__':
    main()
