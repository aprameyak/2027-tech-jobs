#!/usr/bin/env python3
"""
Scrapes Greenhouse, Lever, and Ashby job boards for intern/new grad positions.
Opens GitHub issues for new matches that haven't been seen before.
"""

import json
import os
import re
import time
import requests
import yaml
from pathlib import Path

SEEN_JOBS_FILE = Path('.github/data/seen_jobs.json')

# Keywords matched with word boundaries (avoids "internal", "international", "internals")
BOUNDARY_KEYWORDS = [r'\bintern\b', r'\binternship\b', r'\bco-op\b', r'\bcoop\b']

# Keywords safe for substring matching
SUBSTRING_KEYWORDS = [
    'new grad', 'new-grad', 'entry level', 'entry-level', 'early career', '2027',
]

# Title must contain at least one of these to be considered a tech role
TECH_KEYWORDS = [
    'software', 'engineer', 'engineering', 'developer', 'data', 'machine learning',
    'ml', 'ai ', ' ai', 'artificial intelligence', 'research', 'researcher',
    'quantitative', 'quant', 'infrastructure', 'devops', 'platform', 'backend',
    'frontend', 'front-end', 'back-end', 'fullstack', 'full-stack', 'mobile',
    'ios', 'android', 'cloud', 'security', 'cybersecurity', 'network', 'systems',
    'database', 'analytics', 'product', 'sre', 'reliability', 'embedded',
    'firmware', 'robotics', 'computer', 'computational', 'algorithm', 'applied',
    'technical', 'scientist', 'physics', 'math', 'statistics', 'fintech',
]

# Location must match at least one of these to be considered North America (US or Canada)
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
    # Canada
    'toronto', 'vancouver', 'montreal', 'ottawa', 'calgary', 'canada',
    ', on', ', bc', ', qc', ', ab',
]

# If any of these appear, it's definitely not North America — skip even if US signal present
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


def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        with open(SEEN_JOBS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen):
    SEEN_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_JOBS_FILE, 'w') as f:
        json.dump(sorted(list(seen)), f, indent=2)


def is_tech_title(title):
    t = title.lower()
    return any(kw in t for kw in TECH_KEYWORDS)


def is_relevant_title(title):
    t = title.lower()
    if not is_tech_title(title):
        return False
    if any(re.search(kw, t) for kw in BOUNDARY_KEYWORDS):
        return True
    return any(kw in t for kw in SUBSTRING_KEYWORDS)


def is_us_location(location):
    """Return True if location is in the US, Canada, or unqualified Remote."""
    if not location or location.strip() == '':
        return False  # Skip unknown locations to avoid non-US noise

    loc = location.lower()

    # Immediately reject known non-US locations
    if any(s in loc for s in NON_US_SIGNALS):
        return False

    # Accept if clearly Remote with no country qualifier
    if loc.strip() in ('remote', 'remote (us)', 'us remote', 'remote - us',
                       'remote, us', 'remote, usa', 'work from home',
                       'remote (canada)', 'canada remote', 'remote, canada'):
        return True

    # Accept if it contains a US signal
    return any(s in loc for s in US_SIGNALS)


def infer_listing_type(title):
    t = title.lower()
    if any(kw in t for kw in ['new grad', 'new-grad', 'entry level', 'entry-level', 'early career']):
        return 'New Grad (Full-Time)', '2027 (New Grad — no specific season)'
    return 'Internship', 'Summer 2027'


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
            if is_relevant_title(title) and is_us_location(location):
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
            if is_relevant_title(title) and is_us_location(location):
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
            if is_relevant_title(title) and is_us_location(location):
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


def create_github_issue(job, token, repo):
    listing_type, season = infer_listing_type(job['title'])
    title = f'[JOB] {job["company"]} — {job["title"]}'
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

Undergrad

### Direct Application Link

{job['url']}

### Application Deadline (Optional)

_No response_

### Additional Notes (Optional)

Auto-discovered via {job['board']} API.

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
            'title': title,
            'body': body,
            'labels': ['new listing', 'needs review', 'auto-discovered'],
        },
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 201:
        print(f'  Created issue: {title}')
    else:
        print(f'  Failed ({resp.status_code}): {resp.text[:200]}')


def main():
    with open('companies.yml') as f:
        config = yaml.safe_load(f)

    seen = load_seen_jobs()
    new_jobs = []

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
            jobs = scraper(company, slug)
            for job in jobs:
                if job['id'] not in seen:
                    print(f'  NEW: {job["title"]} @ {job["location"]}')
                    new_jobs.append(job)
                    seen.add(job['id'])
            time.sleep(0.4)

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
    print('Done')


if __name__ == '__main__':
    main()
