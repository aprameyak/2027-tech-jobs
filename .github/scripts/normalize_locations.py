import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

LISTINGS_FILE = Path('listings.json')

STATES = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA',
    'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
    'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS',
    'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK',
    'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
    'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI',
    'Wyoming': 'WY', 'District of Columbia': 'DC', 'Puerto Rico': 'PR',
}
PROVINCES = {
    'Alberta': 'AB', 'British Columbia': 'BC', 'Manitoba': 'MB', 'New Brunswick': 'NB',
    'Newfoundland and Labrador': 'NL', 'Nova Scotia': 'NS', 'Northwest Territories': 'NT',
    'Nunavut': 'NU', 'Ontario': 'ON', 'Prince Edward Island': 'PE', 'Quebec': 'QC',
    'Saskatchewan': 'SK', 'Yukon': 'YT',
}
ABBRS = set(STATES.values()) | set(PROVINCES.values()) | {'UK'}
NAME_TO_ABBR = {n.lower(): a for n, a in {**STATES, **PROVINCES}.items()}
NAME_TO_ABBR['ont'] = 'ON'
NAME_TO_ABBR['d.c.'] = 'DC'


CITY_ALIASES = {
    'nyc': 'New York, NY', 'new york city': 'New York, NY', 'new york': 'New York, NY',
    'ny': 'New York, NY', 'sf': 'San Francisco, CA', 'san francisco': 'San Francisco, CA',
    'la': 'Los Angeles, CA', 'los angeles': 'Los Angeles, CA', 'dc': 'Washington, DC',
    'washington dc': 'Washington, DC', 'washington d.c.': 'Washington, DC',
    'seattle': 'Seattle, WA', 'boston': 'Boston, MA', 'austin': 'Austin, TX',
    'chicago': 'Chicago, IL', 'denver': 'Denver, CO', 'atlanta': 'Atlanta, GA',
    'houston': 'Houston, TX', 'dallas': 'Dallas, TX', 'toronto': 'Toronto, ON',
    'vancouver': 'Vancouver, BC', 'montreal': 'Montreal, QC', 'ottawa': 'Ottawa, ON',
    'waterloo': 'Waterloo, ON', 'san jose': 'San Jose, CA', 'san diego': 'San Diego, CA',
    'palo alto': 'Palo Alto, CA', 'mountain view': 'Mountain View, CA',
    'sunnyvale': 'Sunnyvale, CA', 'menlo park': 'Menlo Park, CA', 'redmond': 'Redmond, WA',
    'bellevue': 'Bellevue, WA', 'pittsburgh': 'Pittsburgh, PA', 'philadelphia': 'Philadelphia, PA',
    'brooklyn': 'Brooklyn, NY', 'minneapolis': 'Minneapolis, MN', 'miami': 'Miami, FL',
    'phoenix': 'Phoenix, AZ', 'raleigh': 'Raleigh, NC', 'durham': 'Durham, NC',
    'cambridge': 'Cambridge, MA', 'boulder': 'Boulder, CO', 'detroit': 'Detroit, MI',
    'salt lake city': 'Salt Lake City, UT', 'santa clara': 'Santa Clara, CA',
    'mississauga': 'Mississauga, ON', 'brampton': 'Brampton, ON', 'markham': 'Markham, ON',
    'kitchener': 'Kitchener, ON', 'calgary': 'Calgary, AB', 'edmonton': 'Edmonton, AB',
    'burnaby': 'Burnaby, BC', 'san francisco bay area': 'San Francisco, CA',
    'south sf': 'South San Francisco, CA', 'south san francisco': 'South San Francisco, CA', 'greater chicago area': 'Chicago, IL',
    'los angeles - greater area': 'Los Angeles, CA', 'redwood city': 'Redwood City, CA',
}
ALIAS_TOKENS = ('NYC', 'SF', 'LA', 'DC')

COUNTRY_TAIL = re.compile(
    r'[,\s]+(?:United States of America|United States|USA|US|Canada|CAN)\s*$', re.I)
COUNTRY_TOKENS = {'us', 'usa', 'united states', 'united states of america', 'canada', 'can'}
NOISE = re.compile(
    r'\b(?:HQ|Headquarters|Main Site|Main Office|Head Office|Office|Campus|Corporate)\b', re.I)


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def _state(tok):
    tok = tok.strip().rstrip('.')
    if tok.upper() in ABBRS and (tok.isupper() or len(tok) == 2):
        return tok.upper()
    return NAME_TO_ABBR.get(tok.lower())


