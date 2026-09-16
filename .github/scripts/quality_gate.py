#!/usr/bin/env python3
"""Regression / quality gate for listings.json + table markdown.

Fails (exit 1) on:
  - invalid JSON / constitution validator failures (caller may also run validate_listings.py)
  - README table count drift vs listings.json
  - polluted location HTML in listings.json
  - third-party tracking slugs / non-aprameyak utm_source on live URLs
  - live international (UK/etc.) locations
  - duplicate live URLs (normalized)
  - missing must-live markers (high-signal roles that must stay open)

Warnings (printed, non-fatal): imperfect live locations (e.g. state-only).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[2]
LISTINGS_FILE = ROOT / 'listings.json'
TABLE_FILES = {
    'summer': ROOT / 'SUMMER.md',
    'offcycle': ROOT / 'OFFCYCLE.md',
    'newgrad': ROOT / 'NEWGRAD.md',
}

VALID_EDU = {'Undergrad', 'Masters', 'PhD'}
ABBR = set(
    'AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO '
    'MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC '
    'AB BC MB NB NL NS NT NU ON PE QC SK YT PR'.split()
)
ATS = re.compile(r'greenhouse|lever\.co|ashby|workday', re.I)
THIRD_PARTY = re.compile(
    r'ref=vansh|gh_src=|lever-source=|ref=Simplify|utm_source=(?!aprameyak)',
)
INTL = re.compile(r'(?i),\s*UK\b|United Kingdom|\bLondon,\s*UK\b')
STRIP = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id',
    'source', 'src', 'ref', 'referer', 'lever-source', 'lever-origin', 'gh_src', 'simplify',
}

# High-signal listings that must remain live (matched by unique URL fragment).
MUST_LIVE = [
    ('DoorDash US intern', '8171041'),
    ('DoorDash TOR intern', '8170944'),
    ('Waymo Commercialization intern', '8198218'),
    ('Apple undergrad internships', '200664785'),
    ('Apple masters internships', '200664320'),
    ('Atlassian Canada intern', '26275'),
    ('Adobe SWE intern', 'R171666'),
    ('Capital One AI PhD intern', 'R249110'),
    ('Capital One AI Masters intern', 'R249109'),
]


def normalize_url(url: str) -> str:
    if not url:
        return ''
    p = urlparse(url.strip())
    params = {
        k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
        if k.lower() not in STRIP
    }
    u = urlunparse(p._replace(
        scheme=(p.scheme or 'https').lower(),
        netloc=p.netloc.lower(),
        query=urlencode(sorted(params.items()), doseq=True),
        fragment='',
    ))
    u = re.sub(r'(myworkdayjobs\.com)/en-[A-Z]{2}/[^/]+/job/', r'\1/BOARD/job/', u)
    return u.lower().rstrip('/')


def loc_ok(loc: str) -> bool:
    parts = [p.strip() for p in loc.split(';') if p.strip()]
    if not parts:
        return False
    for p in parts:
        if re.match(r'(?i)^Remote\s*\((US|Canada)\)$', p):
            continue
        m = re.search(r',\s*([A-Z]{2})$', p)
        if not m or m.group(1) not in ABBR:
            return False
    return True


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    listings = json.loads(LISTINGS_FILE.read_text())

    for name, marker in MUST_LIVE:
        hits = [e for e in listings if marker in (e.get('url') or '')]
        if len(hits) != 1:
            errors.append(f'must-live {name}: expected 1 live hit with {marker!r}, got {len(hits)}')
        elif not hits[0].get('url'):
            errors.append(f'must-live {name}: URL empty (closed regression)')

    for t, path in TABLE_FILES.items():
        text = path.read_text()
        m = re.search(r'(\d+) listing', text)
        header = int(m.group(1)) if m else -1
        count = sum(1 for e in listings if e.get('type') == t)
        if header != count:
            errors.append(f'{path.name} count mismatch: header={header} json={count}')

    seen: dict[str, dict] = {}
    for e in listings:
        edu = e.get('education', '')
        if not edu or any(v not in VALID_EDU for v in edu.split('; ')):
            errors.append(f'bad education: {e.get("company")} / {edu!r}')
        if e.get('type') == 'summer' and e.get('season') != 'Summer 2027':
            errors.append(f'summer wrong season: {e.get("company")} / {e.get("season")}')
        if e.get('type') == 'offcycle' and not str(e.get('season', '')).strip():
            errors.append(f'offcycle missing season: {e.get("company")} / {e.get("role")}')

        loc = e.get('location', '')
        if '<details' in loc or (loc.startswith('**') and 'locations' in loc):
            errors.append(f'polluted location: {e.get("company")} / {loc[:80]!r}')

        url = e.get('url') or ''
        if not url:
            continue
        if THIRD_PARTY.search(url):
            errors.append(f'third-party slug: {e.get("company")} / {url[:100]}')
        if ATS.search(url) and 'utm_source' not in url:
            warnings.append(f'missing utm on ATS URL: {e.get("company")}')
        if INTL.search(loc):
            errors.append(f'international live location: {e.get("company")} / {loc}')
        if not loc_ok(loc):
            warnings.append(f'imperfect live location: {e.get("company")} / {loc}')

        n = normalize_url(url)
        if n in seen:
            a = seen[n]
            errors.append(
                f'URL duplicate: {a.get("company")}/{a.get("role")} vs '
                f'{e.get("company")}/{e.get("role")}'
            )
        else:
            seen[n] = e

    # DoorDash education invariant for the two live summer roles
    for e in listings:
        if e.get('company') != 'DoorDash' or not e.get('url'):
            continue
        if '8171041' in e['url'] or '8170944' in e['url']:
            if e.get('education') != 'Undergrad; Masters':
                errors.append(
                    f'DoorDash education regression: {e.get("role")} -> {e.get("education")}'
                )

    print(f'Checked {len(listings)} listings '
          f'({sum(1 for e in listings if e.get("url"))} live)')
    print(f'Errors: {len(errors)}  Warnings: {len(warnings)}')
    for msg in errors:
        print(f'  ERROR: {msg}')
    for msg in warnings[:25]:
        print(f'  WARN: {msg}')
    if len(warnings) > 25:
        print(f'  WARN: ... +{len(warnings) - 25} more')

    if errors:
        print('QUALITY GATE: FAIL')
        return 1
    print('QUALITY GATE: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
