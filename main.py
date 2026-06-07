import re
import json
import logging
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────
BASE_URL  = ""
JOBS_URL  = ""   
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 () "
      
    )
}

REQUEST_DELAY   = 1.5   # seconds between requests
MAX_RETRIES     = 3
RETRY_BACKOFF   = 2     # exponential backoff multiplier (2s → 4s → 8s)
REQUEST_TIMEOUT = 10    # seconds before giving up on a single request

# Email regex — used to detect plain-text emails in the apply section
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# restored — maps raw "Job Type" text → DB enum value
EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "full time":  "full_time",
    "part time":  "part_time",
    "contract":   "contract",
    "internship": "internship",
    "temporary":  "temporary",
}


SECTION_MAP: dict[str, str] = {
    # description bucket
    "THE ROLE":             "description",
    "ABOUT THE ROLE":       "description",
    "JOB DESCRIPTION":      "description",
    "JOB SUMMARY":          "description",
    "OVERVIEW":             "description",
    "KEY RESPONSIBILITIES": "description",
    "RESPONSIBILITIES":     "description",
    "DUTIES":               "description",
    "WHAT WE OFFER":        "description",
    "WHAT YOU WILL DO":     "description",
    # requirements bucket
    "WHAT WE ARE LOOKING FOR": "requirements",
    "REQUIREMENTS":            "requirements",
    "QUALIFICATIONS":          "requirements",
    "SKILLS & EXPERIENCE":     "requirements",
    "SKILLS AND EXPERIENCE":   "requirements",
    "MINIMUM REQUIREMENTS":    "requirements",
    "WHO WE ARE LOOKING FOR":  "requirements",
}

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HTTP layer
# ══════════════════════════════════════════════════════════════════════════════