def _split_glued(s):
    s = re.sub(r'(Canada|USA|United States)(?=[A-Z][a-z])', r'\1|', s)
    s = re.sub(rf'(,\s*[A-Z]{{2}})\s+(?=(?:{"|".join(ALIAS_TOKENS)})\b)', r'\1|', s)
    s = re.sub(rf'(,\s*[A-Z]{{2}})(?=[A-Z][a-z]|{"|".join(ALIAS_TOKENS)})', r'\1|', s)
    parts = []
    for p in s.split('|'):
        p = p.strip()
        if re.fullmatch(rf'(?:{"|".join(ALIAS_TOKENS)})+', p):
            parts.extend(re.findall('|'.join(ALIAS_TOKENS), p))
            continue
        m = re.match(rf'^((?:{"|".join(ALIAS_TOKENS)})+)(?=[A-Z][a-z])(.*)$', p)
        if m:
            parts.extend(re.findall('|'.join(ALIAS_TOKENS), m.group(1)))
            parts.append(m.group(2))
            continue

        parts.append(p)
    return [p for p in parts if p]


STREET = re.compile(
    r'^.*\b(?:Pkwy|Blvd|Ave|Rd|Dr|St|Street|Avenue|Road|Drive|Way|Hwy|Ln|Ct|Pl|Floor)\.?\s+', re.I)


def _clean_city(city):
    if city[:1].isdigit():
        city = STREET.sub('', city)
    city = re.sub(r'\([^)]*\)', '', city)
    city = NOISE.sub('', city)
    city = re.sub(r'\b\d[\w-]*\b', '', city)
    city = re.sub(r'\s+', ' ', city).strip(' -–,')
    return city


def _normalize_part(p):
    p = _strip_accents(p).strip()
    if not p:
        return None


    p = re.sub(r'\s*\((?!\s*(?:US|USA|Canada)\s*\))[^)]*\)', '', p)
    p = re.sub(r'\s*\+\d+\b', '', p)
    if not re.match(r'(?i)remote', p):
        p = re.sub(r'\s*\(\s*(?:USA|US)\s*\)\s*$', '', p)
    p = re.sub(r'\b\d{5}(?:-\d{4})?\b', '', p)
    p = NOISE.sub('', p)
    p = re.sub(r'\bHub\b', '', p, flags=re.I)
    p = re.sub(r'\s+', ' ', p).strip(' -–,')
    if not p:
        return None
    low = p.lower()

    if low in ('united states', 'united states of america', 'usa', 'us', 'u.s.'):
        return 'Remote (US)'
    if low in ('canada', 'can'):
        return 'Remote (Canada)'

    if re.search(r'\b(?:or|and|within)\b', p):
        return None

    if re.search(r'\bremote\b', low):
        rest = re.sub(r'(?i)\bremote\b(?:\s+work)?(?:\s+in)?', '', p).strip(' ,-–()')
        rl = rest.lower().replace('.', '')
        if rl in ('', 'in', 'us', 'usa', 'united states') or _state(rest):
            return 'Remote (Canada)' if 'canada' in low else 'Remote (US)'
        if rl == 'canada':
            return 'Remote (Canada)'
        p = rest

    p = re.sub(r'^(?:hybrid|onsite|on-site)\s*[-–:]\s*', '', p, flags=re.I)
    p = re.sub(r'^office\s*[-–:]\s*', '', p, flags=re.I)

    if '~' in p:
        m = re.match(r'^([^~]+?)(?:-[\w-]+)?\s*~.*,\s*([A-Z]{2})\s*$', p)
        if m and m.group(2) in ABBRS:
            city = re.sub(r'^Ft\b', 'Fort', m.group(1).strip().title())
            return f'{city}, {m.group(2)}'

    m = re.match(r"^([A-Za-z .']+?)-\d.*,\s*([A-Z]{2})$", p)
    if m and m.group(2) in ABBRS:
        return f'{m.group(1).strip().title()}, {m.group(2)}'


    if ',' not in p and ' - ' not in p and re.search(r'[A-Za-z][-.][A-Za-z]', p):
        segs = [x.strip() for x in re.split(r'[-.]', p) if x.strip()]
        while segs and segs[0].lower() in COUNTRY_TOKENS | {'ca'} and len(segs) > 1:
            if segs[0].lower() == 'ca' and _state(segs[1]) not in PROVINCES.values():
                break
            segs = segs[1:]
        if len(segs) >= 2 and _state(segs[0]):
            return f'{segs[1].title()}, {_state(segs[0])}'

    p = COUNTRY_TAIL.sub('', p).strip(' -–,')
    country_led = bool(re.match(r'^(?:United States of America|United States|USA|US|Canada)\b', p))
    p = re.sub(r'^(?:United States of America|United States|USA|US|Canada)\b[\s,-]*', '', p)


    m = re.match(r'^([A-Za-z .\']+?)\s+([A-Z]{2})$', p)
    if m and m.group(2) in ABBRS and len(m.group(1).split()) <= 3 and not _state(m.group(1)):
        p = f'{m.group(1)}, {m.group(2)}'

    alias = CITY_ALIASES.get(_clean_city(p).lower())
    if alias:
        return alias

    tokens = [t.strip() for t in re.split(r',|\s[-–]\s', p) if t.strip()]
    tokens = [t for t in tokens if t.lower() not in COUNTRY_TOKENS]

    if len(tokens) >= 2 and tokens[0].upper() in ('CA', 'CAN') and _state(tokens[1]) in PROVINCES.values():
        tokens = tokens[1:]
    if len(tokens) >= 2 and tokens[-1].upper() == 'CA' and _state(tokens[-2]) in PROVINCES.values():
        tokens = tokens[:-1]

    state_idx = [i for i, t in enumerate(tokens) if _state(t)]
    if not state_idx:

        if tokens and CITY_ALIASES.get(tokens[0].lower()) and re.search(r'\s[-–]\s', p):
            return CITY_ALIASES[tokens[0].lower()]

        if len(tokens) > 1 and all(CITY_ALIASES.get(t.lower()) for t in tokens):
            return '; '.join(CITY_ALIASES[t.lower()] for t in tokens)
        return None
    if len(state_idx) >= 2 and state_idx[0] == 1 and all(
            b - a == 2 for a, b in zip(state_idx, state_idx[1:])):
        pairs = [_normalize_part(f'{tokens[i - 1]}, {tokens[i]}') for i in state_idx]
        if all(pairs):
            return '; '.join(pairs)
    if country_led and _state(tokens[0]) and len(tokens) > 1:
        idx = 0
    elif state_idx == [0] and len(tokens) > 1:
        idx = 0
    else:
        idx = state_idx[-1]
    st = _state(tokens[idx])
    if idx == 0:
        if len(tokens) < 2:
            return None
        city = tokens[1]
    else:
        city = tokens[0]
        if (city.lower().endswith(' county') or city[:1].isdigit()) and idx >= 2:
            city = tokens[idx - 1]
    city = _clean_city(city)
    if not city or (city.upper() == st and len(city) == 2):
        return None
    if city.lower() in ('nyc', 'new york city'):
        return 'New York, NY'
    return f'{city}, {st}'


