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
        return True


def main():
    with open('README.md', 'r') as f:
        content = f.read()

    matches = list(APPLY_BTN_PATTERN.finditer(content))
    print(f'Found {len(matches)} links to check')

    dead = []
    for match in matches:
        url = match.group(1)
        if should_skip(url):
            print(f'  SKIP (bot-blocked domain): {url}')
            continue

        print(f'  Checking: {url}')
        alive = is_link_alive(url)
        if not alive:
            print(f'  DEAD: {url}')
            dead.append((url, match.group(0)))
        else:
            print(f'  OK')
        time.sleep(0.75)

    if dead:
        dead_urls = {url for url, _ in dead}

        for url, btn in dead:
            content = content.replace(btn, '🔒')
        with open('README.md', 'w') as f:
            f.write(content)

        listings_file = Path('listings.json')
        if listings_file.exists():
            with open(listings_file) as f:
                listings = json.load(f)
            for entry in listings:
                if entry.get('url', '') in dead_urls:
                    entry['url'] = ''
            tmp = listings_file.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(listings, f, indent=2)
            tmp.replace(listings_file)

        print(f'\nMarked {len(dead)} dead link(s) as 🔒')
    else:
        print('\nAll checked links are active')


if __name__ == '__main__':
    main()
