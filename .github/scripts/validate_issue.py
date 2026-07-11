#!/usr/bin/env python3

import os
import re
import sys

import requests

REQUIRED_FIELDS = [
    'Company Name',
    'Role / Job Title',
    'Listing Type',
    'Season / Term',
    'Location',
    'Direct Application Link',
]

VALID_LISTING_TYPES = [
    'Internship',
    'New Grad (Full-Time)',
    'Co-op',
]

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY', 'DC',
}

CA_PROVINCES = {
    'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT',
}

VALID_ABBRS = US_STATES | CA_PROVINCES

REMOTE_RE = re.compile(
    r'^remote\s*(\(us\)|\(canada\)|\(us/canada\)|\(north america\))?$',
    re.IGNORECASE,
)

CITY_STATE_RE = re.compile(r'^.+,\s*([A-Z]{2})$')


def validate_location(location):
    """Returns list of error strings, empty if valid."""
    parts = [p.strip() for p in location.split(';') if p.strip()]
    if not parts:
        return ['location is empty']
    errors = []
    for part in parts:
        if REMOTE_RE.match(part):
            continue
        m = CITY_STATE_RE.match(part)
        if not m:
            errors.append(
                f'`{part}` — use "City, ST" format (e.g. "San Francisco, CA") '
                f'or "Remote (US)" / "Remote (Canada)"'
            )
            continue
        abbr = m.group(1)
        if abbr not in VALID_ABBRS:
            errors.append(
                f'`{part}` — `{abbr}` is not a recognized US state or Canadian province code'
            )
    return errors


def parse_issue_body(body):
    fields = {}
    sections = re.split(r'^### ', body, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().split('\n')
        key = lines[0].strip()
        value = '\n'.join(lines[1:]).strip()
        if value == '_No response_':
            value = ''
        fields[key] = value
    return fields


def post_comment(token, repo, issue_number, body):
    requests.post(
        f'https://api.github.com/repos/{repo}/issues/{issue_number}/comments',
        headers={
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
        },
        json={'body': body},
        timeout=10,
    )


def main():
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    issue_number = os.environ.get('ISSUE_NUMBER')
    body = os.environ.get('ISSUE_BODY', '')

    if not body:
        print('No issue body — skipping validation')
        sys.exit(0)

    fields = parse_issue_body(body)
    errors = []

    for field in REQUIRED_FIELDS:
        if not fields.get(field, '').strip():
            errors.append(f'- **{field}** is missing or empty')

    apply_link = fields.get('Direct Application Link', '').strip()
    if apply_link and not apply_link.startswith('http'):
        errors.append('- **Direct Application Link** must be a valid URL starting with `http`')

    location = fields.get('Location', '').strip()
    if location:
        loc_errors = validate_location(location)
        for e in loc_errors:
            errors.append(f'- **Location**: {e}')

    if errors:
        comment = (
            'Thanks for the submission! A few things need to be fixed before this can be approved:\n\n'
            + '\n'.join(errors)
            + '\n\nPlease edit the issue to correct these and it will be reviewed.'
        )
        post_comment(token, repo, issue_number, comment)
        print(f'Validation failed: {len(errors)} error(s)')
    else:
        print('Validation passed')


if __name__ == '__main__':
    main()
