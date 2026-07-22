#!/usr/bin/env python3

import json
import re
import time
from pathlib import Path

import requests

SKIP_DOMAINS = [
    'careers.ibm.com',
    'www.tesla.com',
    'tesla.com',
    'lockheedmartinjobs.com',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

APPLY_BTN_PATTERN = re.compile(
    r'<a href="([^"]+)"[^>]*><img src="https://i\.imgur\.com/u1KNU8z\.png" width="118" alt="Apply"></a>'
)

WD_BARE = re.compile(r'^(https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com)/job/')


def load_workday_boards():
    company_board = {}
    tenant_board = {}
    cur = None
    section = None
    tenant = None
    for line in Path('companies.yml').read_text().splitlines():
        if line.startswith('workday:'):
            section = 'workday'
            continue
        if line.endswith(':') and not line.startswith(' '):
            section = None
        if section != 'workday':
            continue
        m = re.match(r'- name: (.+)', line)
        if m:
            cur = m.group(1).strip()
        if cur and line.strip().startswith('tenant:'):
            tenant = line.split('tenant:', 1)[1].strip()
        if cur and line.strip().startswith('board:'):
            board = line.split('board:', 1)[1].strip()
            company_board[cur] = board
            if tenant:
                tenant_board[tenant] = board
    return company_board, tenant_board


def fix_workday_url(url, company_board, tenant_board, company=None):
    m = WD_BARE.match(url)
    if not m:
        return url
    base, tenant = m.group(1), m.group(2)
    board = company_board.get(company or '') or tenant_board.get(tenant)
    if not board:
        return url
    return url.replace(f'{base}/job/', f'{base}/{board}/job/')


def should_skip(url):
    for domain in SKIP_DOMAINS:
        if domain in url:
            return True
    return False


def is_link_alive(url):
    try:
        resp = requests.get(url, timeout=12, allow_redirects=True, headers=HEADERS)
        return resp.status_code < 404
    except Exception as e:
        print(f'  Request error: {e}')
        return False


def resolve_url(url, company_board, tenant_board, company=None):
    """Return a working URL, trying Workday board injection if the bare URL 404s."""
    if should_skip(url):
        return url, True

    if is_link_alive(url):
        return url, True

    fixed = fix_workday_url(url, company_board, tenant_board, company)
    if fixed != url and is_link_alive(fixed):
        print(f'  FIXED (board injection): {fixed}')
        return fixed, True

    return url, False


def mark_listing_closed(entry):
    """Mark a listing closed. Only clears url — all other metadata is preserved."""
    entry['url'] = ''


def main():
    company_board, tenant_board = load_workday_boards()

    with open('README.md', 'r') as f:
        content = f.read()

    listings_file = Path('listings.json')
    listings = []
    listings_by_url = {}
    if listings_file.exists():
        with open(listings_file) as f:
            listings = json.load(f)
        for entry in listings:
            u = entry.get('url', '')
            if u:
                listings_by_url[u] = entry

    matches = list(APPLY_BTN_PATTERN.finditer(content))
    print(f'Found {len(matches)} links to check')

    dead = []
    url_replacements = {}
    for match in matches:
        url = match.group(1)
        company = listings_by_url.get(url, {}).get('company')
        print(f'  Checking: {url}')
        resolved, alive = resolve_url(url, company_board, tenant_board, company)
        if not alive:
            print(f'  DEAD: {url}')
            dead.append((url, match.group(0)))
        else:
            print(f'  OK')
            if resolved != url:
                url_replacements[url] = resolved
        time.sleep(0.75)

    if url_replacements:
        for old, new in url_replacements.items():
            content = content.replace(old, new)
            for entry in listings:
                if entry.get('url') == old:
                    entry['url'] = new
        with open('README.md', 'w') as f:
            f.write(content)
        tmp = listings_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(listings, f, indent=2)
        tmp.replace(listings_file)
        print(f'\nFixed {len(url_replacements)} Workday URL(s)')

    if dead:
        dead_urls = {url for url, _ in dead}

        for url, btn in dead:
            content = content.replace(btn, '🔒')
        with open('README.md', 'w') as f:
            f.write(content)

        if listings_file.exists():
            with open(listings_file) as f:
                listings = json.load(f)
            for entry in listings:
                if entry.get('url', '') in dead_urls:
                    # Only clear url — preserve date_added and all other metadata.
                    mark_listing_closed(entry)
            tmp = listings_file.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(listings, f, indent=2)
            tmp.replace(listings_file)

        print(f'\nMarked {len(dead)} dead link(s) as 🔒')
    elif not url_replacements:
        print('\nAll checked links are active')


if __name__ == '__main__':
    main()
