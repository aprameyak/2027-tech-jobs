#!/usr/bin/env python3
"""Reachability check for configured UKG and BambooHR boards."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'companies.yml'
GROUP = os.environ.get('BOARD_GROUP', 'all').strip().lower() or 'all'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; job-scraper-health/1.0)',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}


def check_ukg(entry: dict) -> tuple[str, bool, str]:
    name = entry['name']
    host = entry['host'].strip().rstrip('/')
    if host.startswith('http'):
        host = host.split('://', 1)[1].split('/', 1)[0]
    api = (
        f"https://{host}/{entry['tenant']}/JobBoard/{entry['board']}"
        f"/JobBoardView/LoadSearchResults"
    )
    last_err = ''
    for attempt in range(3):
        try:
            r = requests.post(
                api,
                json={'opportunitySearch': {'Top': 1, 'Skip': 0}},
                headers=HEADERS,
                timeout=(10, 45),
            )
            if r.status_code != 200:
                last_err = f'HTTP {r.status_code}'
                if r.status_code >= 500 and attempt < 2:
                    continue
                return name, False, last_err
            total = (r.json() or {}).get('totalCount')
            return name, True, f'total={total}'
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                continue
    return name, False, last_err


def check_bamboo(entry: dict) -> tuple[str, bool, str]:
    name = entry['name']
    slug = entry['slug']
    url = f'https://{slug}.bamboohr.com/careers/list'
    try:
        r = requests.get(
            url,
            headers={'User-Agent': HEADERS['User-Agent'], 'Accept': 'application/json'},
            timeout=(10, 25),
        )
        if r.status_code != 200:
            return name, False, f'HTTP {r.status_code}'
        n = len((r.json() or {}).get('result') or [])
        return name, True, f'jobs={n}'
    except Exception as e:
        return name, False, str(e)


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    checks = []
    if GROUP in ('all', 'ukg'):
        checks += [('ukg', e, check_ukg) for e in cfg.get('ukg') or []]
    if GROUP in ('all', 'bamboohr'):
        checks += [('bamboohr', e, check_bamboo) for e in cfg.get('bamboohr') or []]

    if not checks:
        print(f'No boards to check for BOARD_GROUP={GROUP!r}')
        return 0

    print(f'Health-checking {len(checks)} board(s) (group={GROUP})...')
    failed = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(fn, entry): (kind, entry['name']) for kind, entry, fn in checks}
        for fut in as_completed(futs):
            kind, _ = futs[fut]
            name, ok, detail = fut.result()
            mark = 'OK' if ok else 'FAIL'
            print(f'  [{kind}] {mark} {name} ({detail})')
            if not ok:
                failed.append(f'{kind}:{name} ({detail})')

    if failed:
        print(f'\nBOARD HEALTH FAIL: {len(failed)} unreachable')
        for f in failed:
            print(f'  - {f}')
        return 1

    print(f'\nBOARD HEALTH PASS: {len(checks)}/{len(checks)} reachable')
    return 0


if __name__ == '__main__':
    sys.exit(main())
