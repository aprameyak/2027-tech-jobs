#!/usr/bin/env python3
\
\
\
   

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
from quality_gate import normalize_url as _qg_normalize_url

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
    """Match quality_gate URL identity so apply cannot reintroduce live dups."""
    if not u:
        return ''
    return _qg_normalize_url(u)

def _dedupe_live_urls(listings):
    """Keep first live row per normalized URL; close later duplicates."""
    seen = {}
    closed = 0
    for e in listings:
        url = e.get('url') or ''
        if not url:
            continue
        n = _norm_url(url)
        if not n:
            continue
        if n in seen:
            e['url'] = ''
            closed += 1
        else:
            seen[n] = e
    return closed

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
    consumed: list[Path] = []

    for pending_file in pending_files:
        with open(pending_file) as f:
            pending = json.load(f)
        if not isinstance(pending, list):
            print(f'  Skip (bad JSON shape): {pending_file.name}')
            continue
        total_pending += len(pending)
        for entry in pending:
            if not isinstance(entry, dict):
                skipped_invalid += 1
                continue
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
        consumed.append(pending_file)

    if skipped_invalid:
        print(f'  Skipped {skipped_invalid} invalid pending entr(y/ies)')

    closed_dups = _dedupe_live_urls(listings)
    if closed_dups:
        print(f'  Closed {closed_dups} live URL duplicate(s) after merge')
        added = max(added, 1)  # force write/rebuild/gate path

    if added > 0 or closed_dups:
        tmp = LISTINGS_FILE.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(listings, f, indent=2, ensure_ascii=False)
            f.write('\n')
        tmp.replace(LISTINGS_FILE)

        result = subprocess.run(
            ['python3', '.github/scripts/rebuild_readme.py'],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f'rebuild_readme.py failed: {result.stderr[:300]}')
            sys.exit(1)
        print(result.stdout.strip() if result.stdout else 'rebuild ok')

        gate = subprocess.run(
            ['python3', '.github/scripts/validate_listings.py'],
            capture_output=True, text=True,
        )
        print(gate.stdout.strip() if gate.stdout else '')
        if gate.returncode != 0:
            print(f'validate_listings.py failed after apply:\n{gate.stderr[:400]}')
            print(gate.stdout)
            sys.exit(1)

        qg = subprocess.run(
            ['python3', '.github/scripts/quality_gate.py'],
            capture_output=True, text=True,
        )
        # Always surface ERROR lines so CI logs are actionable.
        out = (qg.stdout or '') + (qg.stderr or '')
        for line in out.splitlines():
            if 'ERROR:' in line or 'QUALITY GATE' in line or line.startswith('Checked '):
                print(line)
        if qg.returncode != 0:
            print(f'quality_gate.py failed after apply — not clearing pending')
            # Print a short warning sample for context
            warns = [ln for ln in out.splitlines() if 'WARN:' in ln][:5]
            for ln in warns:
                print(ln)
            sys.exit(1)

        print(f'README rebuilt — {added} listing(s) added')
    elif total_pending == 0:
        print('No pending entries to apply — listings.json unchanged')
    else:
        print('All pending entries were duplicates or invalid — listings.json unchanged')

    # Only clear pending after a successful apply path (or pure no-op/dup clear).
    for pending_file in consumed:
        try:
            pending_file.unlink()
            print(f'  Removed {pending_file.name}')
        except FileNotFoundError:
            pass

if __name__ == '__main__':
    main()
