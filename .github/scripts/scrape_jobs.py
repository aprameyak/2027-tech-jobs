#!/usr/bin/env python3

import json
import os
import re
import time
from datetime import datetime
import requests
import yaml
from pathlib import Path

SEEN_JOBS_FILE = Path('.github/data/seen_jobs.json')
TITLE_CACHE_FILE = Path('.github/data/title_classifications.json')
GEMINI_USAGE_FILE = Path('.github/data/gemini_usage.json')

GEMINI_DAILY_LIMIT = 1400
GEMINI_RPM_DELAY = 4.2

_title_cache = None
_gemini_calls_today = 0
_gemini_usage_date = None

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
    'firmware', 'robotics', 'computer', 'computational', 'algorithm', 'applied',
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


def classify_with_gemini(title):
    global _gemini_calls_today

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return None

    if _gemini_calls_today >= GEMINI_DAILY_LIMIT:
        print(f'  [Gemini] Daily limit reached ({GEMINI_DAILY_LIMIT}), using keyword fallback')
        return None

    prompt = (
        'You are a classifier for a tech job board targeting CS/software/data/quant/PM students. '
        'Decide if this job title is relevant for them.\n\n'
        'Answer YES for: software engineering, data science/engineering/analytics, '
        'machine learning/AI, quantitative research/trading, product management, '
        'product development, cybersecurity, DevOps/SRE, embedded/firmware engineering, '
        'computer science research, technical program management, mobile/iOS/Android, '
        'cloud/infrastructure, hardware/VLSI design (chip-level), computer vision, NLP, '
        'technology consulting, digital technology, IT, business analyst (data/tech-focused), '
        'technology analyst, solutions engineering, sales engineering, technical support engineering, '
        'network engineering, systems engineering (software/IT), financial engineering/fintech, '
        'robotics (software), simulation engineering.\n\n'
        'Answer NO for: manufacturing/process/chemical/mechanical/electrical engineering (non-chip), '
        'HR, supply chain, clinical/life science research (non-ML), '
        'non-quant finance/accounting, legal, operations (non-technical), '
        'audit, compliance, tax, logistics, warehouse, facilities, shipping/receiving.\n\n'
        'When uncertain, err on the side of YES. It is better to include a borderline role '
        'for human review than to miss a legitimate tech opportunity.\n\n'
        f'Job title: "{title}"\n\n'
        'Reply with exactly one word — yes or no. No punctuation, no explanation.'
    )

    try:
        resp = requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}',
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0.0,
                    'maxOutputTokens': 3,
                    'topK': 1,
                    'topP': 1.0,
                },
            },
            headers={'Content-Type': 'application/json'},
            timeout=15,
        )
        _gemini_calls_today += 1
        time.sleep(GEMINI_RPM_DELAY)

        if resp.status_code != 200:
            print(f'  [Gemini] HTTP {resp.status_code}')
            return None

        if resp.status_code == 429:
            print('  [Gemini] Rate limited (429) — using keyword fallback for remainder of run')
            _gemini_calls_today = GEMINI_DAILY_LIMIT
            return None

        try:
            body = resp.json()
        except Exception:
            print('  [Gemini] Non-JSON response — using keyword fallback')
            return None

        try:
            text = (
                body.get('candidates', [{}])[0]
                .get('content', {})
                .get('parts', [{}])[0]
                .get('text', '')
                .strip()
                .lower()
            )
        except (IndexError, AttributeError, TypeError):
            print('  [Gemini] Unexpected response shape — using keyword fallback')
            return None

        if not text:
            print('  [Gemini] Empty response text — using keyword fallback')
            return None
        if text.startswith('y'):
            return True
        if text.startswith('n'):
            return False
        clean = text.strip('.,!? ')
        if clean == 'yes':
            return True
        if clean == 'no':
            return False
        print(f'  [Gemini] Unexpected response: {text!r} — using keyword fallback')
        return None
    except requests.exceptions.Timeout:
        print('  [Gemini] Request timed out — using keyword fallback')
        return None
    except Exception as e:
        print(f'  [Gemini] Error: {e} — using keyword fallback')
        return None


