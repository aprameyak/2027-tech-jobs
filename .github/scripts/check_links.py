#!/usr/bin/env python3

import json
import re
import subprocess
import time
from pathlib import Path

import requests

# Domains that are fully skipped — no check of any kind (returns always-alive).
# Use only when the site blocks all automated access AND has no usable API.
SKIP_ALL_DOMAINS = [
    'careers.ibm.com',
    'www.tesla.com',
    'tesla.com',
    'lockheedmartinjobs.com',
    'metacareers.com',
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

APPLY_BTN_PATTERN = re.compile(
    r'<a href="([^"]+)"[^>]*><img src="https://i\.imgur\.com/u1KNU8z\.png" width="118" alt="Apply"></a>'
)

WD_BARE = re.compile(r'^(https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com)/job/')

# Phrases that appear in page body when a job is closed (case-insensitive).
# Ordered from most specific to least — stop at first match.
SOFT_404_PHRASES = [
    # Apple Jobs (HTTP 200, body says role gone)
    'this role does not exist',
    'does not exist or is no longer available',
    'norolefound',
    # Workday
    'this position is no longer available',
    'this job is no longer available',
    'job requisition has been closed',
    # Greenhouse (HTML fallback)
    'job listing is no longer active',
    'this job is no longer accepting applications',
    # Lever (HTML fallback)
    'no longer accepting applications',
    'this posting is no longer accepting',
    # SmartRecruiters
    'this position has been filled',
    'position has been filled',
    # iCIMS
    'this position has closed',
    'position is closed',
    # Generic
    'this opportunity is no longer available',
    'this role is no longer available',
    'this role is no longer open',
    'application is closed',
    'posting has expired',
    'job has expired',
    'opening has been closed',
    # Generic soft-404 (custom career sites: Microsoft, Amazon, Google, etc.)
    'does not exist',
    "doesn't exist",
    'does not exist or is no longer available',
    'job not found',
    'posting not found',
    'position not found',
    'requisition not found',
    'could not be found',
    'unable to find this',
    'page not found',
    'sorry, this job',
    'sorry, this position',
    'sorry, this role',
    'no open positions',
    'job posting has expired',
    'role has been filled',
    'application period has ended',
    'the page you are looking for',
    'no longer exists',
]

# Host → Greenhouse board slug for embedded ?gh_jid= URLs
GH_HOST_BOARD = {
    'stripe.com': 'stripe',
    'nuro.ai': 'nuro',
    'instacart.careers': 'instacart',
    'databricks.com': 'databricks',
    'www.tower-research.com': 'towerresearchcapital',
    'www.boerboeltrading.com': 'boerboeltrading',
    'www.zipline.com': 'zipline',
    'www.ixl.com': 'ixllearning',
    'www.jumptrading.com': 'jumptrading',
    'www.quinstreet.com': 'quinstreet',
    'www.rentec.com': 'rentec',
    'www.oldmissioncapital.com': 'oldmissioncapital',
    'careers.appian.com': 'appian',
}

# ---------------------------------------------------------------------------
# ATS API helpers
# ---------------------------------------------------------------------------

def _gh_board_and_id(url):
    """Extract (board, job_id) from a Greenhouse URL, or (None, None)."""
    # job-boards.greenhouse.io/BOARD/jobs/JOB_ID
    m = re.search(r'(?:job-boards|boards)\.greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    if m:
        return m.group(1), m.group(2)
    # careers.COMPANY.com/...?gh_jid=JOB_ID  or  ...#gh_jid=JOB_ID
    m = re.search(r'[?&#]gh_jid=(\d+)', url)
    if m:
        # Board name is harder to get from the domain alone; skip API check
        return None, None
    return None, None


def check_greenhouse(url):
    """Return True if the job is still open, False if closed, None if unknown."""
    board, job_id = _gh_board_and_id(url)
    if not board or not job_id:
        return None
    return _gh_api_check(board, job_id)


def _gh_api_check(board, job_id):
    api = f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}'
    try:
        r = requests.get(api, timeout=10, headers=HEADERS)
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
    except Exception:
        pass
    return None


def load_greenhouse_boards():
    """Company name → Greenhouse board slug from companies.yml."""
    boards = {}
    section = None
    cur = None
    for line in Path('companies.yml').read_text().splitlines():
        if line.startswith('greenhouse:'):
            section = 'greenhouse'
            continue
        if line.endswith(':') and not line.startswith(' '):
            section = None
        if section != 'greenhouse':
            continue
        m = re.match(r'- name: (.+)', line)
        if m:
            cur = m.group(1).strip()
        if cur and line.strip().startswith('slug:'):
            boards[cur] = line.split('slug:', 1)[1].strip()
    return boards


def check_greenhouse_gh_jid(url, company=None, gh_boards=None):
    """Check embedded ?gh_jid= URLs on custom career sites."""
    m = re.search(r'[?&#]gh_jid=(\d+)', url)
    if not m:
        return None
    job_id = m.group(1)
    board = _gh_board_for_url(url, company, gh_boards)
    if board:
        return _gh_api_check(board, job_id)
    return None


def _gh_board_for_url(url, company=None, gh_boards=None):
    host = re.search(r'https?://([^/]+)', url)
    if not host:
        return None
    board = GH_HOST_BOARD.get(host.group(1).lower())
    if not board and gh_boards and company:
        board = gh_boards.get(company)
    return board


def check_greenhouse_careers_jobs(url, company=None, gh_boards=None):
    """Check Greenhouse /jobs/JOBID URLs on known career-site hosts."""
    m = re.search(r'://([^/]+)/jobs/(\d+)', url)
    if not m:
        return None
    host, job_id = m.group(1).lower(), m.group(2)
    board = GH_HOST_BOARD.get(host) or (
        gh_boards.get(company) if gh_boards and company else None
    )
    if board:
        return _gh_api_check(board, job_id)
    return None


def check_smartrecruiters(url):
    """Return True if open, False if closed, None if not a SmartRecruiters URL."""
    m = re.search(r'jobs\.smartrecruiters\.com/([^/]+)/(\d+)', url)
    if not m:
        return None
    company, job_id = m.group(1), m.group(2)
    api = f'https://api.smartrecruiters.com/v1/companies/{company}/postings/{job_id}'
    try:
        r = requests.get(api, timeout=10, headers=HEADERS)
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
    except Exception:
        pass
    return None


def _lever_company_and_id(url):
    """Extract (company, posting_id) from a Lever URL."""
    m = re.search(r'jobs(?:\.eu)?\.lever\.co/([^/]+)/([a-f0-9-]{36})', url)
    if m:
        return m.group(1), m.group(2)
    return None, None


def check_lever(url):
    """Return True if open, False if closed, None if unknown."""
    company, posting_id = _lever_company_and_id(url)
    if not company or not posting_id:
        return None
    api = f'https://api.lever.co/v0/postings/{company}/{posting_id}'
    try:
        r = requests.get(api, timeout=10, headers=HEADERS)
        if r.status_code == 200:
            data = r.json()
            # Lever returns the posting object; if it has an id it's live
            if data and data.get('id'):
                return True
            return False
        if r.status_code == 404:
            return False
    except Exception:
        pass
    return None


def _ashby_job_id(url):
    """Extract the UUID from an Ashby jobs URL."""
    m = re.search(
        r'jobs\.ashbyhq\.com/[^/]+/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
        url, re.I,
    )
    return m.group(1) if m else None


def check_ashby(url):
    """
    Return True if open, False if closed, None if unknown.
    Fetches the job page directly — Ashby renders job-not-found as a 404
    or injects a closed indicator into the HTML.
    """
    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers=HEADERS)
        if r.status_code == 404:
            return False
        if r.status_code == 200:
            body = r.text.lower()
            # Ashby closed-job indicators
            for phrase in [
                'this role is no longer accepting applications',
                'this role is closed',
                'job not found',
                'position is no longer available',
            ] + SOFT_404_PHRASES:
                if phrase in body:
                    print(f'    soft-404 detected: "{phrase}"')
                    return False
            return True
    except Exception as e:
        print(f'    ashby check error: {e}')
    return None


