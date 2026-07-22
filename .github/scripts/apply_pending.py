#!/usr/bin/env python3
"""
Merge all pending_{group}.json discovery files into listings.json and rebuild README.
Called by the apply job after all board-group scrape jobs finish.
"""

import json
import re
import subprocess
from pathlib import Path

LISTINGS_FILE = Path('listings.json')
DATA_DIR = Path('.github/data')


def _norm_url(u):
    u = u.split('?')[0].rstrip('/')
    u = re.sub(r'(myworkdayjobs\.com)/en-[A-Z]{2}/[^/]+/job/', r'\1/job/', u)
    return u


def main():
    pending_files = sorted(DATA_DIR.glob('pending_*.json'))
    if not pending_files:
        print('No pending files found — nothing to apply')
        return

    print(f'Found {len(pending_files)} pending file(s): {[f.name for f in pending_files]}')

    with open(LISTINGS_FILE) as f:
        listings = json.load(f)

    existing_urls = {_norm_url(e.get('url', '')) for e in listings}
    added = 0
    total_pending = 0

    for pending_file in pending_files:
        with open(pending_file) as f:
            pending = json.load(f)
        total_pending += len(pending)
        for entry in pending:
            if _norm_url(entry.get('url', '')) not in existing_urls:
                listings.append(entry)
                existing_urls.add(_norm_url(entry['url']))
                added += 1
                print(f'  Added: {entry["company"]} — {entry["role"]}')
            else:
                print(f'  Skip (dup): {entry["company"]} — {entry["role"]}')
        pending_file.unlink()
        print(f'  Removed {pending_file.name}')

    if added > 0:
        tmp = LISTINGS_FILE.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(listings, f, indent=2)
        tmp.replace(LISTINGS_FILE)

        result = subprocess.run(
            ['python3', '.github/scripts/rebuild_readme.py'],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f'rebuild_readme.py failed: {result.stderr[:300]}')
        else:
            print(f'README rebuilt — {added} listing(s) added')
    elif total_pending == 0:
        print('No pending entries to apply — listings.json unchanged')
    else:
        print('All pending entries were duplicates — listings.json unchanged')


if __name__ == '__main__':
    main()
