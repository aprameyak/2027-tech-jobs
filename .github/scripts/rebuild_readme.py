#!/usr/bin/env python3

import json
import re
import sys
from datetime import datetime
from pathlib import Path

LISTINGS_FILE = Path('listings.json')
README_FILE = Path('README.md')

TABLE_FILES = {
    'summer': Path('SUMMER.md'),
    'offcycle': Path('OFFCYCLE.md'),
    'newgrad': Path('NEWGRAD.md'),
}

TABLE_TITLES = {
    'summer': '☀️ Summer 2027 Internships',
    'offcycle': '🔄 Off-Cycle Internships & Co-ops',
    'newgrad': '🎓 New Grad 2027',
}

TABLE_HEADERS = {
    'summer': (
        '| Company | Role | Location | Education | Application/Link | Date Added |\n'
        '| ------- | ---- | -------- | --------- | ---------------- | ----------- |\n'
    ),
    'offcycle': (
        '| Company | Role | Location | Season / Term | Education | Application/Link | Date Added |\n'
        '| ------- | ---- | -------- | ------------- | --------- | ---------------- | ----------- |\n'
    ),
    'newgrad': (
        '| Company | Role | Location | Grad Date | Education | Application/Link | Date Added |\n'
        '| ------- | ---- | -------- | --------- | --------- | ---------------- | ----------- |\n'
    ),
}

TOC_ANCHORS = {
    'summer': '#️-summer-2027-internships',
    'offcycle': '#-off-cycle-internships--co-ops',
    'newgrad': '#-new-grad-2027',
}


def _company_sort_key(name):
    name = re.sub(r'[\U0001F000-\U0001FFFF\u2600-\u26FF\u2700-\u27BF]', '', name)
    return name.strip().lower()


def format_company(entry):
    name = entry['company'].strip()
    sponsorship = entry.get('sponsorship', '')
    citizenship = entry.get('citizenship', '')
    if 'not' in sponsorship.lower() or 'no —' in sponsorship.lower():
        name += ' 🛂'
    if 'yes —' in citizenship.lower():
        name += ' 🇺🇸'
    return name


def format_location(location):
    location = location.strip()
    if ';' in location:
        parts = [p.strip() for p in location.split(';') if p.strip()]
    else:
        return location
    if len(parts) <= 1:
        return parts[0] if parts else location
    inner = '</br>'.join(parts)
    return f'<details><summary>**{len(parts)} locations**</summary>{inner}</details>'


def format_date(date_added):
    try:
        dt = datetime.strptime(date_added, '%Y-%m-%d')
        return dt.strftime('%b %d').replace(' 0', ' ')
    except Exception:
        return date_added


def apply_btn(url):
    if not url:
        return '🔒'
    return f'[Apply]({url})'


def format_row(entry, company_col):
    company = company_col
    role = entry['role'].strip()
    location = format_location(entry['location'])
    education = entry.get('education', 'Undergrad').strip()
    url = entry.get('url', '').strip()
    date = format_date(entry['date_added'])
    btn = apply_btn(url)
    table_type = entry['type']

    if table_type == 'offcycle':
        season = entry.get('season', '').strip()
        return f'| {company} | {role} | {location} | {season} | {education} | {btn} | {date} |'
    elif table_type == 'newgrad':
        grad_date = entry.get('grad_date', '').strip()
        return f'| {company} | {role} | {location} | {grad_date} | {education} | {btn} | {date} |'
    else:
        return f'| {company} | {role} | {location} | {education} | {btn} | {date} |'


def build_table(entries):
    def sort_key(e):
        try:
            dt = datetime.strptime(e['date_added'], '%Y-%m-%d')
        except Exception:
            dt = datetime.min
        closed = 1 if not e.get('url', '') else 0
        return (closed, -dt.timestamp(), _company_sort_key(e['company']))

    sorted_entries = sorted(entries, key=sort_key)

    rows = []
    group_tracker = {}

    for entry in sorted_entries:
        company_key = _company_sort_key(entry['company'])
        date_str = entry['date_added']
        group_key = (company_key, date_str)
        company_display = format_company(entry)

        if group_key in group_tracker:
            company_col = '↳'
        else:
            company_col = company_display
            group_tracker[group_key] = True

        rows.append(format_row(entry, company_col))

    return rows


def format_table_block(marker, rows):
    header = TABLE_HEADERS[marker]
    body = '\n'.join(rows) + '\n' if rows else ''
    return (
        f'## {TABLE_TITLES[marker]}\n\n'
        f'<!-- TABLE_START {marker} -->\n\n'
        f'{header}'
        f'{body}'
        f'<!-- TABLE_END {marker} -->\n'
    )


