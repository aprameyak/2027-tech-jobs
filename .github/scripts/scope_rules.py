#!/usr/bin/env python3

import re

# Always out — non-tech / hardware / non-SWE-adjacent disciplines.
# Do NOT put short tokens like "asic" here (substring traps); those use word-boundary checks below.
HARD_REJECT_SIGNALS = [
    'manufacturing engineer', 'process engineer', 'chemical engineer',
    'mechanical engineer', 'mechanical design', 'materials engineer', 'materials scientist',
    'quality engineer', 'production quality', 'equipment engineer', 'industrial engineer',
    'environmental engineer', 'civil engineer', 'structural engineer',
    'electrical engineer', 'electrical design', 'electrical hardware',
    'process integration', 'photolithography',
    'metrology', 'failure analysis', 'yield engineer', 'etch engineer', 'wet etch',
    'tooling engineer', 'tooling intern', 'heat transfer', 'thermodynamic',
    'controls engineering',
    'hardware engineer', 'hardware design', 'hardware intern', 'hardware r&d',
    'hardware systems', 'digital hardware', 'rtl design',
    'rf engineer', 'rf design', 'antenna design', 'pcb design',
    'human resources', 'recruiter', 'recruiting', 'talent acquisition', 'peoplex',
    'people ops', 'people operations', 'people analytics', 'people partner',
    'supply chain', 'procurement',
    'legal intern', 'paralegal', 'accounting intern',
    'logistics', 'warehouse', 'shipping clerk', 'receiving clerk',
    'inventory management', 'inventory specialist', 'inventory analyst',
    'facilities manager', 'facilities engineer', 'facilities intern',
    'embedded software', 'embedded design', 'embedded engineer', 'embedded intern',
    'firmware engineer', 'firmware intern', 'ssd firmware',
    'tax director', 'tax manager',
    'legal counsel', 'general counsel', 'legal operations',
    'digital marketing', 'product marketing', 'marketing intern', 'marketing co-op',
    'marketing co op', 'content marketing', 'brand marketing',
    'netsuite consulting', 'process risk and controls', 'risk and controls consulting',
    'sales intern', 'sales co-op', 'sales engineer', 'sales & relationship',
    'account executive', 'business development intern',
    'avionics systems', 'safety and reliability',
    'wealth management products', 'infrastructure equity',
    'aerospace engineering', 'product design engineering',
]

# Soft hardware signals — reject unless title also has a strong SWE-adjacent keep signal
# (e.g. "Software Controls Engineer", "Thermal Controls Engineer, Vehicle Software").
_SOFT_HARDWARE_SIGNALS = [
    'controls engineer',
]

# SWE-adjacent keep signals — SWE, AI, MLE, PM, consultant, and close neighbors.
# If present, do not reject solely for soft-hardware / ASIC org tokens.
_STRONG_KEEP = re.compile(
    r'software engineer|software developer|software development|\bswe\b|\bsde\b|'
    r'software\s*/\s*hardware|hardware\s*/\s*software|'
    r'software controls|vehicle software|'
    r'machine learning|\bmle\b|ml engineer|ai engineer|artificial intelligence|'
    r'gen ai|large language model|\bllm\b|applied science|'
    r'product manager|\bapm\b|associate product|'
    r'data scientist|data engineer|data science|'
    r'technical consultant|technology consultant|solutions (engineer|consultant)|'
    r'technology consulting|it consultant|'
    r'quantitative (research|trad|develop|analy)|'
    r'cybersecurity|security engineer|devops|site reliability',
    re.I,
)

_SCOPE_TECH_HINT = re.compile(
    r'software|developer|programming|computer science|\bcs\b|data science|data engineer|'
    r'data analyst|data analytics|machine learning|\bml\b|\bai\b|artificial intelligence|'
    r'quantitative|quant|cyber|devops|sre|backend|frontend|full-?stack|platform engineer|'
    r'cloud engineer|information technology|\bit\b|security engineer|product manager|'
    r'product engineer|technology|\btech\b|technical program|business technology|'
    r'digital technology|\berp\b|consultant|consulting',
    re.I,
)

# Word-boundary hardware tokens (avoid matching "basic", "applied science", etc.)
_ASIC_RE = re.compile(r'\basics?\b', re.I)
_FPGA_RE = re.compile(r'\bfpga\b', re.I)


def is_out_of_scope_title(title):
    t = (title or '').lower()
    if not t:
        return True

    has_keep = bool(_STRONG_KEEP.search(t))

    if any(s in t for s in HARD_REJECT_SIGNALS):
        # Mixed titles like "Software / Hardware Engineering" stay in if SWE-primary.
        if has_keep and not any(
            s in t
            for s in (
                'embedded software', 'embedded engineer', 'firmware engineer',
                'firmware intern', 'ssd firmware', 'mechanical engineer',
                'mechanical design', 'electrical engineer', 'electrical design',
                'electrical hardware', 'manufacturing engineer',
            )
        ):
            return False
        return True

    if any(s in t for s in _SOFT_HARDWARE_SIGNALS) and not has_keep:
        return True

    if (_ASIC_RE.search(t) or _FPGA_RE.search(t)) and not has_keep:
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