def normalize_location(loc):
    if not loc or not loc.strip():
        return loc, False
    pieces = []
    loc = re.sub(r'^\d+\s+locations?\s*', '', loc.strip(), flags=re.I)
    loc = re.sub(r'(\d\s*(?:NE|NW|SE|SW));', r'\1', loc)
    for chunk in re.split(r';|\n|\s+or\s+(?=[^,;]+,\s*[A-Z]{2}\b)', loc):
        pieces.extend(_split_glued(chunk.strip()))
    out, ok = [], True
    for p in pieces:
        n = _normalize_part(p)
        if n is None:
            ok = False
            n = p.strip()
        if n not in out:
            out.append(n)
    return '; '.join(out), ok


def is_clean(loc):
    parts = [p.strip() for p in loc.split(';') if p.strip()]
    return bool(parts) and all(
        re.fullmatch(r'Remote \((?:US|Canada)\)', p)
        or (re.fullmatch(r"[^,;]+, [A-Z]{2}", p) and p[-2:] in ABBRS)
        for p in parts)


def clean_location(loc):
    new, ok = normalize_location(loc)
    return new if ok and is_clean(new) else loc


def main():
    apply = '--apply' in sys.argv
    listings = json.loads(LISTINGS_FILE.read_text())
    changed, unresolved = Counter(), Counter()
    for e in listings:
        old = e['location']
        new, ok = normalize_location(old)
        if not ok or not is_clean(new):
            unresolved[(old, new)] += 1
        if new != old:
            changed[(old, new)] += 1
            if apply and ok and is_clean(new):
                e['location'] = new
    print(f'{sum(changed.values())} rows would change ({len(changed)} distinct values)')
    for (o, n), c in changed.most_common(400):
        print(f'  {c:>4}  {o!r} -> {n!r}')
    print(f'\n{sum(unresolved.values())} rows still unresolved ({len(unresolved)} distinct):')
    for (o, n), c in unresolved.most_common(200):
        print(f'  {c:>4}  {o!r}')
    if apply:
        LISTINGS_FILE.write_text(json.dumps(listings, indent=2))
        print('\nlistings.json updated (only fully resolved values were rewritten)')


if __name__ == '__main__':
    main()