def fetch(url: str) -> requests.Response | None:
    """GET a URL with retry + exponential backoff. Returns None on total failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            wait = RETRY_BACKOFF ** attempt
            if attempt < MAX_RETRIES:
                log.warning(
                    "Attempt %d/%d failed for %s: %s — retrying in %ds",
                    attempt, MAX_RETRIES, url, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error("All %d attempts failed for %s: %s", MAX_RETRIES, url, exc)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Listing page — collect job URLs
# ══════════════════════════════════════════════════════════════════════════════

def get_job_links(url: str) -> list[str]:
    """Return absolute job-detail URLs found on a listing page."""
    response = fetch(url)
    if not response:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []

    for job in soup.select("li.job-list-li"):
        title_tag = job.select_one("h2 a")
        if not title_tag:
            continue
        full_url = urljoin(BASE_URL, title_tag["href"])
        links.append(full_url)

    log.info("Found %d job link(s) on %s", len(links), url)
    return links


# ══════════════════════════════════════════════════════════════════════════════
# Detail page — extract structured job data
# ══════════════════════════════════════════════════════════════════════════════

def get_job_details(job_url: str) -> dict | None:
    """
    Scrape a single job detail page and return a dict matching the DB schema:

        title, company_name, location, employment_type,
        description, requirements,
        application_method, application_url, application_email,
        source_url
    """
    response = fetch(job_url)
    if not response:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # ── Title ──────────────────────────────────────────────────────────────
    title_tag = soup.select_one("span.subjob-title")
    title = title_tag.get_text(strip=True) if title_tag else None

    # ── Company Name ───────────────────────────────────────────────────────
    company_tag = soup.select_one("li.job-industry a[href*='/jobs-at/']")
    company_name = (
        company_tag.get_text(strip=True).replace("View Jobs at ", "")
        if company_tag else None
    )

    # ── Helper: sidebar key-info row (Location, Job Type, …) ──────────────
    def get_key_info(label_text: str) -> str | None:
        for li in soup.select("ul.job-key-info li"):
            label = li.select_one("span.jkey-title")
            if label and label_text in label.get_text():
                info = li.select_one("span.jkey-info")
                return info.get_text(strip=True) if info else None
        return None

    # ── Location ──────────────────────────────────────────────────────────
    location = get_key_info("Location")

    # ── Employment Type ───────────────────────────────────────────────────
    raw_type = (get_key_info("Job Type") or "").lower().strip()
    employment_type = EMPLOYMENT_TYPE_MAP.get(raw_type)

    # ── Description & Requirements ─────────────────────────────────────────
    description_lines: list[str] = []
    requirements_lines: list[str] = []

    details_div = soup.select_one("div.job-details")
    if details_div:
        current_bucket: str | None = None

        for elem in details_div.find_all(["p", "ul", "ol"], recursive=False):

            # Check if this <p> is a section heading
            heading_tag = elem.find("strong") or elem.find("b")
            if heading_tag and elem.name == "p":
                heading_text = heading_tag.get_text(strip=True)
                current_bucket = SECTION_MAP.get(heading_text.upper())
                if current_bucket == "description":
                    description_lines.append(f"\n{heading_text}")
                elif current_bucket == "requirements":
                    requirements_lines.append(f"\n{heading_text}")
                continue

            if not current_bucket:
                continue

            # Bullet / numbered list
            if elem.name in ("ul", "ol"):
                items = [
                    f"• {li.get_text(strip=True)}"
                    for li in elem.find_all("li")
                ]
                target = (
                    description_lines
                    if current_bucket == "description"
                    else requirements_lines
                )
                target.extend(items)

            # Plain paragraph under a known section
            elif elem.name == "p":
                text = elem.get_text(strip=True)
                if text:
                    if current_bucket == "description":
                        description_lines.append(text)
                    else:
                        requirements_lines.append(text)

    description  = "\n".join(description_lines).strip()
    requirements = "\n".join(requirements_lines).strip() or None

    # ── Application Method / URL / Email ──────────────────────────────────
    
    application_method: str | None = None
    application_url:    str | None = None
    application_email:  str | None = None

    method_h2 = soup.find(
        lambda tag: tag.name == "h2"
        and "Method of Application" in tag.get_text(" ", strip=True)
    )

    apply_div = method_h2.find_next_sibling("div") if method_h2 else None

    if apply_div:
        text = apply_div.get_text(" ", strip=True)

        # 1. Plain email address in text
        email_match = EMAIL_REGEX.search(text)
        if email_match:
            application_method = "email"
            application_email  = email_match.group(0)


        # 3. Regular apply link
        elif apply_link := apply_div.select_one("a[href]"):
            href = apply_link.get("href", "").strip()
            if href:
                application_method = "website"
                application_url    = urljoin(job_url, href)

   
    return {
        "title":              title,
        "company_name":       company_name,
        "location":           location,
        "employment_type":    employment_type,
        "description":        description,
        "requirements":       requirements,
        "application_method": application_method,
        "application_url":    application_url,
        "application_email":  application_email,
        "source_url":         job_url,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator — paginated multi-page scrape
# ══════════════════════════════════════════════════════════════════════════════

def scrape_jobs(
    source_url: str = JOBS_URL,  
    max_pages: int = 5,
) -> list[dict]:
    """
    Walk paginated listing pages, scrape each job detail page,
    and return a list of job dicts ready for DB insertion.

    Args:
        source_url: Base listing URL (page 1).
        max_pages:  Hard cap on listing pages to crawl.

    Returns:
        List of job detail dicts.
    """
    all_jobs: list[dict] = []

    for page in range(1, max_pages + 1):
       
        #         the separator and produced malformed URLs
        page_url = source_url if page == 1 else f"{source_url}page/{page}"
        log.info("── Page %d ─────────────────────────────", page)

        job_links = get_job_links(page_url)
        if not job_links:
            log.info("No jobs on page %d — stopping.", page)
            break

        for job_url in job_links:
            log.info("  Scraping %s", job_url)
            details = get_job_details(job_url)

            if details:
                all_jobs.append(details)
                log.info(
                    "  ✓ %-45s @ %s",
                    (details["title"] or "?")[:45],
                    details["company_name"] or "?",
                )
            else:
                log.warning("  ✗ Failed — skipping %s", job_url)

            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    log.info("Done. Total jobs scraped: %d", len(all_jobs))
    return all_jobs


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    jobs = scrape_jobs(max_pages=3)

    print(f"\n{'─' * 60}")
    print(f"Scraped {len(jobs)} job(s)\n")
    for job in jobs[:3]:
        print(f"  {job['title']} @ {job['company_name']} [{job['employment_type']}]")
        print(f"  {job['location']} | {job['application_method']} → {job['application_url'] or job['application_email']}")
        print()

    output_file = "jobs.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved to {output_file}")