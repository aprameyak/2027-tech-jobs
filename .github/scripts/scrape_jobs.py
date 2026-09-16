#!/usr/bin/env python3

import json
import os
import re
import subprocess
import time
import html as _html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import anthropic
import requests
import yaml
from pathlib import Path

import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from grad_date import infer_grad_date
from validate_listings import validate_entry
from scope_rules import HARD_REJECT_SIGNALS, is_out_of_scope_title

BOARD_GROUP = os.environ.get('BOARD_GROUP', '').strip()

_seen_jobs_filename = f'seen_jobs_{BOARD_GROUP}.json' if BOARD_GROUP else 'seen_jobs.json'
SEEN_JOBS_FILE = Path(f'.github/data/{_seen_jobs_filename}')
PENDING_FILE = Path(f'.github/data/pending_{BOARD_GROUP}.json') if BOARD_GROUP else None
TITLE_CACHE_FILE = Path('.github/data/title_classifications.json')
                                                                                     
CLAUDE_USAGE_FILE = (
    Path(f'.github/data/claude_usage_{BOARD_GROUP}.json')
    if BOARD_GROUP else Path('.github/data/claude_usage.json')
)
FOLLOWED_COMPANIES_FILE = Path('.github/data/followed_companies.json')

CLAUDE_MODEL = 'claude-haiku-4-5-20251001'
CLAUDE_BATCH_SIZE = 120
TITLE_PROMPT_MAX_LEN = 80
_claude_client = None
_claude_usage_dirty = False

MAX_WORKDAY_PAGES_PER_TERM = 15
MAX_ORACLE_PAGES_PER_TERM = 20
ORACLE_PAGE_SIZE = 50
ORACLE_SEARCH_TERMS = (
    '2027', 'Intern', 'Internship', 'Campus', 'Graduate', 'New Grad',
    'Analyst Program', 'co-op', 'university', 'entry level', 'early career',
)
SCRAPER_MAX_WORKERS = 12

_title_cache = None
_confidence_cache = {}
_add_cache = {}
_claude_calls_today = 0
_claude_usage_date = None

DEFAULT_FOLLOWED_COMPANIES = [
    'Amazon',
    'Apple',
    'Bloomberg',
    'Capital One',
    'CoStar Group',
    'Databricks',
    'Google',
    'Meta',
    'Microsoft',
    'NVIDIA',
    'OpenAI',
    'Palantir',
    'Peraton',
    'Robinhood',
    'Salesforce',
    'SpaceX',
    'Stripe',
    'Tesla',
    'Waymo',
    'Wells Fargo',
]

BOUNDARY_KEYWORDS = [r'\bintern\b', r'\binternship\b', r'\bco-op\b', r'\bcoop\b', r'\bjunior\b',
                     r'\bphd\b', r'\bgraduate\b', r'\bms intern\b',
                     r'\bstudent\b', r'\bcampus\b']

SUBSTRING_KEYWORDS = [
    'new grad', 'new-grad', 'entry level', 'entry-level', 'early career', '2027',
    'university graduate', 'university grad', 'university recruit', 'university hire',
    'campus hire', 'college hire',
    'new hire', 'associate engineer', 'associate software', 'associate data',
    'research scientist', 'recent graduate', 'class of 2027',
    'summer 2026', 'fall 2026', 'spring 2026', 'winter 2026',
    'summer 2027', 'fall 2027', 'spring 2027',
    'phd early career', 'associate data scientist', 'associate product manager',
    ', associate', 'associate (',
    'engineering, associate', 'science, associate',
]

TECH_KEYWORDS = [
    'software', 'engineer', 'engineering', 'developer', 'data', 'machine learning',
    'ml', 'ai ', ' ai', 'artificial intelligence', 'research', 'researcher',
    'quantitative', 'quant', 'infrastructure', 'devops', 'platform', 'backend',
    'frontend', 'front-end', 'back-end', 'fullstack', 'full-stack', 'mobile',
    'ios', 'android', 'cloud', 'security', 'cybersecurity', 'network', 'systems',
    'database', 'analytics', 'product', 'sre', 'reliability', 'embedded',
    'robotics', 'computer', 'computational', 'algorithm', 'applied',
    'technical', 'scientist', 'physics', 'math', 'statistics', 'fintech',
    'product manager', 'program manager', 'consultant', 'consulting',
    'digital', 'technology associate', 'technology analyst',
    'information technology', 'business analyst', 'business technology',
]

                                                                                                              
HIGH_CONFIDENCE_TECH_SIGNALS = [
    'software engineer', 'software developer', 'software development',
    'data engineer', 'data scientist', 'data analyst', 'data science',
    'machine learning', 'ml engineer', 'ai engineer',
    'devops', 'sre ', 'site reliability',
    'backend engineer', 'frontend engineer', 'full-stack engineer', 'fullstack engineer',
    'cloud engineer', 'platform engineer', 'infrastructure engineer',
    'cybersecurity', 'security engineer', 'security analyst',
    'mobile engineer', 'ios engineer', 'android engineer',
    'quantitative researcher', 'quantitative analyst', 'quantitative developer',
    'technology intern', 'technology associate', 'technology analyst',
    'engineering development program', 'software engineering intern',
    'software engineer intern', 'developer intern', 'data intern',
    'associate software', 'software engineering, associate', 'software engineer, associate',
]

_US_STATE_ABBRS = {
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi',
    'id', 'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi',
    'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc',
    'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut',
    'vt', 'va', 'wa', 'wv', 'wi', 'wy', 'dc',
    'on', 'bc', 'qc', 'ab', 'mb', 'sk', 'ns', 'nb', 'nl', 'pe',
}

US_SIGNALS = [
    'united states', 'usa', 'u.s.a',
    'new york', 'san francisco', 'los angeles', 'seattle', 'boston',
    'chicago', 'austin', 'denver', 'atlanta', 'miami', 'dallas',
    'raleigh', 'washington d', 'menlo park', 'palo alto', 'mountain view',
    'redwood city', 'bellevue', 'portland',
    'toronto', 'vancouver', 'montreal', 'ottawa', 'calgary', 'canada',
]

NON_US_SIGNALS = [
    'london', 'united kingdom', ', uk', '(uk)', 'u.k.',
    'berlin', 'munich', 'frankfurt', 'germany',
    'paris', 'france',
    'amsterdam', 'netherlands',
    'dublin', 'ireland',
    'sydney', 'melbourne', 'australia',
    'singapore',
    'bangalore', 'hyderabad', 'india',
    'tokyo', 'japan',
    'beijing', 'shanghai', 'china',
    'tel aviv', 'israel',
    'mexico city', 'mexico',
    'brazil', 'sao paulo',
    'worldwide', 'global (non-us)',
    'cape town', 'south africa',
    'riyadh', 'saudi arabia',
    'costa rica',
    'za, ', 'sa, ', 'cr, ', 'gb, ', 'de, ', 'fr, ', 'nl, ', 'ie, ',
    'au, ', 'sg, ', 'in, ', 'jp, ', 'cn, ', 'il, ', 'mx, ', 'br, ',
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; job-scraper/1.0)'}

US_STATE_ABBRS = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC',
}
CA_PROVINCE_ABBRS = {
    'alberta': 'AB', 'british columbia': 'BC', 'manitoba': 'MB',
    'new brunswick': 'NB', 'newfoundland': 'NL', 'nova scotia': 'NS',
    'northwest territories': 'NT', 'nunavut': 'NU', 'ontario': 'ON',
    'prince edward island': 'PE', 'quebec': 'QC', 'saskatchewan': 'SK', 'yukon': 'YT',
}

