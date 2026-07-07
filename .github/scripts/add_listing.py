#!/usr/bin/env python3
"""
Parses a GitHub issue form submission and inserts a formatted row
into the correct table in README.md.
"""

import os
import re
import sys
from datetime import datetime


def parse_issue_body(body):
    """Parse GitHub issue form body into a field dict."""
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


def format_company(company, sponsorship, citizenship):
    flags = ''
    if 'not' in sponsorship.lower() or 'no —' in sponsorship.lower():
        flags += ' 🛂'
    if 'yes —' in citizenship.lower():
        flags += ' 🇺🇸'
    return company.strip() + flags


def format_location(location):
    """Handle single location or multiple locations separated by semicolons."""
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
    company = format_company(
        fields.get('Company Name', ''),
        fields.get('Visa Sponsorship?', ''),
        fields.get('U.S. Citizenship Required?', '')
    )
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
    """Insert row at the top of the correct table (after header + separator)."""
    start_marker = f'<!-- TABLE_START {table_marker} -->'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f'ERROR: Could not find table marker: {start_marker}')
        sys.exit(1)

    after_start = content[start_idx:]
    sep_match = re.search(r'\| [-| :]+\|\n', after_start)
    if not sep_match:
        print('ERROR: Could not find table separator row')
        sys.exit(1)

    insert_pos = start_idx + sep_match.end()
    return content[:insert_pos] + row + '\n' + content[insert_pos:]


def main():
    issue_body = os.environ.get('ISSUE_BODY', '')
    if not issue_body:
        print('ERROR: ISSUE_BODY environment variable is empty')
        sys.exit(1)

    fields = parse_issue_body(issue_body)
    print(f'Parsed fields: {list(fields.keys())}')

    table_type = determine_table(fields)
    print(f'Target table: {table_type}')

    row = format_row(fields, table_type)
    print(f'Formatted row: {row}')

    with open('README.md', 'r') as f:
        content = f.read()

    apply_link = fields.get('Direct Application Link', '').strip()
    if apply_link and apply_link in content:
        print(f'SKIP: listing already exists in README (link found: {apply_link})')
        sys.exit(0)

    new_content = insert_row(content, table_type, row)

    with open('README.md', 'w') as f:
        f.write(new_content)

    print('Successfully updated README.md')


if __name__ == '__main__':
    main()
