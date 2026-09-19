#!/usr/bin/env python3

import json
import re
import sys
from datetime import datetime
from pathlib import Path

LISTINGS_FILE = Path('listings.json')
README_FILE = Path('README.md')
CLOSED_FILE = Path('CLOSED.md')

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

# Newest rows shown in README per board. Full *open* tables live in
# SUMMER/OFFCYCLE/NEWGRAD; closed rows live in CLOSED.md — keeps the repo
# homepage under GitHub's ~500KB README render limit (same pattern as peer lists).
README_PREVIEW_ROWS = 75

TOC_HREFS = {
    'summer': './SUMMER.md',
    'offcycle': './OFFCYCLE.md',
    'newgrad': './NEWGRAD.md',
}

CATEGORY_FILES = {
    'summer': {
        'swe': Path('SUMMER-SWE.md'),
        'pm': Path('SUMMER-PM.md'),
        'ai_ml': Path('SUMMER-AI-ML.md'),
        'quant': Path('SUMMER-QUANT.md'),
        'other': Path('SUMMER-OTHER.md'),
    },
    'offcycle': {
        'swe': Path('OFFCYCLE-SWE.md'),
        'pm': Path('OFFCYCLE-PM.md'),
        'ai_ml': Path('OFFCYCLE-AI-ML.md'),
        'quant': Path('OFFCYCLE-QUANT.md'),
        'other': Path('OFFCYCLE-OTHER.md'),
    },
    'newgrad': {
        'swe': Path('NEWGRAD-SWE.md'),
        'pm': Path('NEWGRAD-PM.md'),
        'ai_ml': Path('NEWGRAD-AI-ML.md'),
        'quant': Path('NEWGRAD-QUANT.md'),
        'other': Path('NEWGRAD-OTHER.md'),
    },
}


CATEGORIES = (
    ('swe', '💻 Software Engineering'),
    ('pm', '📱 Product Management'),
    ('ai_ml', '🤖 Data Science, AI & Machine Learning'),
    ('quant', '📈 Quantitative Finance'),
    ('other', '🧩 Other Tech'),
)

CATEGORY_TITLES = {
    'swe': 'Software Engineering',
    'pm': 'Product Management',
    'ai_ml': 'Data Science, AI & Machine Learning',
    'quant': 'Quantitative Finance',
    'other': 'Other Tech',
}

def classify_category(role):
    t = (role or '').lower()
    if re.search(
        r'\bquant(?:itative)?\b|\btrading\b|\btrader\b|market maker|'
        r'prop(?:rietary)? trad',
        t,
    ):
        return 'quant'
    if re.search(
        r'product manager|product management|\bapm\b|associate product|'
        r'product owner|technical product',
        t,
    ):
        return 'pm'
    if re.search(
        r'machine learning|\bmle\b|\bai\b|artificial intelligence|gen\s*ai|genai|'
        r'data scien|data engineer|data analyst|data analytics|deep learning|'
        r'\bllm\b|applied science|research scientist|research engineer',
        t,
    ):
        return 'ai_ml'
    if re.search(
        r'\bsoftware\b|\bdeveloper\b|\bsde\b|\bswe\b|\bdevops\b|\bsre\b|'
        r'site reliability|backend|frontend|full-?stack|platform engineer|'
        r'cloud engineer|security engineer|cyber|programmer|information technology|'
        r'\bit\b engineer|solutions engineer|technology analyst',
        t,
    ):
        return 'swe'
    return 'other'


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


