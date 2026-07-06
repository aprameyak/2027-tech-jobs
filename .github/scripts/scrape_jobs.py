#!/usr/bin/env python3
"""
Scrapes Greenhouse, Lever, and Ashby job boards for intern/new grad positions.
Opens GitHub issues for new matches that haven't been seen before.
"""

import json
import os
import time
import requests
import yaml
from pathlib import Path

SEEN_JOBS_FILE = Path('.github/data/seen_jobs.json')

INTERN_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop',
    'new grad', 'new-grad', 'entry level', 'entry-level',
    'early career', '2027', 'associate'
]

# US location signals — broad enough to catch most postings
US_SIGNALS = [
    'united states', 'usa', 'u.s.', 'remote', 'new york', 'san francisco',
    'seattle', 'boston', 'austin', 'chicago', 'los angeles', 'denver',
    'atlanta', 'miami', 'dallas', 'raleigh', 'washington', ', ny', ', ca',
    ', wa', ', ma', ', tx', ', il', ', pa', ', co', ', ga', ', fl', ', nc',
    ', va', ', dc', ', nj', ', oh', ', mn', ', az', 'hybrid'
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


def is_relevant_title(title):
    t = title.lower()
    return any(kw in t for kw in INTERN_KEYWORDS)


def is_us_location(location):
    if not location:
        return True  # no location = assume open/US
    loc = location.lower()
    if any(s in loc for s in US_SIGNALS):
        return True
    # Reject obviously non-US
    non_us = ['london', 'toronto', 'berlin', 'paris', 'sydney', 'singapore',
              'dublin', 'amsterdam', 'india', 'canada', 'uk ', 'u.k.']
    return not any(s in loc for s in non_us)


def infer_listing_type(title):
    t = title.lower()
    if any(kw in t for kw in ['new grad', 'new-grad', 'entry level', 'entry-level', 'early career', 'associate']):
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
                    'location': location or 'United States',
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
                    'location': location or 'United States',
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
                    'location': location or 'United States',
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

- [x] The role is in the United States, Canada, or is Remote.
- [x] The application link is publicly accessible (no login required to view the posting).
- [x] I checked that this listing does not already exist in the repository.
- [x] The information I provided is accurate to the best of my knowledge.
"""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    payload = {
        'title': title,
        'body': body,
        'labels': ['new listing', 'needs review', 'auto-discovered'],
    }
    resp = requests.post(
        f'https://api.github.com/repos/{repo}/issues',
        json=payload,
        headers=headers,
        timeout=10,
    )
    if resp.status_code == 201:
        print(f'  Created issue: {title}')
    else:
        print(f'  Failed to create issue ({resp.status_code}): {resp.text[:200]}')


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
                print(f'  - {job["company"]}: {job["title"]} ({job["url"]})')
        else:
            for job in new_jobs:
                create_github_issue(job, token, repo)
                time.sleep(1)

    save_seen_jobs(seen)
    print('Done')


if __name__ == '__main__':
    main()