def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen):
    SEEN_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_JOBS_FILE, 'w') as f:
        json.dump(sorted(list(seen)), f, indent=2)


def is_tech_title_keywords(title):
    t = title.lower()
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False
    return any(kw in t for kw in TECH_KEYWORDS)


def classify_title(title):
    t = title.lower()

    # Hard reject: definitively non-tech titles, no Gemini needed
    if any(s in t for s in HARD_REJECT_SIGNALS):
        return False, True

    cache = load_title_cache()
    if t in cache:
        return cache[t], True

    result = classify_with_gemini(title)
    if result is not None:
        cache[t] = result
        return result, True

    # Gemini unavailable — use keyword heuristic but DO NOT cache the result
    # so Gemini can retry on the next run. Borderline (no tech keywords) still
    # passes through as unconfident so the scraper can decide to include it.
    has_tech_keywords = is_tech_title_keywords(title)
    return has_tech_keywords, False


def is_relevant_title(title):
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
    if any(kw in t for kw in ['new grad', 'new-grad', 'entry level', 'entry-level', 'early career']):
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
    if any(kw in t for kw in ['phd', 'phd student', 'phd intern', 'phd research', 'phd early career']):
        return 'PhD'
    if any(kw in t for kw in ['master', 'ms ', 'm.s.', 'masters']):
        return "Master's"
    # Default to Undergrad
    return 'Undergrad'


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
            relevant, confident = is_relevant_title(title)
            if relevant and is_us_location(location):
                jobs.append({
                    'id': f'greenhouse_{slug}_{job["id"]}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': job.get('absolute_url', ''),
                    'board': 'Greenhouse',
                    'confident': confident,
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
            relevant, confident = is_relevant_title(title)
            if relevant and is_us_location(location):
                jobs.append({
                    'id': f'lever_{slug}_{job["id"]}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': job.get('hostedUrl', ''),
                    'board': 'Lever',
                    'confident': confident,
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
            relevant, confident = is_relevant_title(title)
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
                    'confident': confident,
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

                relevant, confident = is_relevant_title(title)
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
                        'confident': confident,
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

            relevant, confident = is_relevant_title(title)
            if relevant:
                job_id = job.get('shortcode', job.get('id', ''))
                jobs.append({
                    'id': f'workable_{slug}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': f'https://apply.workable.com/{slug}/j/{job_id}/',
                    'board': 'Workable',
                    'confident': confident,
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

            relevant, confident = is_relevant_title(title)
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
                    'confident': confident,
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

            relevant, confident = is_relevant_title(title)
            if relevant:
                job_id = job.get('id', '')
                jobs.append({
                    'id': f'pinpoint_{slug}_{job_id}',
                    'company': company,
                    'title': title,
                    'location': location,
                    'url': f'https://{slug}.pinpointhq.com/postings/{job_id}',
                    'board': 'Pinpoint',
                    'confident': confident,
                })
        return jobs
    except Exception as e:
        print(f'  [{company}] Pinpoint error: {e}')
        return []


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

    # Search for each term separately — Workday doesn't support OR queries
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
                    relevant, confident = is_relevant_title(title)
                    if relevant and is_us_location(location):
                        jobs.append({
                            'id': f'workday_{tenant}_{external_path}',
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': f'{base_url}{external_path}',
                            'board': 'Workday',
                            'confident': confident,
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
                relevant, confident = is_relevant_title(title)
                if relevant and is_us_location(location):
                    jobs.append({
                        'id': f'linkedin_{job_id}',
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': url,
                        'board': 'LinkedIn',
                        'confident': confident,
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

                relevant, confident = is_relevant_title(title)
                if relevant and is_us_location(location):
                    jobs.append({
                        'id': f'amazon_{job_id}',
                        'company': 'Amazon',
                        'title': title,
                        'location': location,
                        'url': url,
                        'board': 'Amazon Jobs',
                        'confident': confident,
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


def scrape_apple():
    url = 'https://jobs.apple.com/api/role/search'
    headers = {
        **HEADERS,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Referer': 'https://jobs.apple.com/',
    }

    queries = ['intern', 'new grad', 'university']
    seen_ids = set()
    jobs = []

    for query in queries:
        page = 1
        while True:
            payload = {
                'filters': {
                    'postingpostLocation': ['postLocation-USA'],
                },
                'page': page,
                'locale': 'en-us',
                'query': query,
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code != 200:
                    print(f'  [Apple] HTTP {resp.status_code} for query "{query}"')
                    break
                data = resp.json()
                results = data.get('searchResults', [])
                if not results:
                    break
                for job in results:
                    job_id = str(job.get('positionId', job.get('id', '')))
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    title = job.get('postingTitle', '')
                    external_path = job.get('externalPath', '')
                    loc_list = job.get('locations', [])
                    location = loc_list[0].get('name', '') if loc_list else ''
                    apply_url = f'https://jobs.apple.com/en-us/details/{job_id}{external_path}' if job_id else ''

                    relevant, confident = is_relevant_title(title)
                    if relevant:
                        jobs.append({
                            'id': f'apple_{job_id}',
                            'company': 'Apple',
                            'title': title,
                            'location': location,
                            'url': apply_url,
                            'board': 'Apple Jobs',
                            'confident': confident,
                        })

                total_pages = data.get('totalPages', 1)
                if page >= total_pages:
                    break
                page += 1
                time.sleep(0.5)
            except Exception as e:
                print(f'  [Apple] Error for query "{query}": {e}')
                break

    return jobs


def create_github_issue(job, token, repo):
    listing_type, season = infer_listing_type(job['title'])
    confident = job.get('confident', True)
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

    with open('companies.yml') as f:
        config = yaml.safe_load(f)

    seen = load_seen_jobs()
    new_jobs = []

    scrapers = {
        'greenhouse': scrape_greenhouse,
        'lever': scrape_lever,
        'ashby': scrape_ashby,
    }

    def process_jobs(jobs):
        for job in jobs:
            job_id = job['id']
            if job_id not in seen:
                seen.add(job_id)
                print(f'  NEW: {job["title"]} @ {job["location"]}')
                new_jobs.append(job)

    for board, scraper in scrapers.items():
        for entry in config.get(board, []):
            company = entry['name']
            slug = entry['slug']
            print(f'Checking {company} ({board}/{slug})...')
            process_jobs(scraper(company, slug))
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
            process_jobs(scraper(company, slug))
            time.sleep(0.4)

    for entry in config.get('workday', []):
        company = entry['name']
        tenant = entry['tenant']
        instance = entry['instance']
        board = entry.get('board', '')
        print(f'Checking {company} (workday/{tenant})...')
        process_jobs(scrape_workday(company, tenant, instance, board))
        time.sleep(0.4)

    for entry in config.get('linkedin', []):
        company = entry['name']
        company_id = str(entry['company_id'])
        print(f'Checking {company} (LinkedIn via Apify)...')
        process_jobs(scrape_linkedin_apify(company, company_id))

    print('Checking Amazon (amazon.jobs)...')
    process_jobs(scrape_amazon())
    time.sleep(0.4)

    print('Checking Apple (jobs.apple.com)...')
    process_jobs(scrape_apple())

    print(f'\nFound {len(new_jobs)} new job(s)')

    if new_jobs:
        token = os.environ.get('GITHUB_TOKEN')
        repo = os.environ.get('GITHUB_REPOSITORY')
        if not token or not repo:
            print('ERROR: GITHUB_TOKEN or GITHUB_REPOSITORY not set')
            for job in new_jobs:
                print(f'  - {job["company"]}: {job["title"]} | {job["location"]} | {job["url"]}')
        else:
            for job in new_jobs:
                create_github_issue(job, token, repo)
                time.sleep(1)

    save_seen_jobs(seen)
    save_title_cache()
    save_gemini_usage()
    print(f'Gemini calls today: {_gemini_calls_today}')
    print('Done')


if __name__ == '__main__':
    main()