# ---------------------------------------------------------------------------
# Apple Jobs checker
# ---------------------------------------------------------------------------

def _apple_job_id(url):
    """Extract the numeric job ID from an Apple Jobs URL."""
    # https://jobs.apple.com/en-us/details/200636915-0836/slug
    m = re.search(r'/details/(\d+)', url)
    return m.group(1) if m else None


def check_apple(url):
    """
    Return True if open, False if closed, None if unable to determine.
    Uses Apple's role-search JSON API (empty results = gone). Falls back to
    HTML — Apple returns HTTP 200 with "this role does not exist" not 404.
    """
    job_id = _apple_job_id(url)
    if job_id:
        api = f'https://jobs.apple.com/api/role/search?id={job_id}&lang=en-us'
        try:
            r = requests.get(api, timeout=15, headers=HEADERS)
            if r.status_code == 200:
                results = r.json().get('searchResults', None)
                if results is not None:
                    return len(results) > 0 if results else False
            if r.status_code in (404, 410):
                return False
        except Exception as e:
            print(f'    apple api error: {e}')

    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers=HEADERS)
        if r.status_code in (404, 410):
            return False
        if r.status_code == 200:
            body = r.text.lower()
            for phrase in SOFT_404_PHRASES:
                if phrase in body:
                    print(f'    apple soft-404 detected: "{phrase}"')
                    return False
            if job_id and job_id in r.text:
                return True
    except Exception as e:
        print(f'    apple html error: {e}')
    return None


