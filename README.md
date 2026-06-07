# Job Scraper

A Python web scraper that collects job listings from an online job board and extracts structured job information suitable for database storage, analytics, or API ingestion.

## Features

* Scrapes job listing pages
* Handles pagination automatically
* Visits individual job detail pages
* Extracts structured job information
* Detects email-based applications
* Detects website-based applications
* Extracts application emails and URLs
* Retry mechanism with exponential backoff
* Request throttling for responsible crawling
* JSON export support
* Detailed logging for monitoring and debugging

---

# Project Structure

```text
main.py
```

All scraper functionality is contained in `main.py`.

---

# Workflow

The scraper operates in three stages:

## 1. Collect Job Links

The scraper visits listing pages and extracts individual job URLs.

### Function

```python
get_job_links()
```

Example output:

```python
[
    "https://example.com/job/123",
    "https://example.com/job/456",
]
```

---

## 2. Scrape Job Details

Each job URL is visited individually and parsed into a structured format.

### Function

```python
get_job_details()
```

Extracted fields include:

| Field              | Description                           |
| ------------------ | ------------------------------------- |
| title              | Job title                             |
| company_name       | Company or employer name              |
| location           | Job location                          |
| employment_type    | Full Time, Contract, Internship, etc. |
| description        | Job description                       |
| requirements       | Candidate requirements                |
| application_method | email or website                      |
| application_email  | Application email address             |
| application_url    | External or internal application URL  |
| source_url         | Original job posting URL              |

---

## 3. Store Results

All jobs are collected into a list and exported to a JSON file.

Example:

```json
{
  "title": "Backend Engineer",
  "company_name": "Example Company",
  "location": "Nairobi",
  "employment_type": "Full Time",
  "description": "...",
  "requirements": "...",
  "application_method": "website",
  "application_url": "https://example.com/apply",
  "application_email": null,
  "source_url": "https://example.com/job/backend-engineer"
}
```

---

# Core Functions

## fetch(url)

Responsible for all HTTP requests.

Features:

* Request timeout protection
* Automatic retries
* Exponential backoff
* Error logging

Example:

```python
response = fetch(url)
```

---

## get_job_links(url)

Extracts job detail URLs from a listing page.

Example:

```python
job_links = get_job_links(listing_url)
```

Returns:

```python
list[str]
```

---

## get_job_details(job_url)

Visits a job detail page and extracts structured job information.

Example:

```python
job = get_job_details(job_url)
```

Returns:

```python
dict
```

---

## scrape_jobs()

Main orchestration function.

Responsibilities:

1. Crawl listing pages
2. Collect job URLs
3. Scrape job details
4. Build structured job records
5. Return all scraped jobs

Example:

```python
jobs = scrape_jobs(max_pages=3)
```

---

# Application Method Detection

The scraper automatically determines how a candidate should apply.

## Email Application

Example:

```html
<strong>hr@example.com</strong>
```

Output:

```json
{
  "application_method": "email",
  "application_email": "hr@example.com"
}
```

---

## Website Application

Example:

```html
<a href="/apply-now/12345">
Apply Here
</a>
```

Output:

```json
{
  "application_method": "website",
  "application_url": "https://example.com/apply-now/12345"
}
```

---

# Configuration

The following settings can be adjusted at the top of `main.py`.

```python
REQUEST_DELAY = 1.5
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10
```

| Setting         | Description                  |
| --------------- | ---------------------------- |
| REQUEST_DELAY   | Delay between requests       |
| MAX_RETRIES     | Maximum retry attempts       |
| RETRY_BACKOFF   | Exponential retry multiplier |
| REQUEST_TIMEOUT | Timeout per request          |

---

# Running the Scraper

Install dependencies:

```bash
pip install requests beautifulsoup4
```

Run the scraper:

```bash
python main.py
```

Example output:

```text
Found 25 job links
Scraping job details...
Done. Total jobs scraped: 25
Saved to jobs.json
```

---

# Output

Results are saved to:

```text
jobs.json
```

The JSON file can be:

* Imported into a database
* Sent to an API
* Used for analytics
* Processed by another application

---

# Future Improvements

* PostgreSQL integration
* SQLAlchemy models
* Async scraping for higher throughput
* Duplicate detection
* Salary extraction
* Work mode detection (Remote, Hybrid, Onsite)
* Scheduled execution
* API endpoints
* Docker support

---

# Disclaimer

Use this project responsibly and ensure compliance with the target website's terms of service, robots.txt policies, and applicable laws before collecting data.