def normalize_location(location):
    if not location:
        return location

    CITY_DEFAULTS = {
        'ottawa': 'Ottawa, ON', 'toronto': 'Toronto, ON', 'montreal': 'Montreal, QC',
        'vancouver': 'Vancouver, BC', 'atlanta': 'Atlanta, GA', 'chicago': 'Chicago, IL',
        'boston': 'Boston, MA', 'seattle': 'Seattle, WA', 'austin': 'Austin, TX',
    }

    def _normalize_part(part):
        part = part.strip()
        if not part:
            return part
        pl = part.lower()
        if pl in ('remote', 'remote us', 'remote - us', 'remote usa'):
            return 'Remote (US)'
        if pl in ('remote canada', 'remote - canada'):
            return 'Remote (Canada)'

        m = re.match(r'^US,\s*([^,]+),\s*(.+)$', part, re.I)
        if m:
            region, city = m.group(1).strip(), m.group(2).strip()
            abbr = US_STATE_ABBRS.get(region.lower()) or CA_PROVINCE_ABBRS.get(region.lower())
            if abbr:
                return f'{city}, {abbr}'

                                    
        m = re.match(r'^US-([A-Z]{2})-(.+)$', part, re.I)
        if m:
            return f'{m.group(2).strip()}, {m.group(1).upper()}'

                                                                         
        m = re.match(r'^US-([A-Z]{2})\s+(.+)$', part, re.I)
        if m:
            city = re.split(r'\s+-\s+', m.group(2).strip(), maxsplit=1)[0].strip()
            return f'{city}, {m.group(1).upper()}'

        m = re.match(r'^(.+),\s*([^,]+),\s*USA$', part, re.I)
        if m:
            city, region = m.group(1).strip(), m.group(2).strip().lower()
            abbr = US_STATE_ABBRS.get(region)
            if abbr:
                return f'{city}, {abbr}'

        # Oracle HCM: "Phoenix, AZ, United States" / "Toronto, ON, Canada"
        m = re.match(
            r'^(.+),\s*([A-Za-z]{2}),\s*(United States(?: of America)?|USA|Canada)$',
            part,
            re.I,
        )
        if m:
            return f'{m.group(1).strip()}, {m.group(2).upper()}'

        m = re.match(
            r'^(.+),\s*([^,]+),\s*(United States(?: of America)?|USA|Canada)$',
            part,
            re.I,
        )
        if m:
            city, region = m.group(1).strip(), m.group(2).strip().lower()
            abbr = US_STATE_ABBRS.get(region) or CA_PROVINCE_ABBRS.get(region)
            if abbr:
                return f'{city}, {abbr}'

        pieces = [p.strip() for p in part.split(',')]
        if len(pieces) == 2:
            city, region = pieces[0], pieces[1]
            abbr = US_STATE_ABBRS.get(region.lower()) or CA_PROVINCE_ABBRS.get(region.lower())
            if abbr:
                return f'{city}, {abbr}'

        if pl in CITY_DEFAULTS:
            return CITY_DEFAULTS[pl]
        return part

    location = location.replace('•', ';')
    parts = [_normalize_part(p) for p in re.split(r'[;\n]', location) if p.strip()]
    return '; '.join(parts)

def load_title_cache():
    global _title_cache
    if _title_cache is None:
        try:
            if TITLE_CACHE_FILE.exists():
                with open(TITLE_CACHE_FILE) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _title_cache = {}
                    for k, v in data.items():
                        if not isinstance(k, str):
                            continue
                        if is_out_of_scope_title(k):
                            _title_cache[k] = False
                            _confidence_cache[k] = 'high'
                            _add_cache[k] = False
                            continue
                        if isinstance(v, dict):
                            _title_cache[k] = bool(v.get('is_tech', v.get('t', False)))
                            _confidence_cache[k] = v.get('confidence', v.get('c', 'medium'))
                            if 'a' in v or 'add' in v:
                                _add_cache[k] = bool(v.get('a', v.get('add')))
                        else:
                            _title_cache[k] = bool(v)
                else:
                    print('  [Cache] Corrupt title cache — resetting')
                    _title_cache = {}
            else:
                _title_cache = {}
        except Exception as e:
            print(f'  [Cache] Failed to load title cache: {e} — resetting')
            _title_cache = {}
    return _title_cache

def save_title_cache():
    if _title_cache is not None:
        try:
            TITLE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            out = {}
            for k, is_tech in _title_cache.items():
                entry = {
                    't': bool(is_tech),
                    'c': _confidence_cache.get(k, 'medium'),
                }
                if k in _add_cache:
                    entry['a'] = int(_add_cache[k])
                out[k] = entry
            with open(TITLE_CACHE_FILE, 'w') as f:
                json.dump(out, f, indent=2)
        except Exception as e:
            print(f'  [Cache] Failed to save title cache: {e}')

def _read_usage_calls(path, today):
    try:
        if not path.exists():
            return 0
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get('date') == today:
            return int(data.get('calls', 0))
    except Exception:
        return 0
    return 0

def _total_claude_calls_today(today=None):
                                                                                        
    today = today or datetime.now().strftime('%Y-%m-%d')
    data_dir = Path('.github/data')
    total = 0
    seen_paths = set()
    for path in [CLAUDE_USAGE_FILE, *sorted(data_dir.glob('claude_usage*.json'))]:
        resolved = str(path.resolve()) if path.exists() else str(path)
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        total += _read_usage_calls(path, today)
    return total

def load_claude_usage():
    global _claude_calls_today, _claude_usage_date
    today = datetime.now().strftime('%Y-%m-%d')
    _claude_usage_date = today
    _claude_calls_today = _read_usage_calls(CLAUDE_USAGE_FILE, today)

def save_claude_usage():
    global _claude_usage_dirty
    try:
        CLAUDE_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {'date': _claude_usage_date or datetime.now().strftime('%Y-%m-%d'),
                   'calls': _claude_calls_today}
        with open(CLAUDE_USAGE_FILE, 'w') as f:
            json.dump(payload, f)
        _claude_usage_dirty = False
    except Exception as e:
        print(f'  [Claude] Failed to save usage file: {e}')

_claude_calls_this_run = 0

def _get_claude_client():
    global _claude_client
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=api_key)
    return _claude_client

def _record_claude_call():
    global _claude_calls_today, _claude_calls_this_run, _claude_usage_dirty
    if _claude_usage_date != datetime.now().strftime('%Y-%m-%d'):
        load_claude_usage()
    _claude_calls_today += 1
    _claude_calls_this_run += 1
    _claude_usage_dirty = True

def _derive_add_decision(title, is_tech):
    if not is_tech or is_out_of_scope_title(title):
        return False
    return is_auto_addable(title)

def _normalize_claude_row(row):
                                                                             
    if not isinstance(row, dict):
        return None
    if 't' in row or 'c' in row:
        conf_map = {'h': 'high', 'm': 'medium', 'l': 'low'}
        c = str(row.get('c', 'm')).lower()
        return {
            'is_tech': bool(int(row.get('t', 0))),
            'confidence': conf_map.get(c, c if c in conf_map.values() else 'medium'),
            'a': int(row.get('a', 0)),
        }
    return {
        'is_tech': bool(row.get('is_tech', False)),
        'confidence': row.get('confidence', 'medium'),
        'a': int(row.get('a', 0)) if 'a' in row else None,
    }

def batch_classify_with_claude(titles):
    client = _get_claude_client()
    if not client or not titles:
        return {}

    numbered = '\n'.join(
        f'{i + 1}. {titles[i][:TITLE_PROMPT_MAX_LEN]}' for i in range(len(titles))
    )
    n = len(titles)
    prompt = (
        f'CS intern/new-grad board. JSON array len {n}, same order.\n'
        'Each {{"t":0|1,"c":"h"|"m"|"l","a":0|1}}. '
        't=1 core tech (SWE/data/ML/quant/cyber/DevOps/tech-PM). '
        'a=1 only entry campus fit for those. '
        'a=0 marketing/HR/people/sales/generic-BA/systems-eng(no software)/'
        'non-CS research associate/hardware/senior.\n'
        f'{numbered}\nJSON only.'
    )

    for attempt in range(4):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=n * 12 + 32,
                messages=[{'role': 'user', 'content': prompt}],
            )

            _record_claude_call()

            text = message.content[0].text.strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            raw = json.loads(text)

            if not isinstance(raw, list) or len(raw) != n:
                print(f'  [Claude] Expected {n} results, got '
                      f'{len(raw) if isinstance(raw, list) else type(raw).__name__}')
                                                                            
                if n > 20 and attempt < 3:
                    mid = n // 2
                    out = {}
                    out.update(batch_classify_with_claude(titles[:mid]))
                    out.update(batch_classify_with_claude(titles[mid:]))
                    return out
                return {}

            results = {}
            for i, row in enumerate(raw):
                norm = _normalize_claude_row(row)
                if norm is None:
                    continue
                if norm.get('a') is None:
                    del norm['a']
                else:
                    norm['a'] = int(norm['a'])
                results[titles[i].lower()] = norm
            return results

        except json.JSONDecodeError as e:
            print(f'  [Claude] JSON parse error: {e}')
            if n > 20 and attempt < 3:
                mid = n // 2
                out = {}
                out.update(batch_classify_with_claude(titles[:mid]))
                out.update(batch_classify_with_claude(titles[mid:]))
                return out
            return {}
        except anthropic.APIStatusError as e:
            if e.status_code == 429:
                wait = min((2 ** attempt) * 5, 60)
                print(f'  [Claude] 429 rate limit — waiting {wait}s (attempt {attempt + 1}/4)')
                time.sleep(wait)
                continue
            print(f'  [Claude] API error {e.status_code}: {e.message}')
            return {}
        except Exception as e:
            print(f'  [Claude] Error: {e}')
            return {}

    return {}

