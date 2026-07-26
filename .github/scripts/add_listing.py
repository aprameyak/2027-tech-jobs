#!/usr/bin/env python3

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from grad_date import infer_grad_date

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

LISTINGS_FILE = Path('listings.json')


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


def format_company(company, sponsorship, citizenship):
    flags = ''
    if 'not' in sponsorship.lower() or 'no —' in sponsorship.lower():
        flags += ' 🛂'
    if 'yes —' in citizenship.lower():
        flags += ' 🇺🇸'
    return company.strip() + flags


_STATE_MAP = {
    'Alabama':'AL','Alaska':'AK','Arizona':'AZ','Arkansas':'AR','California':'CA',
    'Colorado':'CO','Connecticut':'CT','Delaware':'DE','Florida':'FL','Georgia':'GA',
    'Hawaii':'HI','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS',
    'Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA',
    'Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT',
    'Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM',
    'New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK',
    'Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC',
    'South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT',
    'Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY',
    'District of Columbia':'DC',
}
_PROV_MAP = {
    'Alberta':'AB','British Columbia':'BC','Manitoba':'MB','New Brunswick':'NB',
    'Newfoundland and Labrador':'NL','Nova Scotia':'NS','Northwest Territories':'NT',
    'Nunavut':'NU','Ontario':'ON','Prince Edward Island':'PE','Quebec':'QC',
    'Saskatchewan':'SK','Yukon':'YT',
}
_COUNTRY_SUFFIX = re.compile(
    r',?\s*(United States of America|United States|USA)\s*$', re.I)
_CANADA_SUFFIX = re.compile(r',?\s*Canada\s*$', re.I)


def _normalize_one_location(loc):
    """Normalize a single location string to City, ST format."""
    loc = loc.strip()
    if re.match(r'^(USA|United States of America|United States)$', loc, re.I):
        return 'Remote (US)'
    if re.match(r'^Canada$', loc, re.I):
        return 'Remote (Canada)'
    loc = _COUNTRY_SUFFIX.sub('', loc)
    loc = _CANADA_SUFFIX.sub('', loc)
    for name, abbr in _STATE_MAP.items():
        loc = re.sub(rf',\s*{re.escape(name)}\b', f', {abbr}', loc)
    for name, abbr in _PROV_MAP.items():
        loc = re.sub(rf',\s*{re.escape(name)}\b', f', {abbr}', loc)
    loc = re.sub(r'\s*,\s*', ', ', loc).strip().strip(',').strip()
    # Normalize unicode city names (e.g. Montréal → Montreal)
    import unicodedata
    loc = ''.join(
        c if unicodedata.category(c) != 'Mn' else ''
        for c in unicodedata.normalize('NFD', loc)
    )
    return loc


def format_location(location):
    location = location.strip()
    if ';' in location:
        parts = [p.strip() for p in location.split(';') if p.strip()]
    elif '\n' in location:
        parts = [p.strip() for p in location.split('\n') if p.strip()]
    else:
        return _normalize_one_location(location)

    parts = [_normalize_one_location(p) for p in parts if p.strip()]

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
        f'<a href="{apply_link}" target="_blank" rel="noopener noreferrer">'
        f'<img src="https://i.imgur.com/u1KNU8z.png" width="118" alt="Apply">'
        f'</a>'
    )

    if table_type == 'offcycle':
        season = fields.get('Season / Term', '').strip()
        return f'| {company} | {role} | {location} | {season} | {education} | {apply_btn} | {date} |'
    elif table_type == 'newgrad':
        return f'| {company} | {role} | {location} |  | {education} | {apply_btn} | {date} |'
    else:
        return f'| {company} | {role} | {location} | {education} | {apply_btn} | {date} |'


def _company_sort_key(name):
    name = re.sub(r'[\U0001F000-\U0001FFFF\u2600-\u26FF\u2700-\u27BF]', '', name)
    return name.strip().lower()


def _parse_date(date_str):
    date_str = date_str.strip()
    current_year = datetime.now().year
    for year in [current_year, current_year - 1]:
        try:
            return datetime.strptime(f'{date_str} {year}', '%b %d %Y')
        except ValueError:
            pass
    return None


def _get_row_date(row):
    cols = [c.strip() for c in row.split('|')]
    cols = [c for c in cols if c]
    return _parse_date(cols[-1]) if cols else None


def _get_row_date_str(row):
    cols = [c.strip() for c in row.split('|')]
    cols = [c for c in cols if c]
    return cols[-1].strip() if cols else ''


