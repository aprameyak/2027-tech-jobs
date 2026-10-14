"""Normalize sponsorship / citizenship values to the canonical vocabulary.

Canonical values:
  sponsorship: "Unknown" | "No — does NOT offer sponsorship" | "Yes — sponsorship available"
  citizenship: "Unknown" | "No" | "Yes — U.S. citizenship required"

Usage: python3 .github/scripts/normalize_sponsorship.py [--check]
"""
import json
import sys
from pathlib import Path

LISTINGS_FILE = Path('listings.json')

SPONSORSHIP_YES = 'Yes — sponsorship available'
SPONSORSHIP_NO = 'No — does NOT offer sponsorship'
CITIZENSHIP_YES = 'Yes — U.S. citizenship required'


def normalize_sponsorship(value):
    v = (value or '').strip().lower()
    if not v or v == 'unknown':
        return 'Unknown'
    if v.startswith(('no', 'not ')):
        return SPONSORSHIP_NO
    if v.startswith('yes'):
        return SPONSORSHIP_YES
    return 'Unknown'


def normalize_citizenship(value):
    v = (value or '').strip().lower()
    if not v or v == 'unknown':
        return 'Unknown'
    if v.startswith('yes'):
        return CITIZENSHIP_YES
    if v.startswith('no'):
        return 'No'
    return 'Unknown'


def normalize_entry(entry):
    """Normalize in place; return True if anything changed."""
    changed = False
    for key, fn in (('sponsorship', normalize_sponsorship), ('citizenship', normalize_citizenship)):
        if key in entry:
            new = fn(entry[key])
            if new != entry[key]:
                entry[key] = new
                changed = True
    return changed


def main():
    listings = json.loads(LISTINGS_FILE.read_text())
    changed = sum(normalize_entry(e) for e in listings)
    print(f'{changed} listing(s) normalized')
    if '--check' in sys.argv:
        sys.exit(1 if changed else 0)
    if changed:
        LISTINGS_FILE.write_text(json.dumps(listings, indent=2))


if __name__ == '__main__':
    main()