def classify_titles_batch(title_list):
    global _confidence_cache

    cache = load_title_cache()

    seen_lower = set()
    uncached = []
    for t in title_list:
        tl = t.lower()
        if tl in seen_lower:
            continue
        if tl in cache:
            if tl not in _add_cache:
                _add_cache[tl] = _derive_add_decision(t, bool(cache[tl]))
            seen_lower.add(tl)
            continue
        if any(s in tl for s in HARD_REJECT_SIGNALS) or is_out_of_scope_title(t):
            cache[tl] = False
            _confidence_cache[tl] = 'high'
            _add_cache[tl] = False
            seen_lower.add(tl)
            continue
        if any(s in tl for s in HIGH_CONFIDENCE_TECH_SIGNALS):
            if is_out_of_scope_title(t):
                cache[tl] = False
                _confidence_cache[tl] = 'high'
                _add_cache[tl] = False
            else:
                cache[tl] = True
                _confidence_cache[tl] = 'high'
                _add_cache[tl] = is_auto_addable(t)
            seen_lower.add(tl)
            continue
        seen_lower.add(tl)
        uncached.append(t)

    if not uncached:
        return 0

    print(f'  [Claude] Batch-classifying {len(uncached)} uncached titles '
          f'({(len(uncached) + CLAUDE_BATCH_SIZE - 1) // CLAUDE_BATCH_SIZE} call(s))...')
    classified = 0

    for i in range(0, len(uncached), CLAUDE_BATCH_SIZE):
        batch = uncached[i:i + CLAUDE_BATCH_SIZE]
        results = batch_classify_with_claude(batch)
        for title in batch:
            tl = title.lower()
            result = results.get(tl)
            if result is not None:
                is_tech = bool(result.get('is_tech', False))
                cache[tl] = is_tech
                _confidence_cache[tl] = result.get('confidence', 'medium')
                if is_out_of_scope_title(title):
                    _add_cache[tl] = False
                elif 'a' in result:
                    _add_cache[tl] = bool(int(result.get('a', 0))) and is_tech
                else:
                    _add_cache[tl] = _derive_add_decision(title, is_tech)
            else:
                is_tech = is_tech_title_keywords(title)
                cache[tl] = is_tech
                _confidence_cache[tl] = 'medium'
                _add_cache[tl] = _derive_add_decision(title, is_tech)
            classified += 1

    return classified

def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen):
    SEEN_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_JOBS_FILE, 'w') as f:
        json.dump(sorted(list(seen)), f, indent=2)

def normalize_company_name(name):
    return re.sub(r'[^a-z0-9]+', '', name.strip().lower())

def load_followed_companies():
    try:
        if FOLLOWED_COMPANIES_FILE.exists():
            with open(FOLLOWED_COMPANIES_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                loaded = {
                    normalize_company_name(c)
                    for c in data
                    if isinstance(c, str) and c.strip()
                }
                if loaded:
                    return loaded
            print('  [alerts] Invalid followed_companies.json, using defaults')
    except Exception as e:
        print(f'  [alerts] Failed to load followed companies file: {e}')
    return {normalize_company_name(c) for c in DEFAULT_FOLLOWED_COMPANIES}

def is_followed_company(company, followed_companies):
    return normalize_company_name(company) in followed_companies

def send_followed_company_webhook_alert(job):
    webhook_url = os.environ.get('PRIORITY_ALERT_WEBHOOK_URL', '').strip()
    if not webhook_url:
        return

    if 'discord.com/api/webhooks' in webhook_url:
        message = (
            '## 🚨 Followed Company Role Detected\n'
            f'**Company:** {job["company"]}\n'
            f'**Role:** {job["title"]}\n'
            f'**Location:** {job["location"]}\n'
            f'**Portal:** {job["board"]}\n'
            f'**Apply:** [Open listing]({job["url"]})'
        )
        payload = {'content': message}
    else:
        message = (
            f'Followed company role detected\n'
            f'Company: {job["company"]}\n'
            f'Role: {job["title"]}\n'
            f'Location: {job["location"]}\n'
            f'Portal: {job["board"]}\n'
            f'Apply: {job["url"]}'
        )
        payload = {'text': message}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=(10, 30))
        if resp.status_code not in (200, 201, 202, 204):
            print(f'  [alerts] webhook failed ({resp.status_code}): {resp.text[:200]}')
    except Exception as e:
        print(f'  [alerts] webhook error: {e}')

def is_tech_title_keywords(title):
    t = title.lower()
    if is_out_of_scope_title(title):
        return False
    return any(kw in t for kw in TECH_KEYWORDS)

def classify_title(title, allow_claude=True):
    t = title.lower()

    if is_out_of_scope_title(title):
        return False, True

    cache = load_title_cache()
    if t in cache:
        confidence = _confidence_cache.get(t, 'high')
        return cache[t], confidence != 'low'

    if allow_claude:
        try:
            results = batch_classify_with_claude([title])
            if results and t in results:
                result = results[t]
                is_tech = bool(result.get('is_tech', False))
                confidence = result.get('confidence', 'medium')
                cache[t] = is_tech
                _confidence_cache[t] = confidence
                if 'a' in result:
                    _add_cache[t] = bool(int(result.get('a', 0)))
                return is_tech, confidence != 'low'
        except Exception:
            pass

    is_tech = is_tech_title_keywords(title)
    return is_tech, True

def is_candidate_title(title):
    t = title.lower()
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False
    if any(re.search(kw, t) for kw in BOUNDARY_KEYWORDS):
        return True
    if any(kw in t for kw in SUBSTRING_KEYWORDS):
        return True
    return False

def is_us_location(location):
    if not location or location.strip() == '':
        return False

                                                          
    location = normalize_location(location)
    loc = location.lower()

    if any(s in loc for s in NON_US_SIGNALS):
        return False

    if loc.strip() in ('remote', 'remote (us)', 'us remote', 'remote - us',
                       'remote, us', 'remote, usa', 'work from home',
                       'remote (canada)', 'canada remote', 'remote, canada'):
        return True

    if any(s in loc for s in US_SIGNALS):
        return True

    if any(re.search(r',\s+' + abbr + r'(?:[^a-z]|$)', loc)
           for abbr in _US_STATE_ABBRS):
        return True

    return False

OFFCYCLE_SEASONS = (
    'Co-op', 'Fall 2027', 'Spring 2027', 'Winter 2027',
    'Fall 2026', 'Spring 2026', 'Winter 2026', 'Summer 2026',
)