def insert_row(content, table_marker, row):
    start_marker = f'<!-- TABLE_START {table_marker} -->'
    end_marker = f'<!-- TABLE_END {table_marker} -->'
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1:
        print(f'ERROR: Could not find table marker: {start_marker}')
        sys.exit(1)

    after_start = content[start_idx:]
    sep_match = re.search(r'\| [-| :]+\|\n', after_start)
    if not sep_match:
        print('ERROR: Could not find table separator row')
        sys.exit(1)

    header_end = start_idx + sep_match.end()
    table_body = content[header_end:end_idx]

    new_company_raw = row.split('|')[1].strip() if '|' in row else ''
    new_key = _company_sort_key(new_company_raw)
    new_date = _get_row_date(row)
    new_date_str = _get_row_date_str(row)

    lines = table_body.splitlines(keepends=True)

    last_group_idx = -1
    in_group = False
    for i, line in enumerate(lines):
        if not line.strip() or not line.startswith('|'):
            continue
        cols = line.split('|')
        if len(cols) < 2:
            continue
        col1 = cols[1].strip()
        if col1 != '↳' and _company_sort_key(col1) == new_key and _get_row_date_str(line.rstrip()) == new_date_str:
            in_group = True
            last_group_idx = i
        elif col1 == '↳' and in_group:
            last_group_idx = i
        elif col1 != '↳':
            in_group = False

    if last_group_idx != -1:
        continuation = re.sub(r'^\| [^|]+ \|', '| ↳ |', row, count=1)
        lines.insert(last_group_idx + 1, continuation + '\n')
        return content[:header_end] + ''.join(lines) + content[end_idx:]

    insert_line = len(lines)
    for i, line in enumerate(lines):
        if not line.strip() or not line.startswith('|'):
            continue
        cols = line.split('|')
        if len(cols) < 2:
            continue
        col1 = cols[1].strip()
        if col1 == '↳':
            continue
        row_date = _get_row_date(line.rstrip())
        if new_date and row_date:
            if new_date > row_date:
                insert_line = i
                break
            elif new_date == row_date:
                if _company_sort_key(col1) > new_key:
                    insert_line = i
                    break
        else:
            if _company_sort_key(col1) > new_key:
                insert_line = i
                break

    lines.insert(insert_line, row + '\n')
    return content[:header_end] + ''.join(lines) + content[end_idx:]


def main():
    body_file = os.environ.get('ISSUE_BODY_FILE', '')
    if body_file and os.path.exists(body_file):
        with open(body_file) as f:
            issue_body = f.read()
    else:
        issue_body = os.environ.get('ISSUE_BODY', '')
    if not issue_body:
        print('ERROR: No issue body found (checked ISSUE_BODY_FILE and ISSUE_BODY)')
        sys.exit(1)

    fields = parse_issue_body(issue_body)
    print(f'Parsed fields: {list(fields.keys())}')

    table_type = determine_table(fields)
    print(f'Target table: {table_type}')

    row = format_row(fields, table_type)
    print(f'Formatted row: {row}')

    apply_link = fields.get('Direct Application Link', '').strip()

    listings = []
    if LISTINGS_FILE.exists():
        with open(LISTINGS_FILE) as f:
            listings = json.load(f)

    existing_urls = {normalize_url(e.get('url', '')) for e in listings}
    if apply_link and normalize_url(apply_link) in existing_urls:
        print(f'SKIP: listing already exists (link found: {apply_link})')
        sys.exit(0)

    with open('README.md', 'r') as f:
        content = f.read()

    new_content = insert_row(content, table_type, row)

    with open('README.md', 'w') as f:
        f.write(new_content)

    entry = {
        'company': fields.get('Company Name', '').strip(),
        'role': fields.get('Role / Job Title', '').strip(),
        'location': _normalize_one_location(fields.get('Location', '').strip()),
        'type': table_type,
        'season': fields.get('Season / Term', '').strip(),
        'education': fields.get('Education Level', 'Undergrad').strip(),
        'url': apply_link,
        'sponsorship': fields.get('Visa Sponsorship?', '').strip(),
        'citizenship': fields.get('U.S. Citizenship Required?', '').strip(),
        'date_added': datetime.now().strftime('%Y-%m-%d'),
    }
    if table_type == 'newgrad':
        entry['grad_date'] = infer_grad_date(entry['role'], entry.get('url', ''))
    listings.append(entry)
    with open(LISTINGS_FILE, 'w') as f:
        json.dump(listings, f, indent=2)

    print('Successfully updated README.md and listings.json')


if __name__ == '__main__':
    main()
