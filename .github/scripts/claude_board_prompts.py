#!/usr/bin/env python3
"""Board-specific Claude prompts for campus tech listing classification."""

# Shared discipline scope for all three boards.
_DISCIPLINE = (
    'IN-SCOPE disciplines only: software/SWE/SDE/developer, AI/ML/MLE, data science/'
    'data eng/analytics, quant research/trading/dev, product management (tech), '
    'technical/technology consulting, devops/SRE/cloud/platform, cybersecurity, '
    'IT/technology analyst or associate, solutions engineering. '
    'OUT-OF-SCOPE (always reject): hardware/ASIC/FPGA/RF/PCB, mechanical/electrical/'
    'civil/chemical/manufacturing/process/aerospace engineering, firmware/embedded, '
    'sales (non-solutions), marketing/HR/recruiting/legal/finance(non-quant), '
    'supply chain/logistics/warehouse, senior/staff/principal/director/manager '
    '(unless explicitly new-grad / PhD early career / Member of Technical Staff new grad), '
    'founding eng without campus markers, bare mid-level SWE/PM with no campus signal.'
)

_BOARD_RULES = {
    'summer': (
        'BOARD = Summer 2027 Internships ONLY.\n'
        'ACCEPT only if the title is clearly a Summer 2027 (or generic summer) '
        'internship / summer analyst / summer associate in an in-scope discipline.\n'
        'REJECT: co-ops, fall/spring/winter terms, full-time new-grad roles, '
        'fellowships without intern wording if they are year-round, senior roles, '
        'and anything not an internship.'
    ),
    'offcycle': (
        'BOARD = Off-Cycle Internships & Co-ops.\n'
        'ACCEPT: Fall/Spring/Winter internships, co-ops, fellows/student researcher/'
        'part-time student tech roles, and Summer 2026 internships still open — '
        'in-scope disciplines only.\n'
        'REJECT: Summer 2027 internships (those belong on summer), full-time new-grad '
        'roles, and out-of-scope disciplines.'
    ),
    'newgrad': (
        'BOARD = New Grad 2027 full-time entry-level ONLY.\n'
        'ACCEPT: new grad / university grad / college grad / early career / entry-level / '
        'campus hire / associate SWE or similar / Software Engineer I / junior tech / '
        'Member of Technical Staff (new grad) / graduate programs — in-scope disciplines.\n'
        'REJECT: internships, co-ops, mid-level or experienced SWE/PM without campus '
        'markers, senior/staff/director (unless PhD early career / MotS new grad), '
        'and out-of-scope disciplines.'
    ),
    'unknown': (
        'BOARD ROUTING — assign the best board or reject.\n'
        'summer = Summer 2027 internship / summer analyst.\n'
        'offcycle = co-op, fall/spring/winter intern, fellow/student role, Summer 2026.\n'
        'newgrad = full-time 2027 entry-level / early-career campus role.\n'
        'If it fits none, reject (t=0,a=0,b=x).'
    ),
}

_BOARD_TOKEN = {
    'summer': 's',
    'offcycle': 'o',
    'newgrad': 'n',
    'unknown': 's|o|n|x',
}


def build_classify_prompt(titles, board='unknown'):
    """Build a compact Claude prompt for a batch of job titles.

    board: summer | offcycle | newgrad | unknown
    Returns JSON schema instruction expecting per-title
    {"t":0|1,"c":"h"|"m"|"l","a":0|1,"b":"s"|"o"|"n"|"x"}
    """
    board = board if board in _BOARD_RULES else 'unknown'
    n = len(titles)
    numbered = '\n'.join(
        f'{i + 1}. {titles[i]}' for i in range(n)
    )
    b_token = _BOARD_TOKEN[board]
    board_lock = (
        f'For this batch every accepted row MUST use b="{_BOARD_TOKEN[board]}" '
        f'(this batch is pre-filtered for the {board} board). '
        f'Use b="x" only when rejecting.'
        if board != 'unknown'
        else 'Set b to s (summer), o (offcycle), n (newgrad), or x (reject/none).'
    )

    return (
        f'You classify titles for a US/Canada 2027 tech campus job board.\n'
        f'{_DISCIPLINE}\n\n'
        f'{_BOARD_RULES[board]}\n\n'
        f'{board_lock}\n'
        f'Return a JSON array of length {n} in the same order. '
        f'Each element: {{"t":0|1,"c":"h"|"m"|"l","a":0|1,"b":"{b_token}"}}.\n'
        f't=1 if in-scope discipline. a=1 only if t=1 AND it belongs on this board '
        f'(campus intern/co-op/new-grad as defined above). '
        f'c=h high confidence, m medium, l low/unsure.\n'
        f'Be strict: when unsure, prefer t=0 or a=0.\n'
        f'Titles:\n{numbered}\n'
        f'JSON only — no markdown, no commentary.'
    )


def build_triage_prompt(lines, n):
    """Prompt for GitHub issue triage (add/reject/skip) with board-aware seasons."""
    return (
        f'Triage {n} GitHub listing issues for a US/Canada 2027 tech campus board '
        f'with three tables: summer internships, off-cycle/co-op, and new-grad.\n'
        f'{_DISCIPLINE}\n'
        f'Summer = Summer 2027 internship only. '
        f'Off-cycle = co-op / fall / spring / winter / fellow / Summer 2026. '
        f'New grad = full-time 2027 entry-level / early career only.\n'
        f'Return JSON array length {n}, same order. Each object:\n'
        '{"action":"add"|"reject"|"skip","reason":"short",'
        '"company":"","role":"",'
        '"type":"Internship"|"New Grad (Full-Time)",'
        '"season":"Summer 2027"|"Co-op"|"Fall 2026"|"Fall 2027"|"Spring 2027"|'
        '"Winter 2027"|"Summer 2026"|"2027 (New Grad — no specific season)",'
        '"location":"City, ST","education":"Undergrad"|"Masters"|"PhD"|'
        '"Undergrad; Masters"|"Undergrad; PhD"|"Masters; PhD"|"Undergrad; Masters; PhD",'
        '"citizenship":"Unknown"|"Yes — U.S. citizenship required",'
        '"sponsorship":"Unknown"|"No — sponsorship not offered"}\n'
        'For Internship + Summer 2027 → summer table. '
        'For Internship + co-op/fall/spring/winter/Summer 2026 → offcycle. '
        'For New Grad (Full-Time) → newgrad season '
        '"2027 (New Grad — no specific season)".\n'
        'add = in-scope campus role for the correct board. '
        'reject = out-of-scope / senior / international-only / hardware. '
        'skip = unclear.\n'
        + '\n'.join(lines)
        + '\nJSON only.'
    )


def board_token_to_table(token):
    return {
        's': 'summer',
        'o': 'offcycle',
        'n': 'newgrad',
    }.get((token or '').lower().strip())
