#!/usr/bin/env python3
"""Validate companies.yml structure used by the scraper.

Fails (exit 1) on missing required fields, duplicate board identifiers,
or unreadable YAML — so CI catches config drift before hourly scrapes.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_FILE = ROOT / 'companies.yml'

REQUIRED = {
    'greenhouse': ('name', 'slug'),
    'lever': ('name', 'slug'),
    'ashby': ('name', 'slug'),
    'workable': ('name', 'slug'),
    'recruitee': ('name', 'slug'),
    'pinpoint': ('name', 'slug'),
    'smartrecruiters': ('name', 'identifier'),
    'workday': ('name', 'tenant', 'instance', 'board'),
    'oracle': ('name', 'host', 'site'),
    'icims': ('name', 'host'),
    'avature': ('name', 'portal'),
    'linkedin': ('name', 'company_id'),
}

ID_FIELD = {
    'greenhouse': 'slug',
    'lever': 'slug',
    'ashby': 'slug',
    'workable': 'slug',
    'recruitee': 'slug',
    'pinpoint': 'slug',
    'smartrecruiters': 'identifier',
    'oracle': 'host',
    'icims': 'host',
    'avature': 'portal',
    'linkedin': 'company_id',
}


def main() -> int:
    try:
        config = yaml.safe_load(COMPANIES_FILE.read_text()) or {}
    except Exception as e:
        print(f'ERROR: failed to load companies.yml: {e}')
        return 1

    if not isinstance(config, dict):
        print('ERROR: companies.yml root must be a mapping')
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    totals: dict[str, int] = {}

    for board, entries in config.items():
        if not isinstance(entries, list):
            errors.append(f'{board}: expected a list, got {type(entries).__name__}')
            continue
        totals[board] = len(entries)
        req = REQUIRED.get(board)
        if not req:
            warnings.append(f'{board}: unknown board key ({len(entries)} entries)')
            continue

        seen_ids: dict[str, str] = {}
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f'{board}[{i}]: expected mapping')
                continue
            for field in req:
                if field not in entry or entry[field] in (None, ''):
                    errors.append(
                        f'{board}[{i}] {entry.get("name", "?")!r}: missing {field}'
                    )
            if board == 'workday':
                key = (
                    f'{str(entry.get("tenant", "")).lower()}|'
                    f'{str(entry.get("instance", "")).lower()}|'
                    f'{str(entry.get("board", "")).lower()}'
                )
            else:
                id_field = ID_FIELD.get(board)
                key = str(entry.get(id_field, '')).lower() if id_field else ''
            if key:
                if key in seen_ids:
                    errors.append(
                        f'{board}: duplicate id {key!r} '
                        f'({seen_ids[key]} vs {entry.get("name")})'
                    )
                else:
                    seen_ids[key] = str(entry.get('name', ''))

    total = sum(totals.values())
    print(f'companies.yml: {total} entries across {len(totals)} boards')
    for board, n in sorted(totals.items()):
        print(f'  {board}: {n}')
    for msg in warnings:
        print(f'  WARN: {msg}')
    for msg in errors:
        print(f'  ERROR: {msg}')

    if errors:
        print('COMPANIES VALIDATE: FAIL')
        return 1
    print('COMPANIES VALIDATE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