def build_categorized_markdown(marker, entries):
    """Hub file + per-category files so each page stays under GitHub's render limit."""
    title = TABLE_TITLES[marker]
    header = TABLE_HEADERS[marker]
    open_entries = [e for e in entries if e.get('url')]
    closed_n = len(entries) - len(open_entries)

    by_cat = {k: [] for k, _ in CATEGORIES}
    for e in open_entries:
        by_cat[classify_category(e.get('role', ''))].append(e)

    cat_counts = {k: len(by_cat[k]) for k, _ in CATEGORIES}

    # Per-category full tables
    for key, label in CATEGORIES:
        cat_entries = by_cat[key]
        rows = build_table(cat_entries)
        body = '\n'.join(rows) + '\n' if rows else ''
        path = CATEGORY_FILES[marker][key]
        path.write_text(
            f'# {title} — {CATEGORY_TITLES[key]}\n\n'
            f'**{len(cat_entries)}** open listing(s). '
            f'Board hub: [`{TABLE_FILES[marker].name}`](./{TABLE_FILES[marker].name}). '
            f'Back to [`README`](./README.md).\n\n'
            f'{header}'
            f'{body}',
            encoding='utf-8',
        )

    # Hub with category links only (always renders fully)
    parts = [
        f'# {title}\n\n',
        f'**{len(open_entries)}** open listing(s)',
    ]
    if closed_n:
        parts.append(f' · **{closed_n}** closed in [`CLOSED.md`](./CLOSED.md)')
    parts.append(
        '. Canonical data: [`listings.json`](./listings.json). '
        'Back to [`README`](./README.md).\n\n'
        '### Browse by category\n\n'
    )
    for key, label in CATEGORIES:
        href = f'./{CATEGORY_FILES[marker][key].name}'
        parts.append(f'- [{label}]({href}) ({cat_counts[key]})\n')
    parts.append(
        '\n> Full role tables are split by category so GitHub can render every page. '
        'Closed applications are listed separately in [`CLOSED.md`](./CLOSED.md).\n'
    )

    return ''.join(parts), len(open_entries), cat_counts


def format_table_block(marker, rows, open_n, total_n, href, preview=False):
    header = TABLE_HEADERS[marker]
    body = '\n'.join(rows) + '\n' if rows else ''
    if preview and open_n > len(rows):
        summary = (
            f'Showing newest **{len(rows)}** of **{open_n}** open listings '
            f'({total_n} total incl. closed) · [View full open table]({href})\n\n'
        )
    else:
        summary = (
            f'**{open_n}** open · **{total_n - open_n}** closed · '
            f'[View full open table]({href})\n\n'
        )
    return (
        f'## {TABLE_TITLES[marker]}\n\n'
        f'{summary}'
        f'<!-- TABLE_START {marker} -->\n\n'
        f'{header}'
        f'{body}'
        f'<!-- TABLE_END {marker} -->\n'
    )


def write_closed_file(closed_entries):
    if not closed_entries:
        CLOSED_FILE.write_text(
            '# Closed Listings\n\nNo closed listings.\n\n'
            'Back to [`README`](./README.md).\n',
            encoding='utf-8',
        )
        return

    by_type = {'summer': [], 'offcycle': [], 'newgrad': []}
    for e in closed_entries:
        by_type.setdefault(e.get('type', 'summer'), []).append(e)

    parts = [
        '# Closed Listings\n\n',
        f'**{len(closed_entries)}** closed listing(s) (🔒). '
        'Kept for history — roles existed but are no longer accepting applications. '
        'Back to [`README`](./README.md).\n\n',
    ]
    for marker in ('summer', 'offcycle', 'newgrad'):
        entries = by_type.get(marker, [])
        rows = build_table(entries)
        body = '\n'.join(rows) + '\n' if rows else ''
        parts.append(
            f'## {TABLE_TITLES[marker]}\n\n'
            f'{len(entries)} closed\n\n'
            f'{TABLE_HEADERS[marker]}'
            f'{body}\n'
        )
    CLOSED_FILE.write_text(''.join(parts), encoding='utf-8')


