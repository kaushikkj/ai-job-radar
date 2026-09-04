import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .base import CollectedJob


def date(value):
    try:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            # Lever exposes createdAt as epoch milliseconds.
            if value > 10_000_000_000:
                value = value / 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value).strip()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _parse_human_date(value, now=None):
    if not value:
        return None
    now = now or datetime.now(timezone.utc)
    text = html.unescape(str(value))
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"^(posted date|date posted|posted|published date|published|posted on|published on)\s*[:\-]?\s*", "", text)
    # Career sites frequently render dates with ordinal suffixes, e.g. August 5th 2026.
    text = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", text)
    if text in {"today", "just now", "new"}:
        return now
    if text == "yesterday":
        return now - timedelta(days=1)
    match = re.search(r"(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks)\s+ago", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("minute"):
            return now - timedelta(minutes=amount)
        if unit.startswith("hour"):
            return now - timedelta(hours=amount)
        if unit.startswith("week"):
            return now - timedelta(weeks=amount)
        return now - timedelta(days=amount)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(x) for x in value)
    if isinstance(value, dict):
        return value.get("name", "") or value.get("value", "")
    raw = html.unescape(str(value))
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)


def _description_text(value):
    """Convert plain, HTML, and repeatedly escaped HTML into readable text."""
    if value is None:
        return ""
    raw = str(value).replace("\r", "")
    # Some ATS payloads arrive escaped more than once (e.g. &amp;lt;p&amp;gt;).
    # Decode repeatedly before parsing so literal HTML never leaks into the UI.
    for _ in range(3):
        decoded = html.unescape(raw)
        if decoded == raw:
            break
        raw = decoded
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all("br"):
        tag.replace_with("\n")
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for tag in soup.find_all("li"):
        tag.insert_before("\n• ")
        tag.insert_after("\n")
    for tag in soup.find_all(["p", "div"]):
        tag.insert_after("\n")
    text = soup.get_text(" ", strip=False)
    # Defensive second pass for double-escaped tags that survived parsing.
    for _ in range(2):
        if re.search(r"</?(?:p|div|span|br|b|strong|h[1-6]|li|ul|ol)(?:\s[^>]*)?>", text, re.I):
            text = html.unescape(text)
            text = BeautifulSoup(text, "html.parser").get_text(" ", strip=False)
        else:
            break
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _absolute(base, href):
    if not href:
        return ""
    return urljoin(base, href.strip())


def _normalized_url(url):
    """Normalize tracking parameters while keeping the real job URL intact."""
    try:
        parsed = urlparse(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower()
            not in {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "source",
            }
        ]
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/") or "/",
                "",
                urlencode(query),
                "",
            )
        )
    except Exception:
        return url


def greenhouse(token, timeout, headers):
    response = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
        timeout=timeout,
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()

    jobs = []
    for item in data.get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        description = BeautifulSoup(
            item.get("content", "") or "", "html.parser"
        ).get_text(" ", strip=True)

        jobs.append(
            CollectedJob(
                item.get("title", ""),
                location,
                item.get("absolute_url", ""),
                description,
                "Greenhouse",
                date(item.get("first_published") or item.get("date_posted") or item.get("updated_at")),
                "remote" in location.lower(),
                "published/ATS" if item.get("first_published") or item.get("date_posted") else "updated_at/ATS",
            )
        )
    return jobs


