#!/usr/bin/env python3
"""
Validate listings.json against CLAUDE.md table classification rules.
Exits 0 if clean, 1 if violations are found.
"""

import json
import re
import sys
from pathlib import Path

LISTINGS_FILE = Path('listings.json')

OFFCYCLE_SEASONS = {
    'Co-op', 'Fall 2027', 'Spring 2027', 'Winter 2027',
    'Fall 2026', 'Spring 2026', 'Winter 2026', 'Summer 2026',
}
NEWGRAD_SEASON = '2027 (New Grad — no specific season)'

INTERN = re.compile(r'\bintern(ship)?\b', re.I)
STAFF_RS = re.compile(r'research scientist', re.I)
NEWGRAD_KW = re.compile(
    r'new grad|new-grad|entry[- ]level|early career|university grad|college grad|'
    r'graduate (quantitative|software|trader|developer|engineer|researcher)',
    re.I,
)
SUMMER_PROGRAM = re.compile(
    r'summer analyst|technology intern|leadership rotation|undergraduate student|'
    r'junior (quantitative|software|developer)',
    re.I,
)
SENIOR_PATTERNS = [
    re.compile(r'\bsenior\b', re.I),
    re.compile(r'\bstaff\b', re.I),
    re.compile(r'\bprincipal\b', re.I),
    re.compile(r'\bdirector\b', re.I),
    re.compile(r'\bmanager\b', re.I),
    re.compile(r'\blead\b(?!ership)', re.I),
    re.compile(r'\barchitect\b', re.I),
]
SENIOR_OK = re.compile(
    r'phd early career|senior associate|principal associate|associate product manager|\bapm\b',
    re.I,
)
NEWGRAD_IN_TITLE = re.compile(r'new grad|new-grad|entry', re.I)
RS_OK = re.compile(
    r'intern|new college grad|university grad|phd early career|new grad',
    re.I,
)


def validate_entry(entry):
    role = entry.get('role', '')
    t = role.lower()
    table = entry.get('type', '')
    season = entry.get('season', '')
    company = entry.get('company', '')
    violations = []

    if table == 'summer':
        if season != 'Summer 2027':
            violations.append(f'summer table but season={season!r}')
        if not INTERN.search(role) and not SUMMER_PROGRAM.search(role):
            if NEWGRAD_KW.search(role) or STAFF_RS.search(role):
                violations.append('summer but title looks like new grad or staff research scientist')
            elif re.search(r'\bassociate\b|\bgraduate\b|\bfull[- ]time\b', t) and 'intern' not in t:
                violations.append('summer but associate/graduate/full-time without intern')

    elif table == 'newgrad':
        if season != NEWGRAD_SEASON:
            violations.append(f'newgrad but season={season!r}')
        if INTERN.search(role) and not NEWGRAD_IN_TITLE.search(t):
            violations.append('newgrad but has intern in title without new-grad marker')
        for pat in SENIOR_PATTERNS:
            if pat.search(role) and not SENIOR_OK.search(role):
                violations.append(f'newgrad but senior title pattern: {pat.pattern}')
        if STAFF_RS.search(role) and not RS_OK.search(role):
            violations.append('newgrad staff research scientist (not entry-level)')

    elif table == 'offcycle':
        if season not in OFFCYCLE_SEASONS:
            violations.append(f'offcycle but season={season!r}')

    else:
        violations.append(f'unknown type={table!r}')

    return [(company, role, v) for v in violations]


def main():
    if not LISTINGS_FILE.exists():
        print(f'{LISTINGS_FILE} not found')
        sys.exit(1)

    with open(LISTINGS_FILE) as f:
        listings = json.load(f)

    all_violations = []
    for entry in listings:
        all_violations.extend(validate_entry(entry))

    print(f'Validated {len(listings)} listing(s)')
    if all_violations:
        print(f'Found {len(all_violations)} violation(s):')
        for company, role, reason in all_violations:
            print(f'  - {company}: {role!r} — {reason}')
        sys.exit(1)

    print('All listings pass constitution checks')
    sys.exit(0)


if __name__ == '__main__':
    main()