# ---------------------------------------------------------------------------
# Meta Careers checker
# ---------------------------------------------------------------------------

def _meta_job_id(url):
    m = re.search(r'/jobs/(\d+)', url)
    return m.group(1) if m else None


def check_meta(url):
    """
    Return True if open, False if closed, None if unable to determine.
    Meta soft-404s with page content (not HTTP 404). Bot-blocked fetches
    return None so we do not false-positive mark jobs dead.
    """
    job_id = _meta_job_id(url)
    if job_id:
        api = 'https://www.metacareers.com/graphql'
        payload = {
            'fb_api_caller_class': 'RelayModern',
            'variables': json.dumps({'job_id': job_id}),
            'doc_id': '7823148984374496',
        }
        try:
            r = requests.post(api, data=payload, timeout=12, headers={
                **HEADERS,
                'Content-Type': 'application/x-www-form-urlencoded',
                'x-fb-friendly-name': 'CareersJobDetailQuery',
            })
            if r.status_code == 200 and r.text.strip().startswith('{'):
                node = r.json().get('data', {}).get('job_posting', None)
                if node is None:
                    return False
                if node.get('id'):
                    return True
        except Exception as e:
            print(f'    meta api error: {e}')

    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers={
            **HEADERS,
            'Accept-Language': 'en-US,en;q=0.9',
        })
        if r.status_code in (404, 410):
            return False
        if r.status_code >= 400:
            print(f'    meta blocked (HTTP {r.status_code}) — skipping')
            return None
        body = r.text.lower()
        for phrase in SOFT_404_PHRASES + ['does not exist', "doesn't exist"]:
            if phrase in body:
                print(f'    meta soft-404 detected: "{phrase}"')
                return False
        if job_id and job_id in r.text:
            return True
    except Exception as e:
        print(f'    meta html error: {e}')
    return None


# ---------------------------------------------------------------------------
# Citadel Securities checker (content-based, longer timeout)
# ---------------------------------------------------------------------------

CITADEL_SOFT_404_PHRASES = [
    'this position is no longer available',
    'job is no longer available',
    'this role is no longer',
    'position has been filled',
    'application is closed',
    'page not found',
    '404',
]


def check_citadel(url):
    """Return True if open, False if closed, None if unable to determine."""
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers={
            **HEADERS,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        if r.status_code in (404, 410):
            return False
        if r.status_code == 200:
            body = r.text.lower()
            for phrase in CITADEL_SOFT_404_PHRASES:
                if phrase in body:
                    print(f'    soft-404 detected: "{phrase}"')
                    return False
            return True
    except Exception as e:
        print(f'    citadel check error: {e}')
    return None


# ---------------------------------------------------------------------------
# Generic HTTP + content check
# ---------------------------------------------------------------------------

def check_http_and_content(url):
    """
    Return True if the URL appears live, False if dead/soft-404, None on error.
    Fetches the page and checks both status code and body for closed-job phrases.
    """
    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers=HEADERS)
    except Exception as e:
        print(f'    request error: {e}')
        return None

    if r.status_code >= 400:
        return False

    # Content-based soft-404 detection
    body = r.text.lower()
    for phrase in SOFT_404_PHRASES:
        if phrase in body:
            print(f'    soft-404 detected: "{phrase}"')
            return False

    return True


# ---------------------------------------------------------------------------
# Workday helpers
# ---------------------------------------------------------------------------

def load_workday_boards():
    company_board = {}
    tenant_board = {}
    cur = None
    section = None
    tenant = None
    for line in Path('companies.yml').read_text().splitlines():
        if line.startswith('workday:'):
            section = 'workday'
            continue
        if line.endswith(':') and not line.startswith(' '):
            section = None
        if section != 'workday':
            continue
        m = re.match(r'- name: (.+)', line)
        if m:
            cur = m.group(1).strip()
        if cur and line.strip().startswith('tenant:'):
            tenant = line.split('tenant:', 1)[1].strip()
        if cur and line.strip().startswith('board:'):
            board = line.split('board:', 1)[1].strip()
            company_board[cur] = board
            if tenant:
                tenant_board[tenant] = board
    return company_board, tenant_board


