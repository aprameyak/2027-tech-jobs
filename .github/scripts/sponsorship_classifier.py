"""Token-efficient visa sponsorship / citizenship classification inputs for Claude.

Only the few sentences of a posting that mention visas, work authorization,
citizenship or clearance are sent to Claude. Postings with no such sentence
are never sent (they stay Unknown), so most listings cost zero tokens.
"""
import html as _html
import json
import re

_KEYWORDS = re.compile(
    r'sponsor|visa|work authori[sz]ation|authori[sz]ed to work|legally (?:authori[sz]ed|eligible)|'
    r'right to work|citizen|security clearance|\bclearance\b|\bitar\b|export control|\bh-?1b\b|\bopt\b|\bcpt\b',
    re.I,
)
MAX_SNIPPET_CHARS = 400
MAX_SNIPPETS = 3


def html_to_text(raw):
    text = _html.unescape(raw or '')
    text = re.sub(r'<(?:br|/p|/li|/div|/h\d)\s*/?>', '. ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_visa_snippets(text):
    """Return a short string of the sentences that mention visa/citizenship, or ''."""
    if not text:
        return ''
    picked = []
    text = re.sub(r'\s+', ' ', re.sub(r'\bU\.S\.', 'US', text))
    for sent in re.split(r'(?<=[.!?])\s+', text):
        if _KEYWORDS.search(sent):
            picked.append(sent.strip()[:MAX_SNIPPET_CHARS])
            if len(picked) >= MAX_SNIPPETS:
                break
    return ' | '.join(picked)


def build_sponsorship_prompt(snippets):
    rows = '\n'.join(f'{i}. {s}' for i, s in enumerate(snippets))
    return (
        'For each job-posting excerpt, decide two things.\n'
        's = visa sponsorship: "n" if the posting says it will NOT sponsor / requires existing work '
        'authorization without sponsorship (also if clearance/citizenship makes sponsorship impossible); '
        '"y" if it explicitly offers sponsorship; "u" if the excerpt does not say.\n'
        'c = U.S. citizenship: "y" only if U.S. citizenship (or an active clearance requiring it) is '
        'required; "n" otherwise.\n'
        'Judge only from the excerpt. Reply with ONLY a JSON array of '
        f'{len(snippets)} objects like {{"s":"n","c":"n"}}, in order, no extra text.\n\n{rows}'
    )


def parse_sponsorship_response(text, n):
    """Parse Claude's reply into n (sponsorship, citizenship) tuples; None on malformed output."""
    text = (text or '').strip()
    start, end = text.find('['), text.rfind(']')
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list) or len(raw) != n:
        return None
    out = []
    for row in raw:
        row = row if isinstance(row, dict) else {}
        s = {'n': 'No — does NOT offer sponsorship', 'y': 'Yes — sponsorship available'}.get(
            str(row.get('s', '')).lower(), 'Unknown')
        c = 'Yes — U.S. citizenship required' if str(row.get('c', '')).lower() == 'y' else None
        out.append((s, c))
    return out
