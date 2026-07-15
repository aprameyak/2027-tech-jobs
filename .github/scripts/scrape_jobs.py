#!/usr/bin/env python3

import json
import os
import re
import subprocess
import time
from datetime import datetime
import requests
import yaml
from pathlib import Path

SEEN_JOBS_FILE = Path('.github/data/seen_jobs.json')
TITLE_CACHE_FILE = Path('.github/data/title_classifications.json')
GEMINI_USAGE_FILE = Path('.github/data/gemini_usage.json')
FOLLOWED_COMPANIES_FILE = Path('.github/data/followed_companies.json')

GEMINI_DAILY_LIMIT = 1400
GEMINI_RPM_DELAY = 4.2
GEMINI_BATCH_SIZE = 40

_title_cache = None
_confidence_cache = {}
_gemini_calls_today = 0
_gemini_usage_date = None

DEFAULT_FOLLOWED_COMPANIES = [
    'Amazon',
    'Apple',
    'Databricks',
    'Google',
    'Meta',
    'Microsoft',
    'NVIDIA',
    'OpenAI',
    'Palantir',
    'Salesforce',
    'SpaceX',
    'Stripe',
    'Tesla',
    'Waymo',
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

HARD_REJECT_SIGNALS = [
    'manufacturing engineer', 'process engineer', 'chemical engineer',
    'mechanical engineer', 'materials engineer', 'materials scientist',
    'quality engineer', 'equipment engineer', 'industrial engineer',
    'environmental engineer', 'civil engineer', 'structural engineer',
    'electrical engineer', 'process integration', 'photolithography',
    'metrology', 'failure analysis', 'yield engineer', 'etch engineer',
    'human resources', 'recruiter', 'talent acquisition',
    'supply chain', 'procurement',
    'legal intern', 'paralegal', 'accounting intern',
    'logistics', 'warehouse', 'shipping', 'receiving', 'inventory',
    'facilities manager',
    'tax director', 'tax manager',
    'legal counsel', 'general counsel', 'legal operations',
]

US_SIGNALS = [
    'united states', 'usa', 'u.s.a', ', al', ', ak', ', az', ', ar',
    ', ca', ', co', ', ct', ', de', ', fl', ', ga', ', hi', ', id',
    ', il', ', in', ', ia', ', ks', ', ky', ', la', ', me', ', md',
    ', ma', ', mi', ', mn', ', ms', ', mo', ', mt', ', ne', ', nv',
    ', nh', ', nj', ', nm', ', ny', ', nc', ', nd', ', oh', ', ok',
    ', or', ', pa', ', ri', ', sc', ', sd', ', tn', ', tx', ', ut',
    ', vt', ', va', ', wa', ', wv', ', wi', ', wy', ', dc',
    'new york', 'san francisco', 'los angeles', 'seattle', 'boston',
    'chicago', 'austin', 'denver', 'atlanta', 'miami', 'dallas',
    'raleigh', 'washington d', 'menlo park', 'palo alto', 'mountain view',
    'san jose', 'redwood city', 'bellevue', 'portland',
    'toronto', 'vancouver', 'montreal', 'ottawa', 'calgary', 'canada',
    ', on', ', bc', ', qc', ', ab',
]

NON_US_SIGNALS = [
    'london', 'united kingdom', ', uk', '(uk)', 'u.k.',
    'berlin', 'munich', 'frankfurt', 'germany',
    'paris', 'france',
    'amsterdam', 'netherlands',
    'dublin', 'ireland',
    'sydney', 'melbourne', 'australia',
    'singapore',
    'bangalore', 'india',
    'tokyo', 'japan',
    'beijing', 'shanghai', 'china',
    'tel aviv', 'israel',
    'mexico city', 'mexico',
    'brazil', 'sao paulo',
    'worldwide', 'global (non-us)',
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
    """
    Convert ATS-style location strings to City, ST / City, Province format.
    Handles semicolon-separated multi-locations, bare city names, and
    US, State, City ordering from Workday.
    """
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

        m = re.match(r'^(.+),\s*([^,]+),\s*USA$', part, re.I)
        if m:
            city, region = m.group(1).strip(), m.group(2).strip().lower()
            abbr = US_STATE_ABBRS.get(region)
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
                    _title_cache = {k: bool(v) for k, v in data.items() if isinstance(k, str)}
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
            with open(TITLE_CACHE_FILE, 'w') as f:
                json.dump(_title_cache, f, indent=2)
        except Exception as e:
            print(f'  [Cache] Failed to save title cache: {e}')


def load_gemini_usage():
    global _gemini_calls_today, _gemini_usage_date
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        if GEMINI_USAGE_FILE.exists():
            with open(GEMINI_USAGE_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get('date') == today:
                _gemini_calls_today = int(data.get('calls', 0))
                _gemini_usage_date = today
                return
    except Exception as e:
        print(f'  [Gemini] Failed to load usage file: {e} — starting fresh')
    _gemini_calls_today = 0
    _gemini_usage_date = today


def save_gemini_usage():
    try:
        GEMINI_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GEMINI_USAGE_FILE, 'w') as f:
            json.dump({'date': _gemini_usage_date, 'calls': _gemini_calls_today}, f)
    except Exception as e:
        print(f'  [Gemini] Failed to save usage file: {e}')


def batch_classify_with_gemini(titles):
    """
    Classify up to GEMINI_BATCH_SIZE titles in a single Gemini call.

    Returns dict mapping title_lower -> {"is_tech": bool, "confidence": "high"|"medium"|"low"}.
    Returns {} on any failure so callers can fall back to keywords.
    Handles 429 with exponential backoff (3 attempts: 15s, 30s, 60s).
    Uses responseMimeType=application/json for reliable structured output.
    """
    global _gemini_calls_today

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key or _gemini_calls_today >= GEMINI_DAILY_LIMIT:
        return {}

    numbered = '\n'.join(f'{i + 1}. "{t}"' for i, t in enumerate(titles))
    prompt = (
        'You are a classifier for a tech job board targeting CS/software/data/quant/PM students.\n\n'
        'For each job title return:\n'
        '- "is_tech": true for software/data/ML/AI/quant/PM/cybersecurity/DevOps/SRE/cloud/mobile/'
        'embedded/firmware/robotics/technical-PM/IT/business-analyst(tech)/solutions-engineering/'
        'network-engineering/fintech/chip-design. '
        'false for manufacturing/process/chemical/mechanical/electrical engineering (non-chip), '
        'HR, supply chain, clinical research (non-ML), non-quant finance/accounting, legal, '
        'non-technical operations, logistics, facilities.\n'
        '- "confidence": "high" (clearly one way), "medium", or "low" (genuinely ambiguous — '
        'set is_tech true and flag low so a human reviews it)\n\n'
        f'Titles:\n{numbered}\n\n'
        f'Return a JSON array of exactly {len(titles)} objects in the same order.'
    )

    for attempt in range(3):
        try:
            resp = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}',
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'temperature': 0.0,
                        'maxOutputTokens': len(titles) * 25 + 128,
                        'responseMimeType': 'application/json',
                    },
                },
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )

            if resp.status_code == 429:
                wait = (2 ** attempt) * 15
                print(f'  [Gemini] 429 rate limit — waiting {wait}s (attempt {attempt + 1}/3)')
                time.sleep(wait)
                continue

            _gemini_calls_today += 1
            time.sleep(GEMINI_RPM_DELAY)

            if resp.status_code != 200:
                print(f'  [Gemini] HTTP {resp.status_code}')
                return {}

            body = resp.json()
            text = (
                body.get('candidates', [{}])[0]
                .get('content', {})
                .get('parts', [{}])[0]
                .get('text', '')
            )
            results = json.loads(text)

            if not isinstance(results, list) or len(results) != len(titles):
                print(f'  [Gemini] Expected {len(titles)} results, got '
                      f'{len(results) if isinstance(results, list) else type(results).__name__}')
                return {}

            return {titles[i].lower(): results[i] for i in range(len(titles))}

        except json.JSONDecodeError as e:
            print(f'  [Gemini] JSON parse error: {e}')
            return {}
        except requests.exceptions.Timeout:
            print(f'  [Gemini] Timeout (attempt {attempt + 1}/3)')
            if attempt < 2:
                time.sleep(5)
        except Exception as e:
            print(f'  [Gemini] Error: {e}')
            return {}

    return {}