def update_readme(
    summer_rows, offcycle_rows, newgrad_rows,
    summer_open, offcycle_open, newgrad_open,
    summer_n, offcycle_n, newgrad_n,
    summer_cats, offcycle_cats, newgrad_cats,
    closed_n,
):
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

    open_total = summer_open + offcycle_open + newgrad_open

    def cat_lines(cats, marker):
        lines = []
        for key, label in CATEGORIES:
            href = f'./{CATEGORY_FILES[marker][key].name}'
            lines.append(f'  - [{label}]({href}) ({cats.get(key, 0)})')
        return '\n'.join(lines)

    toc = (
        f'**Browse the searchable site:** [aprameyak-jobs.vercel.app](https://aprameyak-jobs.vercel.app/)\n\n'
        f'### Browse {open_total} open roles\n\n'
        f'- [☀️ Summer 2027 Internships]({TOC_HREFS["summer"]}) '
        f'({summer_open} open / {summer_n} total)\n'
        f'{cat_lines(summer_cats, "summer")}\n'
        f'- [🔄 Off-Cycle Internships & Co-ops]({TOC_HREFS["offcycle"]}) '
        f'({offcycle_open} open / {offcycle_n} total)\n'
        f'{cat_lines(offcycle_cats, "offcycle")}\n'
        f'- [🎓 New Grad 2027]({TOC_HREFS["newgrad"]}) '
        f'({newgrad_open} open / {newgrad_n} total)\n'
        f'{cat_lines(newgrad_cats, "newgrad")}\n'
        f'- [🔒 Closed listings](./CLOSED.md) ({closed_n})\n'
    )

    # Remove prior truncation notes so TOC replace stays idempotent.
    content = re.sub(
        r'\n*> GitHub truncates very large READMEs[^\n]*\n?',
        '\n',
        content,
    )

    toc_pattern = re.compile(
        r'(?:\*\*Browse the searchable site:\*\* \[aprameyak-jobs\.vercel\.app\]\([^)]+\)\n\n)?'
        r'(?:### Browse \d+ open roles\n\n)?'
        r'- \[☀️ Summer 2027 Internships\]\([^)]+\)[^\n]*\n'
        r'(?:  - \[[^\]]+\]\([^)]+\)[^\n]*\n)*'
        r'- \[🔄 Off-Cycle Internships & Co-ops\]\([^)]+\)[^\n]*\n'
        r'(?:  - \[[^\]]+\]\([^)]+\)[^\n]*\n)*'
        r'- \[🎓 New Grad 2027\]\([^)]+\)[^\n]*\n'
        r'(?:  - \[[^\]]+\]\([^)]+\)[^\n]*\n)*'
        r'(?:- \[🔒 Closed listings\]\([^)]+\)[^\n]*\n)?'
    )
    if toc_pattern.search(content):
        content = toc_pattern.sub(toc, content, count=1)
    else:
        print('ERROR: Could not find TOC links to update in README.md')
        sys.exit(1)

    # Ensure legend mentions closed file.
    if 'Closed listings' not in content and '## Legend' in content:
        content = content.replace(
            ' - 🔒 - Application is closed\n',
            ' - 🔒 - Application is closed '
            '([full closed list](./CLOSED.md))\n',
            1,
        )

    content = re.sub(r'(?:\n---\s*){2,}\n', '\n---\n', content)
    content = re.sub(r'\n{3,}', '\n\n', content)

    # README previews use open rows only (newest first — build_table sorts closed last).
    tables = (
        format_table_block(
            'summer', summer_rows[:README_PREVIEW_ROWS], summer_open, summer_n,
            TOC_HREFS['summer'], preview=True,
        )
        + '\n'
        + format_table_block(
            'offcycle', offcycle_rows[:README_PREVIEW_ROWS], offcycle_open, offcycle_n,
            TOC_HREFS['offcycle'], preview=True,
        )
        + '\n'
        + format_table_block(
            'newgrad', newgrad_rows[:README_PREVIEW_ROWS], newgrad_open, newgrad_n,
            TOC_HREFS['newgrad'], preview=True,
        )
    )

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
    closed = [e for e in listings if not e.get('url')]

    print(
        f'Loaded {len(listings)} listings: '
        f'{len(summer)} summer, {len(offcycle)} offcycle, {len(newgrad)} newgrad '
        f'({len(closed)} closed)'
    )

    summer_md, summer_open, summer_cats = build_categorized_markdown('summer', summer)
    offcycle_md, offcycle_open, offcycle_cats = build_categorized_markdown('offcycle', offcycle)
    newgrad_md, newgrad_open, newgrad_cats = build_categorized_markdown('newgrad', newgrad)

    TABLE_FILES['summer'].write_text(summer_md, encoding='utf-8')
    TABLE_FILES['offcycle'].write_text(offcycle_md, encoding='utf-8')
    TABLE_FILES['newgrad'].write_text(newgrad_md, encoding='utf-8')
    write_closed_file(closed)

    # README previews: open rows only, newest first.
    summer_rows = build_table([e for e in summer if e.get('url')])
    offcycle_rows = build_table([e for e in offcycle if e.get('url')])
    newgrad_rows = build_table([e for e in newgrad if e.get('url')])

    update_readme(
        summer_rows, offcycle_rows, newgrad_rows,
        summer_open, offcycle_open, newgrad_open,
        len(summer), len(offcycle), len(newgrad),
        summer_cats, offcycle_cats, newgrad_cats,
        len(closed),
    )

    print(
        'Rebuilt README.md + category tables in SUMMER/OFFCYCLE/NEWGRAD.md '
        f'+ CLOSED.md ({len(closed)} closed)'
    )


if __name__ == '__main__':
    main()
