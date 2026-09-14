#!/usr/bin/env python3
"""
Merge all pending_{group}.json discovery files into listings.json and rebuild README.
Called by the apply job after all board-group scrape jobs finish.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from validate_listings import validate_entry

LISTINGS_FILE = Path('listings.json')
DATA_DIR = Path('.github/data')

_UTM_STRIP = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id',
    'source', 'src', 'ref', 'referer', 'lever-source', 'lever-origin', 'gh_src',
}


def _with_aprameyak_utm(url):
    if not url:
        return url
    try:
        p = urlparse(url.strip())
        host = (p.netloc or '').lower()
        if not any(m in host for m in (
            'greenhouse.io', 'lever.co', 'ashbyhq.com', 'myworkdayjobs.com', 'workdaysite.com',
        )):
            return url
        params = {}
        for k, v in parse_qs(p.query, keep_blank_values=True).items():
            kl = k.lower()
            if kl in _UTM_STRIP:
                continue
            cleaned = [x for x in v if x not in ('', 'gh_src=', 'gh_src')]
            if kl == 't' and (not cleaned or all(str(x).startswith('gh_src') for x in cleaned)):
                continue
            if not cleaned and kl != 'gh_jid':
                continue
            params[k] = cleaned if cleaned else v
        params['utm_source'] = ['aprameyak']
        return urlunparse(p._replace(
            query=urlencode(sorted(params.items()), doseq=True),
            fragment='',
        ))
    except Exception:
        return url


def _norm_url(u):
    if not u:
        return u
    u = u.split('?')[0].split('#')[0].rstrip('/')
    m = re.match(r'(https?://)([^/]+)(.*)', u)
    if m:
        scheme, host, path = m.groups()
        host = host.lower()
        if host.startswith('www.'):
            host = host[4:]
        u = scheme + host + path
    u = re.sub(r'/application$', '', u)
    u = re.sub(r'(myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?[^/]+/job/', r'\1/job/', u)
    u = re.sub(r'(_(JR|REQ|R)\d+)-\d+$', r'\1', u, flags=re.I)
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
    skipped_invalid = 0
    total_pending = 0

    for pending_file in pending_files:
        with open(pending_file) as f:
            pending = json.load(f)
        total_pending += len(pending)
        for entry in pending:
            violations = validate_entry(entry)
            if violations:
                skipped_invalid += 1
                print(f'  Skip (invalid): {entry.get("company")} — {entry.get("role", "")[:50]}')
                print(f'    {violations[0][2]}')
                continue
            entry['url'] = _with_aprameyak_utm(entry.get('url', ''))
            if _norm_url(entry.get('url', '')) not in existing_urls:
                listings.append(entry)
                existing_urls.add(_norm_url(entry['url']))
                added += 1
                print(f'  Added: {entry["company"]} — {entry["role"]}')
            else:
                print(f'  Skip (dup): {entry["company"]} — {entry["role"]}')
        pending_file.unlink()
        print(f'  Removed {pending_file.name}')

    if skipped_invalid:
        print(f'  Skipped {skipped_invalid} invalid pending entr(y/ies)')

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
            sys.exit(1)

        print(f'README rebuilt — {added} listing(s) added')
    elif total_pending == 0:
        print('No pending entries to apply — listings.json unchanged')
    else:
        print('All pending entries were duplicates or invalid — listings.json unchanged')

if __name__ == '__main__':
    main()