def classify_titles_batch(title_list):
    """
    Classify all titles in title_list that are not already cached, in batches.
    Updates _title_cache and _confidence_cache in-place.
    Returns the number of titles newly classified.
    """
    global _confidence_cache

    cache = load_title_cache()

    seen_lower = set()
    uncached = []
    for t in title_list:
        tl = t.lower()
        if tl in seen_lower or tl in cache:
            continue
        if any(s in tl for s in HARD_REJECT_SIGNALS):
            cache[tl] = False
            _confidence_cache[tl] = 'high'
            seen_lower.add(tl)
            continue
        seen_lower.add(tl)
        uncached.append(t)

    if not uncached:
        return 0

    print(f'  [Gemini] Batch-classifying {len(uncached)} uncached titles '
          f'({len(uncached) // GEMINI_BATCH_SIZE + 1} call(s))...')
    classified = 0

    for i in range(0, len(uncached), GEMINI_BATCH_SIZE):
        if _gemini_calls_today >= GEMINI_DAILY_LIMIT:
            print(f'  [Gemini] Daily limit reached — {len(uncached) - i} titles unclassified')
            break
        batch = uncached[i:i + GEMINI_BATCH_SIZE]
        results = batch_classify_with_gemini(batch)
        for title in batch:
            result = results.get(title.lower())
            if result is not None:
                cache[title.lower()] = bool(result.get('is_tech', False))
                _confidence_cache[title.lower()] = result.get('confidence', 'medium')
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
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code not in (200, 201, 202, 204):
            print(f'  [alerts] webhook failed ({resp.status_code}): {resp.text[:200]}')
    except Exception as e:
        print(f'  [alerts] webhook error: {e}')