def infer_listing_type(title):
                                                                              
    t = title.lower()
    is_intern = bool(re.search(r'\bintern(ship)?\b|\bco-?op\b', t))

    if any(kw in t for kw in ['co-op', 'coop', 'co op']):
        return 'Internship', 'Co-op'

    # Full-time new-grad signals beat graduation-window seasons embedded in titles
    # e.g. "Software Engineer I, Entry-Level (Graduation Date: Fall 2026-Summer 2027)"
    if not is_intern and any(kw in t for kw in [
        'new grad', 'new-grad', 'entry level', 'entry-level', 'early career',
        'university graduate', 'new college grad', 'college grad',
        'full-time', ' full time', 'campus undergraduate', 'campus graduate',
    ]):
        return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'

    # Bank / consulting style graduate & analyst programs (non-intern)
    if not is_intern:
        if re.search(r'\bgraduate (program|programme)\b', t) and any(
            k in t for k in (
                'technolog', 'developer', 'engineer', 'software', 'data',
                'quant', 'product', 'trading', 'analyst',
            )
        ):
            return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'
        if re.search(r'\banalyst program\b', t) and any(
            k in t for k in (
                'engineering', 'developer', 'data science', 'technolog',
                'trading', 'product', 'software', 'quant',
            )
        ):
            return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'
        if re.search(r'\bgraduate (quantitative|software|trader|developer|engineer|researcher)\b', t):
            return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'

    if any(kw in t for kw in ['fall 2027', 'autumn 2027']):
        return 'Internship', 'Fall 2027'
    if 'spring 2027' in t:
        return 'Internship', 'Spring 2027'
    if 'winter 2027' in t:
        return 'Internship', 'Winter 2027'
    if any(kw in t for kw in ['fall 2026', 'autumn 2026']):
        return 'Internship', 'Fall 2026'
    if 'spring 2026' in t:
        return 'Internship', 'Spring 2026'
    if 'winter 2026' in t:
        return 'Internship', 'Winter 2026'
    if 'summer 2026' in t:
        return 'Internship', 'Summer 2026'

    if not is_intern:
        if re.search(
            r'\bassociate\b.*\b(software|data|security|platform|devops|sre|product)\b'
            r'|\b(software|data|security|platform|devops|cyber)\b.*\bassociate\b'
            r'|\bjunior\b.*\b(software|engineer|developer|data)\b',
            t,
        ):
            return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'

    if re.search(r'research scientist', t):
        if is_intern:
            return 'Internship', 'Summer 2027'
        if any(kw in t for kw in ['new college grad', 'university grad', 'phd early career']):
            return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'

    if is_intern:
        return 'Internship', 'Summer 2027'
    if re.search(
        r'summer analyst|technology intern|leadership rotation|undergraduate student|'
        r'junior (quantitative|software|developer)',
        t,
    ):
        return 'Internship', 'Summer 2027'

    return 'Internship', 'Summer 2027'

def _title_is_tech(title):
    tl = title.lower()
    cache = load_title_cache()
    if tl in cache:
        return bool(cache[tl])
    is_tech, _ = classify_title(title)
    return is_tech

def should_list_job(job):
    title = job['title']
    tl = title.lower()
    if is_out_of_scope_title(title):
        return False
    if not _title_is_tech(title):
        return False
    if tl in _add_cache:
        return _add_cache[tl]
    conf = _confidence_cache.get(tl, 'medium')
    if conf == 'low':
        return False
    if is_auto_addable(title) and conf in ('high', 'medium'):
        return True
    return False

def is_auto_addable(title):
    t = title.lower()

    if is_out_of_scope_title(title):
        return False

    if re.search(r'\b(senior|staff|principal|director)\b', t) and 'intern' not in t:
        return False
    if re.search(r'\blead\b', t) and 'intern' not in t and 'leadership' not in t:
        return False

    listing_type, season = infer_listing_type(title)

    if listing_type == 'New Grad (Full-Time)':
        return True
    if season in OFFCYCLE_SEASONS:
        return True
    if re.search(r'\bintern(ship)?\b', t):
        return True
    if re.search(
        r'summer analyst|technology intern|leadership rotation|undergraduate student|'
        r'junior (quantitative|software|developer)',
        t,
    ):
        return True

    if re.search(r'research scientist', t) and 'intern' not in t and 'early career' not in t:
        return False

    return False

def table_for_listing(listing_type, season):
    if listing_type == 'New Grad (Full-Time)':
        return 'newgrad'
    if season in OFFCYCLE_SEASONS:
        return 'offcycle'
    return 'summer'

def infer_education_level(title):
    t = title.lower()
    if any(kw in t for kw in ['phd', 'ph.d', 'phd student', 'phd intern', 'phd research', 'phd early career']):
        return 'PhD'
    if any(kw in t for kw in ['master', 'ms ', 'm.s.', 'masters', 'meng', 'm.eng']):
        return 'Masters'
    return 'Undergrad'

_UTM_HOST_MARKERS = (
    'greenhouse.io', 'lever.co', 'ashbyhq.com', 'myworkdayjobs.com', 'workdaysite.com',
)
_UTM_STRIP = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id',
    'source', 'src', 'ref', 'referer', 'lever-source', 'lever-origin', 'gh_src',
}

def with_aprameyak_utm(url):
                                                                                   
    if not url:
        return url
    try:
        p = urlparse(url.strip())
        host = (p.netloc or '').lower()
        if not any(m in host for m in _UTM_HOST_MARKERS):
            return url
        params = {}
        for k, v in parse_qs(p.query, keep_blank_values=True).items():
            kl = k.lower()
            if kl in _UTM_STRIP:
                continue
                                                                         
            cleaned = [x for x in v if x not in ('', 'gh_src=', 'gh_src')]
            if kl == 't' and (not cleaned or all(str(x).startswith('gh_src') for x in cleaned)):
                continue
            if not cleaned and kl != 'gh_jid':
                continue
            params[k] = cleaned if cleaned else v
        params['utm_source'] = ['aprameyak']
        return urlunparse(p._replace(
            query=urlencode(sorted(params.items()), doseq=True),
            fragment='',
        ))
    except Exception:
        return url

def build_entry(job):
                                                              
    listing_type, season = infer_listing_type(job['title'])
    education = infer_education_level(job['title'])
    location = normalize_location(job.get('location', ''))
    table = table_for_listing(listing_type, season)
    title_l = job['title'].lower()
    citizenship = 'Unknown'
    if any(k in title_l for k in (
        'ts/sci', 'top secret', 'u.s. citizen', 'us citizen', 'us citizenship',
        'security clearance', 'with poly', 'w/poly', 'w poly',
    )):
        citizenship = 'Yes — U.S. citizenship required'
    entry = {
        'company': job['company'],
        'role': job['title'],
        'location': location,
        'type': table,
        'season': season,
        'education': education,
        'url': with_aprameyak_utm(job['url']),
        'sponsorship': 'Unknown',
        'citizenship': citizenship,
        'date_added': datetime.now().strftime('%Y-%m-%d'),
    }
    if table == 'newgrad':
        entry['grad_date'] = infer_grad_date(entry['role'], entry['url'])
                                                                   
    return entry

def add_job_directly(job, listings_file, rebuild=True):
    try:
        listing_type, season = infer_listing_type(job['title'])
        education = infer_education_level(job['title'])
        location = normalize_location(job.get('location', ''))

        table = table_for_listing(listing_type, season)

        entry = {
            'company': job['company'],
            'role': job['title'],
            'location': location,
            'type': table,
            'season': season,
            'education': education,
            'url': with_aprameyak_utm(job['url']),
            'sponsorship': 'Unknown',
            'citizenship': 'Unknown',
            'date_added': datetime.now().strftime('%Y-%m-%d'),
        }
        if table == 'newgrad':
            entry['grad_date'] = infer_grad_date(entry['role'], entry['url'])

        listings_path = listings_file
        if listings_path.exists():
            with open(listings_path) as f:
                listings = json.load(f)
        else:
            listings = []

        def _norm_url(u):
            if not u:
                return u
            u = u.split('?')[0].split('#')[0].rstrip('/')
            m = re.match(r'(https?://)([^/]+)(.*)', u)
            if m:
                scheme, host, path = m.groups()
                host = host.lower()
                if host.startswith('www.'):
                    host = host[4:]
                u = scheme + host + path
            u = re.sub(r'/application$', '', u)
            u = re.sub(r'(myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?[^/]+/job/', r'\1/job/', u)
            u = re.sub(r'(_(JR|REQ|R)\d+)-\d+$', r'\1', u, flags=re.I)
            return u

        existing_urls = {_norm_url(e.get('url', '')) for e in listings}
        if _norm_url(entry['url']) in existing_urls:
            print(f'  [direct] Skipping duplicate URL: {entry["url"]}')
            return

        listings.append(entry)
        tmp = listings_path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(listings, f, indent=2)
        tmp.replace(listings_path)
        print(f'  [direct] Added: {entry["company"]} — {entry["role"]}')

        if rebuild:
            result = subprocess.run(
                ['python3', '.github/scripts/rebuild_readme.py'],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f'  [direct] rebuild_readme.py failed: {result.stderr[:200]}')
            else:
                print(f'  [direct] README rebuilt successfully')

    except Exception as e:
        print(f'  [direct] Failed to add "{job.get("title", "unknown")}": {e}')

