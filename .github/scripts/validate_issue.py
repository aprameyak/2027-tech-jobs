#!/usr/bin/env python3
"""
Validates a job listing issue submission and comments with any missing fields.
"""

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