def is_tech_title_keywords(title):
    t = title.lower()
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False
    return any(kw in t for kw in TECH_KEYWORDS)


def classify_title(title):
    """
    Returns (is_tech: bool, confident: bool).
    Checks cache first (populated by classify_titles_batch in main).
    Falls back to single-title Gemini call if cache missed, then keyword heuristic.
    """
    t = title.lower()

    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False, True

    cache = load_title_cache()
    if t in cache:
        confidence = _confidence_cache.get(t, 'high')
        return cache[t], confidence != 'low'

    try:
        results = batch_classify_with_gemini([title])
        if results and t in results:
            result = results[t]
            is_tech = bool(result.get('is_tech', False))
            confidence = result.get('confidence', 'medium')
            cache[t] = is_tech
            _confidence_cache[t] = confidence
            return is_tech, confidence != 'low'
    except Exception:
        pass

    return is_tech_title_keywords(title), False


def is_candidate_title(title):
    """
    Fast keyword-only pre-filter used during the scraping pass (no Gemini calls).
    Accepts any title with intern/grad boundary signals that isn't a hard reject.
    Gemini will verify tech relevance in the batch classification pass.
    """
    t = title.lower()
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False
    if any(re.search(kw, t) for kw in BOUNDARY_KEYWORDS):
        return True
    if any(kw in t for kw in SUBSTRING_KEYWORDS):
        return True
    return False


