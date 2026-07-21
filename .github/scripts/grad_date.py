#!/usr/bin/env python3
"""Infer expected graduation term from new-grad role title and URL."""

import re


def infer_grad_date(role, url=''):
    """Return a semester label (e.g. Spring 2027) or empty string if unknown."""
    role = (role or '').strip()
    url = (url or '').strip()
    blob = f'{role} {url}'.lower()

    m = re.search(r'\b(spring|fall|winter|summer|autumn)\s*(20\d{2})\b', blob, re.I)
    if m:
        return f'{m.group(1).title()} {m.group(2)}'

    m = re.search(r'\b(20\d{2})\s*(spring|fall|winter|summer|autumn)\b', blob, re.I)
    if m:
        return f'{m.group(2).title()} {m.group(1)}'

    title_patterns = [
        r'\b(20\d{2})\s+university\s+grad',
        r'university\s+grad(?:uate)?[- ]?(20\d{2})',
        r'university\s+graduate\s+(20\d{2})',
        r'new college grad(?:uate)?(?:\s|,|-)*(20\d{2})',
        r'new grad(?:uate)?\s*\(?\s*(20\d{2})\s*start',
        r'graduate program\s*[\(-]?\s*(20\d{2})',
        r'\b(20\d{2})\s+graduate program',
        r'\b(20\d{2})\s+early career\b',
        r'\bearly career\b.*\b(20\d{2})\b',
        r'\b(20\d{2})\s+graduate\b',
        r'campus full time\s+(20\d{2})',
        r'\b(20\d{2})\s+grads\b',
        r'\b(20\d{2})\s+phds?\b',
        r'\[(20\d{2})\]',
        r'^\s*\(?\[?(20\d{2})\]?[\)\s-]+',
    ]
    for pat in title_patterns:
        m = re.search(pat, role, re.I)
        if not m:
            m = re.search(pat, blob, re.I)
        if m:
            year = next(g for g in m.groups() if g)
            return f'Spring {year}'

    m = re.search(r'(20\d{2})[-_]us\b', url.lower())
    if m:
        return f'Spring {m.group(1)}'

    m = re.search(r'[-_/](20\d{2})[-_/]|[-_]us[-_](20\d{2})\b', url.lower())
    if m:
        year = next(g for g in m.groups() if g)
        if year and int(year) >= 2024:
            signals = (
                'new grad', 'university', 'college grad', 'early career',
                'graduate', 'campus full time',
            )
            if any(k in blob for k in signals):
                return f'Spring {year}'

    return ''