def fix_workday_url(url, company_board, tenant_board, company=None):
    m = WD_BARE.match(url)
    if not m:
        return url
    base, tenant = m.group(1), m.group(2)
    board = company_board.get(company or '') or tenant_board.get(tenant)
    if not board:
        return url
    return url.replace(f'{base}/job/', f'{base}/{board}/job/')


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def is_skipped(url):
    for domain in SKIP_ALL_DOMAINS:
        if domain in url:
            return True
    return False


def resolve_url(url, company_board, tenant_board, company=None, gh_boards=None):
    """
    Return (resolved_url, is_alive).
    ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters) first, then site-specific
    checkers (Apple, Citadel), then universal content-based soft-404 for all
    custom career sites (Microsoft, Amazon, Google, Workday HTML, iCIMS, etc.).
    """
    if is_skipped(url):
        return url, True

    # --- SmartRecruiters API ---
    result = check_smartrecruiters(url)
    if result is True:
        return url, True
    if result is False:
        return url, False

    # --- Greenhouse API (direct + embedded gh_jid) ---
    if 'greenhouse.io' in url:
        result = check_greenhouse(url)
        if result is True:
            return url, True
        if result is False:
            return url, False
    result = check_greenhouse_gh_jid(url, company, gh_boards)
    if result is True:
        return url, True
    if result is False:
        return url, False
    result = check_greenhouse_careers_jobs(url, company, gh_boards)
    if result is True:
        return url, True
    if result is False:
        return url, False

    # --- Lever API ---
    if 'lever.co' in url:
        result = check_lever(url)
        if result is True:
            return url, True
        if result is False:
            return url, False

    # --- Ashby ---
    if 'ashbyhq.com' in url:
        result = check_ashby(url)
        if result is True:
            return url, True
        if result is False:
            return url, False

    # --- Apple Jobs (API + soft-404 HTML) ---
    if 'jobs.apple.com' in url:
        result = check_apple(url)
        if result is True:
            return url, True
        if result is False:
            return url, False

    # --- Citadel Securities ---
    if 'citadelsecurities.com' in url:
        result = check_citadel(url)
        if result is True:
            return url, True
        if result is False:
            return url, False

    # --- Universal content soft-404 (custom career sites + ATS HTML fallbacks) ---
    result = check_http_and_content(url)
    if result is False:
        fixed = fix_workday_url(url, company_board, tenant_board, company)
        if fixed != url:
            fixed_result = check_http_and_content(fixed)
            if fixed_result is True:
                print(f'    FIXED (board injection): {fixed}')
                return fixed, True
        return url, False
    if result is True:
        return url, True

    # Network error — assume alive to avoid false positives
    return url, True


def mark_listing_closed(entry):
    """Mark a listing closed. Only clears url — all other metadata is preserved."""
    entry['url'] = ''


def main():
    company_board, tenant_board = load_workday_boards()
    gh_boards = load_greenhouse_boards()

    listings_file = Path('listings.json')
    with open(listings_file) as f:
        listings = json.load(f)

    initial_count = len(listings)

    live = [e for e in listings if e.get('url', '').strip()]
    print(f'Checking {len(live)} live URL(s)')

    dead_count = 0
    fixed_count = 0
    for i, entry in enumerate(live, 1):
        url = entry['url']
        company = entry.get('company')
        if i % 50 == 0 or i == 1:
            print(f'  Progress: {i}/{len(live)}')
        resolved, alive = resolve_url(
            url, company_board, tenant_board, company, gh_boards,
        )
        if not alive:
            print(f'  DEAD: {company} — {entry["role"][:50]}')
            mark_listing_closed(entry)
            dead_count += 1
        elif resolved != url:
            print(f'  FIXED: {company} — {resolved[:70]}')
            entry['url'] = resolved
            fixed_count += 1
        time.sleep(0.25)

    if dead_count or fixed_count:
        if len(listings) != initial_count:
            raise SystemExit(
                f'Refusing to write: listing count changed '
                f'{initial_count} -> {len(listings)} (only url may change)',
            )
        tmp = listings_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(listings, f, indent=2)
        tmp.replace(listings_file)
        print(f'\nMarked {dead_count} dead, fixed {fixed_count} URL(s)')
        result = subprocess.run(
            ['python3', '.github/scripts/rebuild_readme.py'],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f'rebuild_readme.py failed: {result.stderr[:300]}')
        else:
            print(result.stdout.strip())
    else:
        print('\nAll checked links are active')


if __name__ == '__main__':
    main()