def write_table_file(marker, rows, count):
    title = TABLE_TITLES[marker]
    header = TABLE_HEADERS[marker]
    body = '\n'.join(rows) + '\n' if rows else ''
    content = (
        f'# {title}\n\n'
        f'{count} listing(s). Canonical data lives in [`listings.json`](./listings.json). '
        f'Back to [`README`](./README.md).\n\n'
        f'<!-- TABLE_START {marker} -->\n\n'
        f'{header}'
        f'{body}'
        f'<!-- TABLE_END {marker} -->\n'
    )
    TABLE_FILES[marker].write_text(content, encoding='utf-8')


def update_readme(summer_rows, offcycle_rows, newgrad_rows, summer_n, offcycle_n, newgrad_n):
    if not README_FILE.exists():
        print('ERROR: README.md not found')
        sys.exit(1)

    content = README_FILE.read_text(encoding='utf-8')

    # Drop any previously embedded tables (so rebuild is idempotent).
    for marker in ('summer', 'offcycle', 'newgrad'):
        content = re.sub(
            rf'\n## {re.escape(TABLE_TITLES[marker])}\n.*?<!-- TABLE_END {marker} -->\n?',
            '\n',
            content,
            count=1,
            flags=re.S,
        )

    toc = (
        f'**Browse the searchable site:** [aprameyak-jobs.vercel.app](https://aprameyak-jobs.vercel.app/)\n\n'
        f'- [☀️ Summer 2027 Internships]({TOC_ANCHORS["summer"]}) ({summer_n})\n'
        f'- [🔄 Off-Cycle Internships & Co-ops]({TOC_ANCHORS["offcycle"]}) ({offcycle_n})\n'
        f'- [🎓 New Grad 2027]({TOC_ANCHORS["newgrad"]}) ({newgrad_n})\n'
    )

    toc_pattern = re.compile(
        r'(?:\*\*Browse the searchable site:\*\* \[aprameyak-jobs\.vercel\.app\]\([^)]+\)\n\n)?'
        r'- \[☀️ Summer 2027 Internships\]\([^)]+\)(?:\s*\(\d+\))?\n'
        r'- \[🔄 Off-Cycle Internships & Co-ops\]\([^)]+\)(?:\s*\(\d+\))?\n'
        r'- \[🎓 New Grad 2027\]\([^)]+\)(?:\s*\(\d+\))?\n'
    )
    if toc_pattern.search(content):
        content = toc_pattern.sub(toc, content, count=1)
    else:
        print('ERROR: Could not find TOC links to update in README.md')
        sys.exit(1)

    # Collapse leftover separators from prior table removals.
    content = re.sub(r'(?:\n---\s*){2,}\n', '\n---\n', content)
    content = re.sub(r'\n{3,}', '\n\n', content)

    tables = (
        format_table_block('summer', summer_rows)
        + '\n'
        + format_table_block('offcycle', offcycle_rows)
        + '\n'
        + format_table_block('newgrad', newgrad_rows)
    )

    # Insert tables after Legend, before Disclaimer (or License).
    disclaimer = re.search(r'\n## Disclaimer\n', content)
    license_h = re.search(r'\n## License\n', content)
    if disclaimer:
        insert_at = disclaimer.start()
        content = content[:insert_at] + '\n' + tables + content[insert_at:]
    elif license_h:
        insert_at = license_h.start()
        content = content[:insert_at] + '\n' + tables + content[insert_at:]
    else:
        content = content.rstrip() + '\n\n' + tables

    content = re.sub(r'(?:\n---\s*){2,}\n', '\n---\n', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    README_FILE.write_text(content, encoding='utf-8')


def main():
    if not LISTINGS_FILE.exists():
        print('ERROR: listings.json not found')
        sys.exit(1)

    with open(LISTINGS_FILE) as f:
        listings = json.load(f)

    summer = [e for e in listings if e['type'] == 'summer']
    offcycle = [e for e in listings if e['type'] == 'offcycle']
    newgrad = [e for e in listings if e['type'] == 'newgrad']

    print(
        f'Loaded {len(listings)} listings: '
        f'{len(summer)} summer, {len(offcycle)} offcycle, {len(newgrad)} newgrad'
    )

    summer_rows = build_table(summer)
    offcycle_rows = build_table(offcycle)
    newgrad_rows = build_table(newgrad)

    write_table_file('summer', summer_rows, len(summer))
    write_table_file('offcycle', offcycle_rows, len(offcycle))
    write_table_file('newgrad', newgrad_rows, len(newgrad))
    update_readme(
        summer_rows, offcycle_rows, newgrad_rows,
        len(summer), len(offcycle), len(newgrad),
    )

    print('Rebuilt README.md tables plus SUMMER.md, OFFCYCLE.md, and NEWGRAD.md')


if __name__ == '__main__':
    main()