def scrape_greenhouse(company, slug):
    url = f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true'
    try:
        resp = requests.get(url, timeout=(10, 30), headers=HEADERS)
        if resp.status_code != 200:
            print(f'  [{company}] Greenhouse HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json().get('jobs', []):
            title = job.get('title', '')
            location = job.get('location', {}).get('name', '')
            relevant = is_candidate_title(title)
            if relevant and is_us_location(location):
                jobs.append({
                    'id': f'greenhouse_{slug}_{job["id"]}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': job.get('absolute_url', ''),
                    'board': 'Greenhouse',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Greenhouse error: {e}')
        return []

def scrape_lever(company, slug):
    url = f'https://api.lever.co/v0/postings/{slug}?mode=json'
    try:
        resp = requests.get(url, timeout=(10, 30), headers=HEADERS)
        if resp.status_code != 200:
            print(f'  [{company}] Lever HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json():
            title = job.get('text', '')
            location = job.get('categories', {}).get('location', '')
            relevant = is_candidate_title(title)
            if relevant and is_us_location(location):
                jobs.append({
                    'id': f'lever_{slug}_{job["id"]}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': job.get('hostedUrl', ''),
                    'board': 'Lever',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Lever error: {e}')
        return []

def scrape_ashby(company, slug):
    url = f'https://api.ashbyhq.com/posting-api/job-board/{slug}'
    try:
        resp = requests.get(url, timeout=(10, 30), headers=HEADERS)
        if resp.status_code != 200:
            print(f'  [{company}] Ashby HTTP {resp.status_code}')
            return []
        jobs = []
        data = resp.json()
        postings = data.get('jobPostings') or data.get('jobs') or []
        for job in postings:
            title = job.get('title', '')
            location = job.get('locationName', '') or job.get('location', '')
            relevant = is_candidate_title(title)
            if relevant and is_us_location(location):
                apply_url = (
                    job.get('jobPostingUrls', {}).get('Full', '')
                    or job.get('applyUrl', '')
                    or f'https://jobs.ashbyhq.com/{slug}/{job.get("id", "")}'
                )
                jobs.append({
                    'id': f'ashby_{slug}_{job["id"]}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': apply_url,
                    'board': 'Ashby',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Ashby error: {e}')
        return []

def scrape_smartrecruiters(company, identifier):
    url = f'https://api.smartrecruiters.com/v1/companies/{identifier}/postings'
    params = {'status': 'PUBLIC', 'limit': 100, 'offset': 0}
    jobs = []

    while True:
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=(10, 30))
            if resp.status_code != 200:
                print(f'  [{company}] SmartRecruiters HTTP {resp.status_code}')
                break
            data = resp.json()
            content = data.get('content', [])
            if not content:
                break
            for job in content:
                title = job.get('name', '')
                loc = job.get('location', {})
                country = loc.get('country', '').lower()
                remote = loc.get('remote', False)
                city = loc.get('city', '')
                region = loc.get('region', '')

                if not (country in ('us', 'ca') or remote):
                    continue

                if remote:
                    location = 'Remote'
                elif city and region:
                    location = f'{city}, {region}'
                elif city:
                    location = city
                else:
                    location = country.upper() if country else ''

                relevant = is_candidate_title(title)
                if relevant:
                    job_id = job.get('id', '')
                    jobs.append({
                        'id': f'smartrecruiters_{identifier}_{job_id}',
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': f'https://jobs.smartrecruiters.com/{identifier}/{job_id}',
                        'board': 'SmartRecruiters',
                        })

            total = data.get('totalFound', 0)
            params['offset'] += len(content)
            if params['offset'] >= total:
                break
        except Exception as e:
            print(f'  [{company}] SmartRecruiters error: {e}')
            break

    return jobs

def scrape_workable(company, slug):
    url = f'https://apply.workable.com/api/v1/widget/accounts/{slug}'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=(10, 30))
        if resp.status_code != 200:
            print(f'  [{company}] Workable HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json().get('jobs', []):
            title = job.get('title', '')
            loc = job.get('location', {})
            country = loc.get('countryCode', '').lower()
            remote = loc.get('remote', False)
            city = loc.get('city', '')
            region = loc.get('region', '')

            if not (country in ('us', 'ca') or remote):
                continue

            if remote:
                location = 'Remote'
            elif city and region:
                location = f'{city}, {region}'
            elif city:
                location = city
            else:
                location = country.upper() if country else ''

            relevant = is_candidate_title(title)
            if relevant:
                job_id = job.get('shortcode', job.get('id', ''))
                jobs.append({
                    'id': f'workable_{slug}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': f'https://apply.workable.com/{slug}/j/{job_id}/',
                    'board': 'Workable',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Workable error: {e}')
        return []

def scrape_recruitee(company, slug):
    url = f'https://{slug}.recruitee.com/api/offers/'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=(10, 30))
        if resp.status_code != 200:
            print(f'  [{company}] Recruitee HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json().get('offers', []):
            title = job.get('title', '')
            country = (job.get('country') or '').lower()
            remote = job.get('remote', False) or 'remote' in (job.get('location') or '').lower()
            city = job.get('city', '') or ''
            region = job.get('province', '') or ''

            if not (country in ('us', 'ca', 'united states', 'canada') or remote):
                continue

            if remote:
                location = 'Remote'
            elif city and region:
                location = f'{city}, {region}'
            elif city:
                location = city
            else:
                location = country.title() if country else ''

            relevant = is_candidate_title(title)
            if relevant:
                job_id = str(job.get('id', ''))
                careers_url = job.get('careers_url', f'https://{slug}.recruitee.com/o/{job.get("slug", job_id)}')
                jobs.append({
                    'id': f'recruitee_{slug}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': careers_url,
                    'board': 'Recruitee',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Recruitee error: {e}')
        return []

def scrape_pinpoint(company, slug):
    url = f'https://{slug}.pinpointhq.com/postings.json'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=(10, 30))
        if resp.status_code != 200:
            print(f'  [{company}] Pinpoint HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json().get('data', []):
            attrs = job.get('attributes', {})
            title = attrs.get('job-title', '')
            workplace = attrs.get('workplace-type', '').lower()
            remote = workplace == 'remote'
            city = attrs.get('city', '') or ''
            region = attrs.get('state-province', '') or ''
            country = (attrs.get('country', '') or '').lower()

            if not (country in ('united states', 'us', 'canada', 'ca') or remote):
                continue

            if remote:
                location = 'Remote'
            elif city and region:
                location = f'{city}, {region}'
            elif city:
                location = city
            else:
                location = ''

            relevant = is_candidate_title(title)
            if relevant:
                job_id = job.get('id', '')
                jobs.append({
                    'id': f'pinpoint_{slug}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': f'https://{slug}.pinpointhq.com/postings/{job_id}',
                    'board': 'Pinpoint',
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Pinpoint error: {e}')
        return []

def _workday_job_url(base_url, board, external_path):
    path = re.sub(r'^/[a-z]{2}-[A-Z]{2}/[^/]+(?=/job/)', '', external_path)
    if not path.startswith('/job/'):
        path = external_path
    if board:
        return f'{base_url}/en-US/{board}{path}'
    return f'{base_url}{path}'

def _oracle_job_url(host, site_number, job_id):
    return (
        f'https://{host}/hcmUI/CandidateExperience/en/sites/'
        f'{site_number}/job/{job_id}'
    )

def scrape_oracle(company, host, site_number, keywords=None):
    """Scrape Oracle HCM Candidate Experience (CE) recruiting API."""
    host = host.strip().removeprefix('https://').removeprefix('http://').rstrip('/')
    site_number = site_number.strip()
    search_terms = list(keywords) if keywords else list(ORACLE_SEARCH_TERMS)

    api_base = (
        f'https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions'
    )
    headers = {
        **HEADERS,
        'Accept': 'application/json',
    }

    jobs = []
    seen_ids = set()

    for search_term in search_terms:
        offset = 0
        pages_fetched = 0
        while pages_fetched < MAX_ORACLE_PAGES_PER_TERM:
            finder = (
                f'findReqs;siteNumber={site_number},'
                'facetsList=LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;'
                'CATEGORIES;ORGANIZATIONS;JOB_FAMILY;JOB_FUNCTION;WORK_LEVEL;'
                f'WORKER_TYPES,limit={ORACLE_PAGE_SIZE},offset={offset},'
                f'keyword={search_term}'
            )
            try:
                resp = requests.get(
                    api_base,
                    params={
                        'onlyData': 'true',
                        'expand': 'requisitionList.secondaryLocations',
                        'finder': finder,
                    },
                    headers=headers,
                    timeout=(10, 45),
                )
                if resp.status_code != 200:
                    print(f'  [{company}] Oracle HTTP {resp.status_code} ({search_term})')
                    break
                data = resp.json()
                items = data.get('items') or []
                block = items[0] if items else {}
                reqs = block.get('requisitionList') or []
                if not reqs:
                    break

                for job in reqs:
                    job_id = str(job.get('Id') or '').strip()
                    if not job_id or job_id in seen_ids:
                        continue
                    title = (job.get('Title') or '').strip()
                    location = (job.get('PrimaryLocation') or '').strip()
                    if not title:
                        continue
                    if not is_candidate_title(title):
                        continue
                    if not is_us_location(location):
                        continue
                    seen_ids.add(job_id)
                    jobs.append({
                        'id': f'oracle_{site_number}_{job_id}',
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': _oracle_job_url(host, site_number, job_id),
                        'board': 'Oracle HCM',
                    })

                total = block.get('TotalJobsCount') or block.get('totalJobsCount')
                offset += len(reqs)
                pages_fetched += 1
                if total is not None and offset >= int(total):
                    break
                if len(reqs) < ORACLE_PAGE_SIZE:
                    break
                time.sleep(0.2)
            except Exception as e:
                print(f'  [{company}] Oracle error ({search_term}): {e}')
                break

    return jobs

def scrape_workday(company, tenant, instance, board):
    if board:
        api_url = f'https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs'
    else:
        api_url = f'https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/jobs'
    base_url = f'https://{tenant}.{instance}.myworkdayjobs.com'

    wd_headers = {
        **HEADERS,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    jobs = []
    seen_paths = set()

    for search_term in ['intern', 'internship', 'new grad', 'early career', 'university', '2027', 'co-op']:
        offset = 0
        pages_fetched = 0
        while True:
            payload = {
                'appliedFacets': {},
                'limit': 20,
                'offset': offset,
                'searchText': search_term,
            }
            try:
                resp = requests.post(api_url, json=payload, headers=wd_headers, timeout=(10, 30))
                if resp.status_code != 200:
                    print(f'  [{company}] Workday HTTP {resp.status_code} for "{search_term}"')
                    break
                data = resp.json()
                postings = data.get('jobPostings', [])
                if not postings:
                    break
                for job in postings:
                    external_path = job.get('externalPath', '')
                    if external_path in seen_paths:
                        continue
                    seen_paths.add(external_path)
                    title = job.get('title', '')
                    location = normalize_location(job.get('locationsText', '') or '')
                    relevant = is_candidate_title(title)
                    if relevant and is_us_location(location):
                        jobs.append({
                            'id': f'workday_{tenant}_{external_path}',
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': _workday_job_url(base_url, board, external_path),
                            'board': 'Workday',
                                })
                total = data.get('total', 0)
                offset += len(postings)
                pages_fetched += 1
                if offset >= total or pages_fetched >= MAX_WORKDAY_PAGES_PER_TERM:
                    break
                time.sleep(0.1)
            except Exception as e:
                print(f'  [{company}] Workday error for "{search_term}": {e}')
                break

    return jobs

def _parse_icims_locations(raw):
                                                                                 
    if not raw:
        return ''
    parts = []
    for piece in re.split(r'\s*\|\s*', raw):
        piece = piece.strip()
        if not piece:
            continue
        m = re.match(r'^US-([A-Z]{2})-(.+)$', piece, re.I)
        if m:
            parts.append(f'{m.group(2).strip()}, {m.group(1).upper()}')
        else:
            parts.append(piece)
    return normalize_location('; '.join(parts))

def scrape_icims(company, host, keywords=None):
                                                                       
    keywords = keywords or ['2027', 'intern', 'new grad', 'early career', 'associate']
    jobs = []
    seen_ids = set()
    base = f'https://{host}'

    for keyword in keywords:
        for page in range(0, 8):
            params = {
                'ss': '1',
                'searchKeyword': keyword,
                'searchRelation': 'keyword_all',
                'in_iframe': '1',
                'pr': str(page),
            }
            try:
                resp = requests.get(
                    f'{base}/jobs/search',
                    params=params,
                    headers=HEADERS,
                    timeout=(10, 30),
                )
                if resp.status_code != 200:
                    print(f'  [{company}] iCIMS HTTP {resp.status_code} for "{keyword}" page {page}')
                    break
                html = resp.text
                cards = re.findall(
                    r'<li class="iCIMS_JobCardItem">(.*?)</li>',
                    html,
                    re.S | re.I,
                )
                if not cards:
                    break
                found_new = False
                for card in cards:
                    m = re.search(
                        r'href="(https?://[^"]+/jobs/(\d+)/[^"]+/job)[^"]*"[^>]*'
                        r'class="iCIMS_Anchor"[^>]*title="([^"]+)"',
                        card,
                        re.I,
                    )
                    if not m:
                        m = re.search(
                            r'href="(/jobs/(\d+)/[^"]+/job)[^"]*"[^>]*'
                            r'class="iCIMS_Anchor"[^>]*title="([^"]+)"',
                            card,
                            re.I,
                        )
                    if not m:
                        continue
                    url, job_id, title_attr = m.group(1), m.group(2), m.group(3)
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    found_new = True
                    title = re.sub(r'^\d+\s*-\s*', '', _html.unescape(title_attr)).strip()
                    h3 = re.search(r'<h3[^>]*>(.*?)</h3>', card, re.S | re.I)
                    if h3:
                        title = re.sub(r'<[^>]+>', '', _html.unescape(h3.group(1))).strip() or title
                    loc_m = re.search(
                        r'Job Locations?</span>\s*<span[^>]*>\s*([^<]+)',
                        card,
                        re.I,
                    )
                    location = _parse_icims_locations(loc_m.group(1).strip() if loc_m else '')
                    if not location:
                                                                                       
                        tm = re.search(r'\s[-–—]\s+([A-Za-z .]+,\s*[A-Z]{2})\s*$', title)
                        if tm:
                            location = tm.group(1).strip()
                    if url.startswith('/'):
                        url = f'{base}{url}'
                    url = re.sub(r'\?.*$', '', url)
                    if is_candidate_title(title) and is_us_location(location):
                        jobs.append({
                            'id': f'icims_{host}_{job_id}',
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': url,
                            'board': 'iCIMS',
                        })
                if not found_new:
                    break
                time.sleep(0.15)
            except Exception as e:
                print(f'  [{company}] iCIMS error for "{keyword}" page {page}: {e}')
                break

    return jobs

def scrape_avature(company, portal, keywords=None):
                                                      
    keywords = keywords or ['2027', 'Internship', 'Graduate', 'Student', 'Early Career', 'Intern']
    jobs = []
    seen_ids = set()
    base = f'https://{portal}.avature.net/careers'

    for keyword in keywords:
        try:
            resp = requests.get(
                f'{base}/SearchJobs/',
                params={
                    'listFilterMode': '1',
                    'jobRecordsPerPage': '50',
                    'search': keyword,
                },
                headers=HEADERS,
                timeout=(10, 30),
            )
            if resp.status_code != 200:
                print(f'  [{company}] Avature HTTP {resp.status_code} for "{keyword}"')
                continue
            html = resp.text
            for m in re.finditer(
                r'href="(https?://[^"]*?/JobDetail/([^/]+)/(\d+))"[^>]*>\s*([^<]+)\s*</a>',
                html,
                re.I,
            ):
                url, _slug, job_id, title = (
                    m.group(1), m.group(2), m.group(3), m.group(4).strip(),
                )
                if title.lower() == 'apply' or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                if not is_candidate_title(title):
                    continue
                                                                   
                rest = html[m.end():m.end() + 900]
                loc = ''
                lm = re.search(
                    r'class="[^"]*(?:location|jobLocation)[^"]*"[^>]*>\s*([^<]+)',
                    rest,
                    re.I,
                )
                if lm:
                    loc = lm.group(1).strip()
                else:
                    text = re.sub(r'<[^>]+>', ' ', rest)
                    text = re.sub(r'\s+', ' ', text)
                    lm = re.search(
                        r'([A-Za-z .]+,\s*(?:New York|[A-Z]{2}|United States|USA|Canada)[^|]{0,40})',
                        text,
                    )
                    if lm:
                        loc = lm.group(1).strip()
                location = normalize_location(loc) if loc else ''
                title_l = title.lower()
                if any(s in title_l for s in NON_US_SIGNALS):
                    continue
                if not location or not is_us_location(location):
                    if any(s in title_l for s in (
                        'new york', ', ny', 'united states', 'usa', 'new jersey', ', nj',
                    )):
                        location = 'New York, NY'
                    elif any(s in title_l for s in ('toronto', 'canada', ', on', 'vancouver', ', bc')):
                        location = 'Toronto, ON'
                    else:
                        location = 'United States'
                if not is_us_location(location):
                    continue
                jobs.append({
                    'id': f'avature_{portal}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': url.split('?')[0],
                    'board': 'Avature',
                })
            time.sleep(0.2)
        except Exception as e:
            print(f'  [{company}] Avature error for "{keyword}": {e}')

    return jobs

def _clean_google_location(raw):
    if not raw:
        return ''
    loc = re.sub(r'\s*;\s*\+\d+\s+more\b.*$', '', raw, flags=re.I)
    loc = re.sub(r'\s*(?:bar_chart|share|link|content_copy).*$', '', loc, flags=re.I)
    loc = loc.replace('USA', '').replace('United States', '')
    loc = re.sub(r'\s+', ' ', loc).strip(' ;,')
    first = loc.split(';')[0].strip(' ;,')
    return normalize_location(first)

def scrape_google_careers():
                                                                         
    queries = [
        'Software Engineer Intern 2027',
        'early career 2027',
        'Student Researcher 2027',
        'Software Engineer Early Career',
        'intern 2027',
    ]
    jobs = []
    seen_ids = set()
    skip_headings = {
        'locations', 'experience', 'skills & qualifications', 'degree',
        'job types', 'organizations', 'sort by', 'search sidebar',
    }

    for query in queries:
        for page in range(1, 6):
            params = {
                'q': query,
                'location': 'United States',
                'page': str(page),
            }
            try:
                resp = requests.get(
                    'https://www.google.com/about/careers/applications/jobs/results/',
                    params=params,
                    headers={
                        **HEADERS,
                        'Accept': 'text/html,application/xhtml+xml',
                    },
                    timeout=(10, 30),
                )
                if resp.status_code != 200:
                    print(f'  [Google] HTTP {resp.status_code} for "{query}" page {page}')
                    break
                html = resp.text
                page_jobs = 0
                for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.S | re.I):
                    title = _html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))
                    title = re.sub(r'\s+', ' ', title).strip()
                    if not title or title.lower() in skip_headings:
                        continue
                    chunk = html[m.end():m.end() + 4000]
                    ids = re.findall(r'jobs/results/(\d+)', chunk)
                    if not ids:
                        continue
                    job_id = ids[0]
                    if job_id in seen_ids:
                        continue
                    text = re.sub(r'<[^>]+>', ' ', chunk)
                    text = re.sub(r'\s+', ' ', text)
                    loc = ''
                    lm = re.search(
                        r'place\s+(.+?)(?:\s+share|\s+link|\s+content_copy|\s+schedule|'
                        r'\s+Full-time|\s+Temporary|\s+Learn more|\s+bar_chart)',
                        text,
                    )
                    if lm:
                        loc = _clean_google_location(lm.group(1).strip())
                    if not loc:
                        loc = 'United States'
                    if not is_candidate_title(title):
                        continue
                    if not (is_us_location(loc) or loc == 'United States'):
                        continue
                    seen_ids.add(job_id)
                    page_jobs += 1
                    jobs.append({
                        'id': f'google_{job_id}',
                        'company': 'Google',
                        'title': title,
                        'location': loc,
                        'url': (
                            'https://www.google.com/about/careers/applications/'
                            f'jobs/results/{job_id}'
                        ),
                        'board': 'Google Careers',
                    })
                if page_jobs == 0:
                    break
                time.sleep(0.25)
            except Exception as e:
                print(f'  [Google] Error for "{query}" page {page}: {e}')
                break

    return jobs

def scrape_linkedin_apify(company, company_id):
    apify_token = os.environ.get('APIFY_TOKEN')
    if not apify_token:
        return []

    jobs = []
    seen_ids = set()

    for keyword in ['intern', 'new grad', 'early career']:
        encoded_keyword = keyword.replace(' ', '+')
        search_url = (
            f'https://www.linkedin.com/jobs/search/'
            f'?keywords={encoded_keyword}'
            f'&f_C={company_id}'
            f'&location=United+States'
            f'&f_TPR=r2592000'
        )
        try:
            resp = requests.post(
                'https://api.apify.com/v2/acts/harvestapi~linkedin-job-search/run-sync-get-dataset-items',
                params={'token': apify_token, 'timeout': 60},
                json={'searchUrl': search_url, 'count': 15},
                timeout=90,
            )
            if resp.status_code not in (200, 201):
                print(f'  [{company}] Apify LinkedIn HTTP {resp.status_code} for "{keyword}"')
                continue
            items = resp.json()
            if not isinstance(items, list):
                print(f'  [{company}] Apify LinkedIn unexpected response shape for "{keyword}"')
                continue
            for item in items:
                job_id = str(
                    item.get('id') or item.get('jobId') or item.get('entityUrn', '')
                ).strip()
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                title = (
                    item.get('title') or item.get('jobTitle') or item.get('name') or ''
                ).strip()
                location = (
                    item.get('location') or item.get('jobLocation') or item.get('formattedLocation') or ''
                ).strip()
                url = (
                    item.get('url') or item.get('jobUrl') or item.get('applyUrl')
                    or f'https://www.linkedin.com/jobs/view/{job_id}'
                ).strip()
                if not title:
                    continue
                relevant = is_candidate_title(title)
                if relevant and is_us_location(location):
                    jobs.append({
                        'id': f'linkedin_{job_id}',
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': url,
                        'board': 'LinkedIn',
                        })
        except Exception as e:
            print(f'  [{company}] Apify LinkedIn error for "{keyword}": {e}')
        time.sleep(2)

    return jobs

def scrape_amazon():
    base_url = 'https://www.amazon.jobs/en/search.json'
    params = {
        'base_query': 'intern OR "new grad" OR "university hire"',
        'loc_query': 'united states',
        'result_limit': 100,
        'offset': 0,
        'job_type': 'Full-Time,Part-Time,Temporary,Internship',
    }
    jobs = []

    while True:
        try:
            resp = requests.get(base_url, params=params, headers=HEADERS, timeout=(10, 30))
            if resp.status_code != 200:
                print(f'  [Amazon] HTTP {resp.status_code}')
                break
            data = resp.json()
            postings = data.get('jobs', [])
            if not postings:
                break
            for job in postings:
                title = job.get('title', '')
                location = job.get('location', '')
                job_id = str(job.get('id_icims', job.get('id', '')))
                job_path = job.get('job_path', '')
                url = f'https://www.amazon.jobs{job_path}' if job_path else f'https://www.amazon.jobs/en/jobs/{job_id}'

                relevant = is_candidate_title(title)
                if relevant and is_us_location(location):
                    jobs.append({
                        'id': f'amazon_{job_id}',
                        'company': 'Amazon',
                        'title': title,
                        'location': location,
                        'url': url,
                        'board': 'Amazon Jobs',
                        })

            total = data.get('hits', 0)
            params['offset'] += len(postings)
            if params['offset'] >= total or len(postings) < params['result_limit']:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f'  [Amazon] Error: {e}')
            break

    return jobs

_BOARD_GROUP_BOARDS = {
    'greenhouse': {'greenhouse'},
    'ashby': {'ashby'},
    'workday': {'workday'},
    'oracle': {'oracle'},
    'linkedin_amazon': {'linkedin', 'amazon', 'google'},
    'other': {
        'lever', 'smartrecruiters', 'workable', 'recruitee', 'pinpoint',
        'icims', 'avature',
    },
}

def main():
    load_claude_usage()

    try:
        with open('companies.yml') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f'ERROR: Failed to load companies.yml: {e}')
        return

    included_boards = _BOARD_GROUP_BOARDS.get(BOARD_GROUP) if BOARD_GROUP else None
    if BOARD_GROUP:
        print(f'Board group: {BOARD_GROUP} (boards: {sorted(included_boards)})')
    else:
        print('Board group: all')

    seen = load_seen_jobs()
    followed_companies = load_followed_companies()

    scrape_tasks = []

    for board, scraper in [
        ('greenhouse', scrape_greenhouse),
        ('lever', scrape_lever),
        ('ashby', scrape_ashby),
    ]:
        if included_boards is None or board in included_boards:
            for entry in config.get(board, []):
                scrape_tasks.append((scraper, entry['name'], entry['slug'], board))

    for board_key, scraper, slug_field in [
        ('smartrecruiters', scrape_smartrecruiters, 'identifier'),
        ('workable', scrape_workable, 'slug'),
        ('recruitee', scrape_recruitee, 'slug'),
        ('pinpoint', scrape_pinpoint, 'slug'),
    ]:
        if included_boards is None or board_key in included_boards:
            for entry in config.get(board_key, []):
                scrape_tasks.append((scraper, entry['name'], entry[slug_field], board_key))

    if included_boards is None or 'icims' in included_boards:
        for entry in config.get('icims', []):
            scrape_tasks.append((
                scrape_icims,
                entry['name'],
                entry['host'],
                entry.get('keywords'),
                'icims',
            ))

    if included_boards is None or 'avature' in included_boards:
        for entry in config.get('avature', []):
            scrape_tasks.append((
                scrape_avature,
                entry['name'],
                entry['portal'],
                entry.get('keywords'),
                'avature',
            ))

    if included_boards is None or 'oracle' in included_boards:
        for entry in config.get('oracle', []):
            scrape_tasks.append((
                scrape_oracle,
                entry['name'],
                entry['host'],
                entry['site'],
                entry.get('keywords'),
                'oracle',
            ))

    if included_boards is None or 'workday' in included_boards:
        for entry in config.get('workday', []):
            scrape_tasks.append((
                scrape_workday,
                entry['name'], entry['tenant'], entry['instance'], entry.get('board', ''),
                'workday',
            ))

    if included_boards is None or 'linkedin' in included_boards:
        for entry in config.get('linkedin', []):
            scrape_tasks.append((scrape_linkedin_apify, entry['name'], str(entry['company_id']), 'linkedin'))

    if included_boards is None or 'amazon' in included_boards:
        scrape_tasks.append(('amazon_special', scrape_amazon))

    if included_boards is None or 'google' in included_boards:
        scrape_tasks.append(('google_special', scrape_google_careers))

    def _run_task(task):
        fn, *args = task
        board_label = args[-1]
        scraper_args = args[:-1]
        company = scraper_args[0] if scraper_args else 'Unknown'
        print(f'Checking {company} ({board_label})...')
        try:
            return fn(*scraper_args)
        except Exception as e:
            print(f'  [{company}] Scraper crashed: {e}')
            return []

    def _run_workday_task(task):
        _, company, tenant, instance, board_name, _label = task
        print(f'Checking {company} (workday/{tenant}/{board_name})...')
        try:
            return scrape_workday(company, tenant, instance, board_name)
        except Exception as e:
            print(f'  [{company}] Scraper crashed: {e}')
            return []

    def _run_oracle_task(task):
        _, company, host, site_number, keywords, _label = task
        print(f'Checking {company} (oracle/{host}/{site_number})...')
        try:
            return scrape_oracle(company, host, site_number, keywords)
        except Exception as e:
            print(f'  [{company}] Scraper crashed: {e}')
            return []

    def _run_amazon_task():
        print('Checking Amazon (amazon.jobs)...')
        try:
            return scrape_amazon()
        except Exception as e:
            print(f'  [Amazon] Scraper crashed: {e}')
            return []

    def _run_google_task():
        print('Checking Google (careers.google.com)...')
        try:
            return scrape_google_careers()
        except Exception as e:
            print(f'  [Google] Scraper crashed: {e}')
            return []

    candidate_jobs = []
    print(f'Scraping {len(scrape_tasks)} sources concurrently (max {SCRAPER_MAX_WORKERS} workers)...')

    with ThreadPoolExecutor(max_workers=SCRAPER_MAX_WORKERS) as executor:
        futures = {}
        for task in scrape_tasks:
            fn = task[0]
            if fn == 'amazon_special':
                futures[executor.submit(_run_amazon_task)] = task
            elif fn == 'google_special':
                futures[executor.submit(_run_google_task)] = task
            elif fn is scrape_workday:
                futures[executor.submit(_run_workday_task, task)] = task
            elif fn is scrape_oracle:
                futures[executor.submit(_run_oracle_task, task)] = task
            else:
                futures[executor.submit(_run_task, task)] = task

        for future in as_completed(futures):
            try:
                for job in future.result():
                    if job['id'] not in seen:
                        candidate_jobs.append(job)
            except Exception as e:
                print(f'  [task] Future error: {e}')

    print(f'\nPass 1 complete: {len(candidate_jobs)} candidate job(s) to classify')

    if candidate_jobs:
        all_titles = list(dict.fromkeys(j['title'] for j in candidate_jobs))
        classified = classify_titles_batch(all_titles)
        print(f'  [Claude] Classified {classified} unique title(s); '
              f'{_claude_calls_this_run} call(s) this run, {_claude_calls_today} today')

    new_jobs = []
    for job in candidate_jobs:
        try:
            is_tech, confident = classify_title(job['title'], allow_claude=False)
        except Exception as e:
            print(f'  [classify] Error on "{job["title"]}": {e} — skipping')
            continue
        if is_tech:
            new_jobs.append(job)
            print(f'  NEW: {job["title"]} @ {job["location"]}')
        elif confident:
                                                                  
            seen.add(job['id'])

    print(f'\nFound {len(new_jobs)} new tech job(s)')

    to_list = []
    to_list_ids = set()
    for job in new_jobs:
        tl = job['title'].lower()
        if tl not in _add_cache:
            _add_cache[tl] = _derive_add_decision(job['title'], True)
        if should_list_job(job):
            to_list.append(job)
            to_list_ids.add(job['id'])
            continue
        if tl in _add_cache and not _add_cache[tl]:
            seen.add(job['id'])

    print(f'  Adding {len(to_list)} job(s) to pending')

    if PENDING_FILE is not None:
        pending = []
        for j in to_list:
            entry = build_entry(j)
            violations = validate_entry(entry)
            if violations:
                print(f'  REJECT: {entry["company"]} — {entry["role"][:55]}')
                print(f'    {violations[0][2]}')
                continue
            pending.append(entry)
            seen.add(j['id'])
        PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PENDING_FILE, 'w') as f:
            json.dump(pending, f, indent=2)
        print(f'  [pending] Saved {len(pending)} job(s) to {PENDING_FILE}')

    if new_jobs:
        followed_matches = [j for j in new_jobs if is_followed_company(j['company'], followed_companies)]
        if followed_matches:
            print(f'  [alerts] Sending {len(followed_matches)} followed-company alert(s)')
            for job in followed_matches:
                send_followed_company_webhook_alert(job)
                time.sleep(0.3)

        listings_file = Path('listings.json')

        if PENDING_FILE is None:
            for job in to_list:
                add_job_directly(job, listings_file, rebuild=False)
                seen.add(job['id'])
                time.sleep(0.5)

            if to_list:
                result = subprocess.run(
                    ['python3', '.github/scripts/rebuild_readme.py'],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f'  [direct] rebuild_readme.py failed: {result.stderr[:200]}')
                else:
                    print(f'  [direct] README rebuilt ({len(to_list)} job(s) added)')

    save_seen_jobs(seen)
    save_title_cache()
    if _claude_usage_dirty:
        save_claude_usage()
    print(f'Board group: {BOARD_GROUP or "all"} | Claude: {_claude_calls_this_run} this run, '
          f'{_claude_calls_today} in {CLAUDE_USAGE_FILE.name}, '
          f'{_total_claude_calls_today()} today all groups (single-pass+cache)')
    print('Done')

if __name__ == '__main__':
    main()