def lever(site, timeout, headers):
    response = requests.get(
        f"https://api.lever.co/v0/postings/{site}?mode=json",
        timeout=timeout,
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()

    jobs = []
    for item in data:
        categories = item.get("categories") or {}
        location = categories.get("location", "")
        description = item.get("descriptionPlain") or BeautifulSoup(
            item.get("description", "") or "", "html.parser"
        ).get_text(" ", strip=True)

        jobs.append(
            CollectedJob(
                item.get("text", ""),
                location,
                item.get("hostedUrl") or item.get("applyUrl", ""),
                description,
                "Lever",
                date(item.get("createdAt")),
                "remote" in location.lower(),
                "createdAt/Lever" if item.get("createdAt") else "",
            )
        )
    return jobs


def rss(url, timeout, headers):
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    return [
        CollectedJob(
            entry.get("title", ""),
            entry.get("location", ""),
            entry.get("link", ""),
            entry.get("summary", "") or "",
            "RSS",
            date(entry.get("published_parsed")) or date(entry.get("updated_parsed")) or _parse_human_date(entry.get("published")) or _parse_human_date(entry.get("updated")),
            "remote"
            in (
                (entry.get("title", "") or "")
                + " "
                + (entry.get("summary", "") or "")
            ).lower(),
            "published/RSS" if entry.get("published") or entry.get("published_parsed") else "updated/RSS",
        )
        for entry in feed.entries
    ]


ROLE_TERMS = (
    "sre",
    "site reliability",
    "reliability engineer",
    "devops",
    "platform engineer",
    "platform reliability",
    "cloud engineer",
    "cloud infrastructure",
    "cloud platform",
    "infrastructure engineer",
    "infrastructure platform",
    "software engineer",
    "software development engineer",
    "backend engineer",
    "database reliability",
    "database engineer",
    "database platform",
    "production engineer",
    "systems engineer",
    "site operations",
)

JOB_PATH_PATTERNS = (
    re.compile(r"/job(?:s)?(?:/|$)", re.I),
    re.compile(r"/career(?:s)?/job(?:s)?(?:/|$)", re.I),
    re.compile(r"/position(?:s)?(?:/|$)", re.I),
    re.compile(r"/opening(?:s)?(?:/|$)", re.I),
    re.compile(r"/vacanc(?:y|ies)(?:/|$)", re.I),
    re.compile(r"/opportunit(?:y|ies)(?:/|$)", re.I),
    re.compile(r"/requisition(?:/|$)", re.I),
    re.compile(r"/req(?:/|$)", re.I),
    re.compile(r"/careers?/[^/]+/[^/]+/job(?:/|$)", re.I),
)


def _looks_like_job_path(url):
    parsed = urlparse(url)
    path = parsed.path or ""
    if any(pattern.search(path) for pattern in JOB_PATH_PATTERNS):
        return True

    # Common ATS query-driven job pages.
    query = parsed.query.lower()
    return any(
        token in query
        for token in ("gh_jid=", "jobid=", "job_id=", "requisitionid=", "reqid=")
    )


def _looks_like_role(text):
    value = (text or "").lower()
    return any(term in value for term in ROLE_TERMS)


def _same_domain(a, b):
    return urlparse(a).netloc.lower().replace("www.", "") == urlparse(
        b
    ).netloc.lower().replace("www.", "")


def _extract_jobposting(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        try:
            data = json.loads(raw)
        except Exception:
            continue

        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if not isinstance(item, dict):
                continue

            item_type = item.get("@type", "")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" in types:
                return item

            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)

    return None


def _extract_location(job_data, soup):
    location = job_data.get("jobLocation")

    if isinstance(location, list):
        values = []
        for item in location:
            address = item.get("address", item) if isinstance(item, dict) else item
            if isinstance(address, dict):
                parts = [
                    address.get("addressLocality", ""),
                    address.get("addressRegion", ""),
                    address.get("addressCountry", ""),
                ]
                value = ", ".join(str(x) for x in parts if x)
            else:
                value = _text(address)
            if value:
                values.append(value)
        if values:
            return " | ".join(dict.fromkeys(values))

    elif isinstance(location, dict):
        address = location.get("address", location)
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality", ""),
                address.get("addressRegion", ""),
                address.get("addressCountry", ""),
            ]
            value = ", ".join(str(x) for x in parts if x)
            if value:
                return value
        elif address:
            return _text(address)

    elif location:
        return _text(location)

    applicant = job_data.get("applicantLocationRequirements")
    if applicant:
        value = _text(applicant)
        if value:
            return value

    meta_names = (
        "job-location",
        "job_location",
        "location",
        "locationName",
        "location-name",
    )
    for name in meta_names:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()

    # LPL/Workday-style pages and other ATS pages often expose the
    # location in visible labels. Prefer a concise line containing a
    # recognizable geography.
    geo_terms = (
        "hyderabad",
        "bengaluru",
        "bangalore",
        "mumbai",
        "pune",
        "chennai",
        "delhi",
        "gurugram",
        "noida",
        "india",
        "remote",
        "united states",
        "usa",
        "canada",
        "united kingdom",
        "uk",
        "singapore",
        "australia",
    )

    for element in soup.find_all(["div", "span", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if 2 <= len(text) <= 180:
            lower = text.lower()
            if any(term in lower for term in geo_terms):
                if not any(
                    bad in lower
                    for bad in ("copyright", "cookie", "privacy", "follow us")
                ):
                    return text

    return ""


def _extract_description(job_data, soup):
    description = _description_text(job_data.get("description"))
    if len(description) >= 150:
        return description[:30000]

    for selector in (
        '[class*="job-description"]',
        '[class*="jobDescription"]',
        '[id*="job-description"]',
        '[id*="jobDescription"]',
        '[class*="job-detail"]',
        '[class*="jobDetail"]',
        "main",
    ):
        element = soup.select_one(selector)
        if element:
            text = _description_text(str(element))
            if len(text) >= 150:
                return text[:30000]

    return _description_text(str(soup.body or soup))[:30000]


def _extract_posted(job_data, soup):
    """Extract the original publication date, never a crawl/update timestamp.

    Employer pages can expose several dates. An explicit visible ``Posted Date``
    is the strongest signal, followed by JobPosting ``datePosted`` and metadata.
    ``dateModified``/updated timestamps are deliberately ignored.
    """
    text = soup.get_text(" ", strip=True)
    explicit_patterns = (
        (r"(?:posted\s*date|date\s*posted)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})", "visible Posted Date"),
        (r"(?:posted\s*date|date\s*posted)\s*[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}[,]?\s+\d{4})", "visible Posted Date"),
    )
    for pattern, source in explicit_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _parse_human_date(match.group(1))
            if parsed:
                return parsed, source

    # Also inspect raw page source because some ATS templates keep the label
    # inside JSON or escaped markup that BeautifulSoup hides from visible text.
    raw_source = str(soup)
    for pattern, source in explicit_patterns:
        match = re.search(pattern, html.unescape(raw_source), re.I)
        if match:
            parsed = _parse_human_date(match.group(1))
            if parsed:
                return parsed, source

    value = job_data.get("datePosted") if isinstance(job_data, dict) else None
    parsed = date(value) or _parse_human_date(value)
    if parsed:
        return parsed, "datePosted/JobPosting"

    meta_candidates = (
        ("name", "datePosted", "datePosted meta"),
        ("name", "date-posted", "date-posted meta"),
        ("name", "posted-date", "posted-date meta"),
        ("name", "job-posted-date", "job-posted-date meta"),
        ("itemprop", "datePosted", "itemprop datePosted"),
        ("property", "article:published_time", "article:published_time"),
        ("property", "og:published_time", "og:published_time"),
    )
    for attr, value, source in meta_candidates:
        tag = soup.find("meta", attrs={attr: value})
        if tag:
            raw = tag.get("content")
            parsed = date(raw) or _parse_human_date(raw)
            if parsed:
                return parsed, source

    return None, ""


def _extract_company_name(job_data, final_url=""):
    if isinstance(job_data, dict):
        org = job_data.get("hiringOrganization")
        if isinstance(org, dict):
            name = _text(org.get("name"))
            if name:
                return name.strip()
        elif isinstance(org, str) and org.strip():
            return org.strip()
    host = urlparse(final_url).netloc.lower().replace("www.", "")
    known = {
        "wise.jobs": "Wise",
        "careers.wise.jobs": "Wise",
        "barclays.com": "Barclays",
        "lplfinancial.in": "LPL Financial India",
        "careers.lplfinancial.in": "LPL Financial India",
    }
    return known.get(host, "")


def fetch_single_job(url, timeout, headers, source="Career Site"):
    """Fetch one known job URL directly, preserving its original posted date."""
    response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
    response.raise_for_status()
    page = BeautifulSoup(response.text, "html.parser")
    job_data = _extract_jobposting(page) or {}
    title = _extract_title(job_data, page, "")
    description = _extract_description(job_data, page)
    location = _extract_location(job_data, page)
    posted_at, posted_at_source = _extract_posted(job_data, page)
    job_type = _text(job_data.get("employmentType")) if isinstance(job_data, dict) else ""
    remote = "remote" in (title + " " + location + " " + job_type + " " + description).lower()
    if not title or len(description) < 100:
        return None
    return CollectedJob(title, location, response.url, description, source, posted_at, remote, posted_at_source, _extract_company_name(job_data, response.url))


def _extract_title(job_data, soup, fallback):
    title = _text(job_data.get("title"))
    if title:
        return title[:500]

    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
        if 5 <= len(title) <= 220:
            return title

    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        return meta["content"].strip()[:500]

    if soup.title:
        title = soup.title.get_text(" ", strip=True)
        for separator in (" | ", " - ", " — "):
            if separator in title:
                title = title.split(separator, 1)[0]
                break
        if 5 <= len(title) <= 220:
            return title

    return fallback[:500]


def _fetch_sitemap_candidates(base_url, timeout, headers):
    parsed = urlparse(base_url)
    sitemap_urls = [
        f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
        f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml",
    ]

    found = []
    for sitemap_url in sitemap_urls:
        try:
            response = requests.get(
                sitemap_url,
                timeout=min(timeout, 10),
                headers=headers,
            )
            if response.status_code != 200:
                continue

            root = ET.fromstring(response.content)
            namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            for loc in root.findall(".//sm:loc", namespace):
                value = (loc.text or "").strip()
                if value and _same_domain(value, base_url):
                    found.append(value)

            # Some sites omit the namespace.
            if not found:
                for loc in root.findall(".//loc"):
                    value = (loc.text or "").strip()
                    if value and _same_domain(value, base_url):
                        found.append(value)

        except Exception:
            continue

        if found:
            break

    return found


def generic(url, timeout, headers):
    """
    Generic collector for employer career sites.

    It only emits records when a candidate looks like an individual
    job-detail page. Structured JobPosting JSON-LD is preferred; the
    fallback requires a job-like URL plus a plausible role title and
    substantial job-page content.
    """
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen = set()

    def add_candidate(href, anchor_title=""):
        href = _absolute(url, href)
        if not href.startswith(("http://", "https://")):
            return
        normalized = _normalized_url(href)
        # Career sites frequently hand off the actual application page to a
        # separate ATS domain. Keep external URLs when they clearly look like
        # individual job pages; only role-text links without a job path must
        # remain on the employer domain.
        if not _same_domain(href, url) and not _looks_like_job_path(href):
            return
        if normalized in seen:
            return
        if normalized.rstrip("/") == _normalized_url(url).rstrip("/"):
            return
        seen.add(normalized)
        candidates.append((href, anchor_title))

    # Direct links from the career page.
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        title = anchor.get_text(" ", strip=True)

        if _looks_like_job_path(_absolute(url, href)) or _looks_like_role(
            title
        ):
            add_candidate(href, title)

    # Some sites put job URLs into JSON/HTML attributes rather than anchors.
    for element in soup.find_all(["div", "script"]):
        for attribute in ("data-url", "data-href", "data-job-url"):
            value = element.get(attribute)
            if value and _looks_like_job_path(_absolute(url, value)):
                add_candidate(value, element.get_text(" ", strip=True)[:220])

    # JS-heavy sites may expose jobs only in their sitemap.
    if len(candidates) < 5:
        for sitemap_url in _fetch_sitemap_candidates(url, timeout, headers):
            if _looks_like_job_path(sitemap_url):
                add_candidate(sitemap_url)

    # The page itself can be an individual JobPosting.
    page_job = _extract_jobposting(soup)
    if page_job:
        canonical = soup.find("link", rel="canonical")
        href = _text(page_job.get("url"))
        if not href and canonical and canonical.get("href"):
            href = _absolute(url, canonical["href"])
        href = href or url
        add_candidate(href, _text(page_job.get("title")))

    output = []

    for href, anchor_title in candidates[:12]:
        try:
            page_response = requests.get(
                href,
                timeout=timeout,
                headers=headers,
                allow_redirects=True,
            )
            if page_response.status_code != 200:
                continue

            final_url = page_response.url
            page = BeautifulSoup(page_response.text, "html.parser")
            job_data = _extract_jobposting(page)

            # Strongest signal: structured JobPosting data.
            if job_data:
                title = _extract_title(job_data, page, anchor_title)
                description = _extract_description(job_data, page)
                location = _extract_location(job_data, page)
                posted_at, posted_at_source = _extract_posted(job_data, page)

                job_type = _text(job_data.get("employmentType"))
                remote = "remote" in (
                    title + " " + location + " " + job_type + " " + description
                ).lower()

                output.append(
                    CollectedJob(
                        title,
                        location,
                        final_url,
                        description,
                        "Career Site",
                        posted_at,
                        remote,
                        posted_at_source,
                        _extract_company_name(job_data, final_url),
                    )
                )
                continue

            # Fallback: only accept URLs that actually look like job-detail
            # URLs. This is what prevents product/blog/career pages from
            # becoming fake jobs.
            if not _looks_like_job_path(final_url):
                continue

            title = _extract_title({}, page, anchor_title)
            if not title or not _looks_like_role(title):
                continue

            description = _extract_description({}, page)
            if len(description) < 150:
                continue

            location = _extract_location({}, page)
            remote = "remote" in (
                title + " " + location + " " + description
            ).lower()

            output.append(
                CollectedJob(
                    title,
                    location,
                    final_url,
                    description,
                    "Career Site",
                    _extract_posted({}, page)[0],
                    remote,
                    _extract_posted({}, page)[1],
                )
            )

        except requests.RequestException:
            continue
        except Exception:
            continue

    unique = []
    seen_urls = set()
    for job in output:
        normalized = _normalized_url(job.url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        unique.append(job)

    return unique[:100]


def fingerprint(title, url, company):
    normalized = _normalized_url(url)
    return hashlib.sha256(
        f"{company}|{title}|{normalized}".lower().encode()
    ).hexdigest()