def is_relevant_title(title):
    """Full classification: checks is_tech (via cache/Gemini) + boundary keywords."""
    is_tech, confident = classify_title(title)
    if not is_tech:
        return False, confident
    t = title.lower()
    if any(re.search(kw, t) for kw in BOUNDARY_KEYWORDS):
        return True, confident
    if any(kw in t for kw in SUBSTRING_KEYWORDS):
        return True, confident
    return False, confident


def is_us_location(location):
    if not location or location.strip() == '':
        return False

    loc = location.lower()

    if any(s in loc for s in NON_US_SIGNALS):
        return False

    if loc.strip() in ('remote', 'remote (us)', 'us remote', 'remote - us',
                       'remote, us', 'remote, usa', 'work from home',
                       'remote (canada)', 'canada remote', 'remote, canada'):
        return True

    return any(s in loc for s in US_SIGNALS)


def infer_listing_type(title):
    t = title.lower()
    if any(kw in t for kw in [
        'new grad', 'new-grad', 'entry level', 'entry-level', 'early career',
        'university graduate', 'new college grad', 'college grad',
        'full-time', ' full time',
    ]):
        return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'
    if any(kw in t for kw in ['co-op', 'coop', 'co op']):
        return 'Internship', 'Co-op'
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
    return 'Internship', 'Summer 2027'


def infer_education_level(title):
    t = title.lower()
    if any(kw in t for kw in ['phd', 'ph.d', 'phd student', 'phd intern', 'phd research', 'phd early career']):
        return 'PhD'
    if any(kw in t for kw in ['master', 'ms ', 'm.s.', 'masters', 'meng', 'm.eng']):
        return 'Masters'
    return 'Undergrad'


