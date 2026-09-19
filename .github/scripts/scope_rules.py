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
    'mechanical associate', 'radiation effects', 'assembly, integration',
    'postdoctoral', 'post-doctoral', 'postdoc fellow', 'post-doc',
]

# Soft hardware signals — reject unless title also has a strong SWE-adjacent keep signal
# (e.g. "Software Controls Engineer", "Thermal Controls Engineer, Vehicle Software").
_SOFT_HARDWARE_SIGNALS = [
    'controls engineer',
]

# SWE-adjacent keep signals — anything software / devops / technology related,
# plus AI, MLE, PM, consultant, and close neighbors.
# If present, do not reject solely for soft-hardware / ASIC org tokens.
_STRONG_KEEP = re.compile(
    r'\bsoftware\b|\bdevops\b|\btechnology\b|\btechnologies\b|\btechnologist\b|'
    r'\btech\b(?!\s*sales)|'
    r'\bswe\b|\bsde\b|\bsre\b|site reliability|'
    r'software\s*/\s*hardware|hardware\s*/\s*software|'
    r'machine learning|\bmle\b|ml engineer|ai engineer|artificial intelligence|'
    r'gen ai|genai|large language model|\bllm\b|applied science|'
    r'product manager|\bapm\b|associate product|'
    r'data scientist|data engineer|data science|data analyst|data analytics|'
    r'developer|programming|computer science|'
    r'technical consultant|technology consultant|solutions (engineer|consultant)|'
    r'technology consulting|it consultant|information technology|'
    r'quantitative (research|trad|develop|analy|technolog)|'
    r'cybersecurity|security engineer|cloud engineer|platform engineer|'
    r'backend|frontend|full-?stack',
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

# Intern / co-op / student / fellow signals (plurals included).
_INTERN_COOP = re.compile(
    r'\bintern(?:ships?|s)?\b|\bco-?ops?\b|\bcooperative\b|'
    r'summer analyst|summer associate|winter analyst|fall analyst|spring analyst|'
    r'analyst program|leadership rotation|'
    r'\bstudent\b|\bfellows?\b|\bfellowship\b',
    re.I,
)

# Explicit new-grad / early-career campus signals.
_NEWGRAD_MARKERS = re.compile(
    r'\bnew\s*grads?\b|\bnew-grads?\b|new college grads?|university grads?|college grads?|'
    r'entry[- ]level|early[- ]career|\bcampus\b|'
    r'\bgraduates?\b|\bgraduating\b|class of|university hire|college hire|'
    r'associate (?:software|engineer|developer|product|consultant|data|quantitative)|'
    r'software associate|engineer associate|'
    r'data science,? associate|cyber security specialist,? associate|'
    r'\bapm\b|principal associate|'
    r'(?:software )?(?:engineer|developer|sde)\s*[i1]\b|'
    r'junior (?:software|developer|engineer|quantitative|data)|'
    r'member of technical staff|ml technical staff|'
    r'technology (?:associate|analyst|development|developer)|'
    r'development program|rotational|emerging talent|'
    r'\b2027\b',
    re.I,
)

# Plain entry-level tech titles commonly posted without "New Grad" in the title.
_PLAIN_NEWGRAD_TITLE = re.compile(
    r'software engineer|software developer|software development|\bswe\b|\bsde\b|'
    r'machine learning|\bmle\b|ai engineer|data scientist|data engineer|data analyst|'
    r'quantitative|frontend|backend|full-?stack|devops|\bsre\b|site reliability|'
    r'security engineer|cloud engineer|platform engineer|solutions (?:engineer|consultant)|'
    r'technical consultant|technology consultant|cybersecurity analyst|'
    r'\bdeveloper\b|\bprogrammer\b|research engineer|research scientist|'
    r'product designer|design engineer',
    re.I,
)

_EXPERIENCED = re.compile(
    r'\b(senior|principal|director|architect)\b',
    re.I,
)
_STAFF_WORD = re.compile(r'\bstaff\b', re.I)
_MANAGER_WORD = re.compile(r'\bmanager\b', re.I)
_PM_TITLE = re.compile(
    r'\b(product manager|program manager|technical program manager|technical product manager)\b',
    re.I,
)
_EXPERIENCED_CAMPUS_OK = re.compile(
    r'new\s*grads?|new-grads?|new college|entry[- ]level|early[- ]career|phd early|'
    r'senior associate|principal associate|intern(?:ships?)?|co-?ops?|'
    r'member of technical staff|ml technical staff|associate product|\bapm\b',
    re.I,
)


def is_campus_role_title(title, table=None):
    """True only for intern, co-op, or new-grad / early-career style roles."""
    t = (title or '').strip()
    if not t:
        return False
    tl = t.lower()

    if _EXPERIENCED.search(tl) and not _EXPERIENCED_CAMPUS_OK.search(tl):
        return False
    if _STAFF_WORD.search(tl) and not _EXPERIENCED_CAMPUS_OK.search(tl):
        return False
    if _MANAGER_WORD.search(tl) and not _PM_TITLE.search(tl):
        if not _EXPERIENCED_CAMPUS_OK.search(tl) and not _INTERN_COOP.search(tl):
            return False

    # Startup "Founding *" roles are not campus new-grad / intern postings.
    if re.search(r'\bfounding\b', tl) and not (
        _NEWGRAD_MARKERS.search(tl) or _INTERN_COOP.search(tl)
    ):
        return False

    if _INTERN_COOP.search(tl):
        return True

    # Junior tech roles are entry-level / campus regardless of table.
    if re.search(r'\bjunior\b', tl) and re.search(
        r'software|engineer|developer|data|ml|ai|quant|security|cloud|devops|sre',
        tl,
    ):
        return True

    # Named early-career programs often omit "intern" / "new grad".
    if re.search(
        r'rotational|development program|amplify|new analyst|new professional|'
        r'career development|edison engineering|early talent|\bresident\b',
        tl,
    ):
        return True

    if _PM_TITLE.search(tl):
        # PM / TPM only when clearly campus (new grad, intern, 2027, associate, etc.)
        return bool(_NEWGRAD_MARKERS.search(tl) or _INTERN_COOP.search(tl))

    if table in ('summer', 'offcycle'):
        return False

    if table == 'newgrad':
        if _NEWGRAD_MARKERS.search(tl):
            return True
        return bool(_PLAIN_NEWGRAD_TITLE.search(tl))

    # No table (scraper pre-check): intern/coop or explicit new-grad markers only.
    return bool(_NEWGRAD_MARKERS.search(tl))


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
                'mechanical associate', 'radiation effects', 'assembly, integration',
                'postdoctoral', 'post-doctoral', 'postdoc fellow', 'post-doc',
            )
        ):
            return False
        return True

    if any(s in t for s in _SOFT_HARDWARE_SIGNALS) and not has_keep:
        return True

    if (_ASIC_RE.search(t) or _FPGA_RE.search(t)) and not has_keep:
        return True

    if re.search(r'\bpost-?docs?\b|\bpostdoctoral\b', t):
        return True
    if re.search(r'\bsales\b', t) and not re.search(
        r'software|solutions|developer|engineer|technology|technolog|devops',
        t,
    ):
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


def is_in_scope_listing_title(title, table=None):
    """Discipline + campus gate used by scraper and cleanup."""
    if is_out_of_scope_title(title):
        return False
    if not is_campus_role_title(title, table=table):
        return False
    # Intern / co-op / fellow / student: discipline gate is enough.
    if _INTERN_COOP.search(title or ''):
        return True
    # New-grad / early-career without intern wording: require a tech signal
    # (drops on-campus non-tech like video producer).
    if not re.search(
        r'software|developer|engineer|devops|technolog|technologist|\btech\b|'
        r'machine learning|\bml\b|\bai\b|artificial|gen\s*ai|deep learning|'
        r'data scien|data engineer|data analyst|data analytics|quant|'
        r'cyber|security|cloud|platform|backend|frontend|full-?stack|'
        r'product manag|product design|consultant|programming|computer|'
        r'research scientist|research engineer|\bsre\b|reliability|'
        r'network|systems|infrastructure|sdet|\bqa\b|compiler|'
        r'information technology|\bit\b|analytics|automation|'
        r'applied science|algorithm|\btrading\b',
        title or '',
        re.I,
    ):
        return False
    return True
