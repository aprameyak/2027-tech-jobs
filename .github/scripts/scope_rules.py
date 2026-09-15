#!/usr/bin/env python3

import re

HARD_REJECT_SIGNALS = [
    'manufacturing engineer', 'process engineer', 'chemical engineer',
    'mechanical engineer', 'materials engineer', 'materials scientist',
    'quality engineer', 'equipment engineer', 'industrial engineer',
    'environmental engineer', 'civil engineer', 'structural engineer',
    'electrical engineer', 'process integration', 'photolithography',
    'metrology', 'failure analysis', 'yield engineer', 'etch engineer',
    'human resources', 'recruiter', 'talent acquisition', 'peoplex',
    'people ops', 'people operations', 'people analytics', 'people partner',
    'supply chain', 'procurement',
    'legal intern', 'paralegal', 'accounting intern',
    'logistics', 'warehouse', 'shipping clerk', 'receiving clerk',
    'inventory management', 'inventory specialist', 'inventory analyst',
    'facilities manager', 'facilities engineer', 'facilities intern',
    'embedded software', 'embedded design', 'embedded engineer', 'embedded intern',
    'firmware engineer', 'firmware intern',
    'tax director', 'tax manager',
    'legal counsel', 'general counsel', 'legal operations',
    'digital marketing', 'product marketing', 'marketing intern', 'marketing co-op',
    'marketing co op', 'content marketing', 'brand marketing',
    'netsuite consulting', 'process risk and controls', 'risk and controls consulting',
    'sales intern', 'sales co-op', 'account executive', 'business development intern',
    'avionics systems', 'safety and reliability',
]

_SCOPE_TECH_HINT = re.compile(
    r'software|developer|programming|computer science|\bcs\b|data science|data engineer|'
    r'data analyst|data analytics|machine learning|\bml\b|\bai\b|artificial intelligence|'
    r'quantitative|quant|cyber|devops|sre|backend|frontend|full-?stack|platform engineer|'
    r'cloud engineer|information technology|\bit\b|security engineer|product manager|'
    r'product engineer|technology|\btech\b|technical program|business technology|'
    r'digital technology|\berp\b',
    re.I,
)


def is_out_of_scope_title(title):
    t = (title or '').lower()
    if not t:
        return True
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return True
    if re.search(r'research associate', t) and not _SCOPE_TECH_HINT.search(t):
        return True
    if re.search(r'\bsystems engineering\b', t):
        if not re.search(r'software|computer|cyber|digital|information technology|\bit\b', t):
            return True
    if re.search(r'\bbusiness analyst\b', t) and not _SCOPE_TECH_HINT.search(t):
        return True
    if re.search(r'\bconsulting intern\b|\bconsulting co-?op\b', t) and not _SCOPE_TECH_HINT.search(t):
        return True
    if re.search(r'\bmarketing\b', t) and not _SCOPE_TECH_HINT.search(t):
        return True
    if re.search(r'\b(people|hr)\b', t) and not _SCOPE_TECH_HINT.search(t):
        return True
    return False