def add_job_directly(job, listings_file, readme_file):
    """
    Add a high-confidence job directly to listings.json and rebuild the README.
    Skips if the URL already exists in listings.json.
    """
    try:
        listing_type, season = infer_listing_type(job['title'])
        education = infer_education_level(job['title'])
        location = normalize_location(job.get('location', ''))

        table = 'summer'
        if listing_type == 'New Grad (Full-Time)':
            table = 'newgrad'
        elif season in ('Co-op', 'Fall 2027', 'Spring 2027', 'Winter 2027',
                        'Fall 2026', 'Spring 2026', 'Winter 2026', 'Summer 2026'):
            table = 'offcycle'

        entry = {
            'company': job['company'],
            'role': job['title'],
            'location': location,
            'type': table,
            'season': season,
            'education': education,
            'url': job['url'],
            'sponsorship': 'Unknown',
            'citizenship': 'Unknown',
            'date_added': datetime.now().strftime('%Y-%m-%d'),
        }

        listings_path = listings_file
        if listings_path.exists():
            with open(listings_path) as f:
                listings = json.load(f)
        else:
            listings = []

        def _norm_url(u):
            u = u.split('?')[0].rstrip('/')
            import re
            u = re.sub(r'(myworkdayjobs\.com)/en-[A-Z]{2}/[^/]+/job/', r'\1/job/', u)
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
        resp = requests.get(url, timeout=10, headers=HEADERS)
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
        resp = requests.get(url, timeout=10, headers=HEADERS)
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
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            print(f'  [{company}] Ashby HTTP {resp.status_code}')
            return []
        jobs = []
        for job in resp.json().get('jobPostings', []):
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
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
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
                    ref = job.get('ref', f'https://jobs.smartrecruiters.com/{identifier}/{job_id}')
                    jobs.append({
                        'id': f'smartrecruiters_{identifier}_{job_id}',
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': ref,
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
        resp = requests.get(url, headers=HEADERS, timeout=10)
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
        resp = requests.get(url, headers=HEADERS, timeout=10)
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
        resp = requests.get(url, headers=HEADERS, timeout=10)
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
    """
    Build a canonical Workday job URL from known-good components.

    The Workday API returns `externalPath` inconsistently across tenants:
      - Some return: /en-US/BoardName/job/Location/Title_ID
      - Some return: /job/Location/Title_ID          (no locale or board)
      - Some return: /en-GB/BoardName/job/...        (wrong locale)

    Strategy: strip any locale+board prefix that the API may have included,
    leaving a bare /job/... path, then prepend our authoritative board from
    companies.yml. This guarantees the URL is always valid regardless of
    what the API happens to return.
    """
    path = re.sub(r'^/[a-z]{2}-[A-Z]{2}/[^/]+(?=/job/)', '', external_path)
    if not path.startswith('/job/'):
        path = external_path
    if board:
        return f'{base_url}/en-US/{board}{path}'
    return f'{base_url}{path}'


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

    for search_term in ['intern', 'new grad', 'early career', 'university']:
        offset = 0
        while True:
            payload = {
                'appliedFacets': {},
                'limit': 20,
                'offset': offset,
                'searchText': search_term,
            }
            try:
                resp = requests.post(api_url, json=payload, headers=wd_headers, timeout=10)
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
                    location = job.get('locationsText', '')
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
                if offset >= total:
                    break
                time.sleep(0.3)
            except Exception as e:
                print(f'  [{company}] Workday error for "{search_term}": {e}')
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
                params={'token': apify_token, 'timeout': 120},
                json={'searchUrl': search_url, 'count': 15},
                timeout=150,
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
            resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
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




def create_github_issue(job, token, repo):
    listing_type, season = infer_listing_type(job['title'])
    confident = job.get('confident', False)
    issue_title = f'[JOB] {job["company"]} — {job["title"]}'

    if confident:
        labels = ['new listing', 'auto-discovered']
        notes = f'Auto-discovered via {job["board"]} API.'
    else:
        labels = ['new listing', 'needs-review']
        notes = (
            f'Auto-discovered via {job["board"]} API. '
            f'**Needs manual review** — Gemini was unavailable so this was classified by keyword matching only. '
            f'Please verify this is a legitimate tech role before approving.'
        )
    body = f"""### Company Name

{job['company']}

### Role / Job Title

{job['title']}

### Listing Type

{listing_type}

### Season / Term

{season}

### Location

{job['location']}

### Visa Sponsorship?

Unknown

### U.S. Citizenship Required?

No

### Education Level

{infer_education_level(job['title'])}

### Direct Application Link

{job['url']}

### Application Deadline (Optional)

_No response_

### Additional Notes (Optional)

{notes}

### Checklist

- [x] The role is in the United States, Canada, or is Remote (North America).
- [x] The application link is publicly accessible (no login required to view the posting).
- [x] I checked that this listing does not already exist in the repository.
- [x] The information I provided is accurate to the best of my knowledge.
"""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    resp = requests.post(
        f'https://api.github.com/repos/{repo}/issues',
        json={
            'title': issue_title,
            'body': body,
            'labels': labels,
        },
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 201:
        review_flag = '' if confident else ' [NEEDS REVIEW]'
        print(f'  Created issue{review_flag}: {issue_title}')
    else:
        print(f'  Failed ({resp.status_code}): {resp.text[:200]}')


def main():
    load_gemini_usage()

    try:
        with open('companies.yml') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f'ERROR: Failed to load companies.yml: {e}')
        return

    seen = load_seen_jobs()
    followed_companies = load_followed_companies()

    candidate_jobs = []

    def collect_jobs(jobs):
        for job in jobs:
            if job['id'] not in seen:
                candidate_jobs.append(job)

    scrapers = {
        'greenhouse': scrape_greenhouse,
        'lever': scrape_lever,
        'ashby': scrape_ashby,
    }
    for board, scraper in scrapers.items():
        for entry in config.get(board, []):
            company = entry['name']
            slug = entry['slug']
            print(f'Checking {company} ({board}/{slug})...')
            try:
                collect_jobs(scraper(company, slug))
            except Exception as e:
                print(f'  [{company}] Scraper crashed: {e}')
            time.sleep(0.4)

    for board_key, scraper, slug_field in [
        ('smartrecruiters', scrape_smartrecruiters, 'identifier'),
        ('workable', scrape_workable, 'slug'),
        ('recruitee', scrape_recruitee, 'slug'),
        ('pinpoint', scrape_pinpoint, 'slug'),
    ]:
        for entry in config.get(board_key, []):
            company = entry['name']
            slug = entry[slug_field]
            print(f'Checking {company} ({board_key}/{slug})...')
            try:
                collect_jobs(scraper(company, slug))
            except Exception as e:
                print(f'  [{company}] Scraper crashed: {e}')
            time.sleep(0.4)

    for entry in config.get('workday', []):
        company = entry['name']
        tenant = entry['tenant']
        instance = entry['instance']
        board = entry.get('board', '')
        print(f'Checking {company} (workday/{tenant})...')
        try:
            collect_jobs(scrape_workday(company, tenant, instance, board))
        except Exception as e:
            print(f'  [{company}] Scraper crashed: {e}')
        time.sleep(0.4)

    for entry in config.get('linkedin', []):
        company = entry['name']
        company_id = str(entry['company_id'])
        print(f'Checking {company} (LinkedIn via Apify)...')
        try:
            collect_jobs(scrape_linkedin_apify(company, company_id))
        except Exception as e:
            print(f'  [{company}] Scraper crashed: {e}')

    print('Checking Amazon (amazon.jobs)...')
    try:
        collect_jobs(scrape_amazon())
    except Exception as e:
        print(f'  [Amazon] Scraper crashed: {e}')
    time.sleep(0.4)

    print(f'\nPass 1 complete: {len(candidate_jobs)} candidate job(s) to classify')

    if candidate_jobs:
        all_titles = [j['title'] for j in candidate_jobs]
        classified = classify_titles_batch(all_titles)
        print(f'  [Gemini] Classified {classified} new title(s); '
              f'{_gemini_calls_today} API call(s) used today')

    new_jobs = []
    for job in candidate_jobs:
        try:
            is_tech, confident = classify_title(job['title'])
        except Exception as e:
            print(f'  [classify] Error on "{job["title"]}": {e} — skipping')
            continue
        if is_tech:
            seen.add(job['id'])
            job['confident'] = confident
            new_jobs.append(job)
            flag = '' if confident else ' [NEEDS REVIEW]'
            print(f'  NEW{flag}: {job["title"]} @ {job["location"]}')

    print(f'\nFound {len(new_jobs)} new job(s)')

    if new_jobs:
        followed_matches = [j for j in new_jobs if is_followed_company(j['company'], followed_companies)]
        if followed_matches:
            print(f'  [alerts] Sending {len(followed_matches)} followed-company alert(s)')
            for job in followed_matches:
                send_followed_company_webhook_alert(job)
                time.sleep(0.3)

        listings_file = Path('listings.json')
        readme_file = Path('README.md')
        token = os.environ.get('GITHUB_TOKEN')
        repo = os.environ.get('GITHUB_REPOSITORY')

        high_confidence = [j for j in new_jobs if j.get('confident') == True]
        low_confidence = [j for j in new_jobs if j.get('confident') != True]

        for job in high_confidence:
            add_job_directly(job, listings_file, readme_file)
            time.sleep(0.5)

        if low_confidence:
            if not token or not repo:
                print('ERROR: GITHUB_TOKEN or GITHUB_REPOSITORY not set')
                for job in low_confidence:
                    print(f'  - {job["company"]}: {job["title"]} | {job["location"]} | {job["url"]}')
            else:
                for job in low_confidence:
                    try:
                        create_github_issue(job, token, repo)
                    except Exception as e:
                        print(f'  [issue] Failed to create issue for "{job["title"]}": {e}')
                    time.sleep(1)

    save_seen_jobs(seen)
    save_title_cache()
    save_gemini_usage()
    print(f'Gemini calls today: {_gemini_calls_today}')
    print('Done')


if __name__ == '__main__':
    main()
