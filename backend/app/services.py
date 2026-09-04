import json
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .ai import analyze_job
from .collectors.ats import fingerprint, generic, greenhouse, lever, rss, fetch_single_job, _normalized_url
from .collectors.base import CollectedJob
from .db import SessionLocal
from .models import Company, Job
from sqlalchemy import desc
from .scoring import score_job


SCAN_LOCK = threading.Lock()
SCAN_STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "last_error": None,
}


def now():
    return datetime.now(timezone.utc)


@contextmanager
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seeds():
    path = Path("/app/seed-data/companies.json")
    return json.loads(path.read_text(encoding="utf-8"))


def seed_companies(db):
    for item in seeds():
        company = db.query(Company).filter_by(slug=item["slug"]).first()
        if not company:
            company = Company(
                name=item["name"],
                slug=item["slug"],
                category=item.get("category", "Technology"),
                priority=item.get("priority", 50),
                career_url=item.get("career_url", ""),
                source_type=item.get("source_type", "generic"),
                adapter_config=json.dumps(item.get("adapter_config", {})),
                enabled=item.get("enabled", True),
            )
            db.add(company)
        else:
            # Keep user-managed enabled state, but refresh source configuration
            # when the seed definition changes.
            company.name = item["name"]
            company.category = item.get("category", company.category)
            company.priority = item.get("priority", company.priority)
            company.career_url = item.get("career_url", company.career_url)
            company.source_type = item.get("source_type", company.source_type)
            company.adapter_config = json.dumps(item.get("adapter_config", {}))

    db.commit()


def _safe_json(value):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def collect(company, timeout=20):
    config = _safe_json(company.adapter_config)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36 "
            "AI-Job-Radar/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Prefer an explicit adapter, then auto-detect common ATS hosts so a
    # company can be added with only its public careers URL.
    if company.source_type == "greenhouse" and config.get("token"):
        return greenhouse(config["token"], timeout, headers)
    if company.source_type == "lever" and config.get("site"):
        return lever(config["site"], timeout, headers)
    if company.source_type == "rss" and config.get("url"):
        return rss(config["url"], timeout, headers)

    career_url = company.career_url or ""
    host = urlparse(career_url).netloc.lower()
    if "greenhouse.io" in host:
        token = config.get("token") or career_url.rstrip("/").split("/")[-1]
        if token:
            return greenhouse(token, timeout, headers)
    if "lever.co" in host:
        site = config.get("site") or career_url.rstrip("/").split("/")[-1]
        if site:
            return lever(site, timeout, headers)
    if career_url:
        return generic(career_url, timeout, headers)

    return []


def upsert(db, company, collected):
    if not collected.title or not collected.url:
        return False

    # Career URLs can redirect to another employer's actual ATS/site. Prefer
    # the employer declared by the final JobPosting (or a known final host).
    detected_company = (getattr(collected, "company_name", "") or "").strip()
    job_company = company
    if detected_company and detected_company.casefold() != company.name.casefold():
        job_company = db.query(Company).filter(Company.name.ilike(detected_company)).first() or company

    # Never store a company homepage as a job URL.
    normalized_url = collected.url.rstrip("/")
    career_url = (company.career_url or "").rstrip("/")
    if normalized_url == career_url and collected.source not in {
        "Greenhouse",
        "Lever",
        "RSS",
    }:
        return False

    fp = fingerprint(collected.title, collected.url, job_company.name)
    job = db.query(Job).filter_by(fingerprint=fp).first()

    score = score_job(
        collected.title,
        collected.location,
        collected.description,
        job_company.priority,
        job_company.category,
    )

    is_new = job is None

    if job is None:
        job = Job(
            company_id=job_company.id,
            company_name=detected_company or job_company.name,
            title=collected.title[:500],
            location=(collected.location or "")[:500],
            remote=bool(collected.remote),
            source=collected.source[:100],
            url=collected.url[:2000],
            description=(collected.description or "")[:30000],
            posted_at=collected.posted_at,
            posted_at_source=getattr(collected, "posted_at_source", "") or "",
            first_seen_at=now(),
            last_seen_at=now(),
            fingerprint=fp,
        )
        db.add(job)
    else:
        job.company_id = job_company.id
        job.company_name = detected_company or job_company.name
        job.title = collected.title[:500]
        job.location = (collected.location or job.location or "")[:500]
        job.remote = bool(collected.remote)
        job.source = collected.source[:100]
        job.url = collected.url[:2000]
        job.description = (collected.description or job.description or "")[:30000]
        job.posted_at = collected.posted_at or job.posted_at
        if getattr(collected, "posted_at_source", ""):
            job.posted_at_source = collected.posted_at_source
        job.last_seen_at = now()

    job.score = score.total
    job.role_score = score.role
    job.technical_score = score.technical
    job.experience_score = score.experience
    job.location_score = score.location
    job.company_score = score.company
    job.industry_score = score.industry
    job.match_reason = score.reason

    # AI analysis is intentionally on-demand. Never block a career-site scan
    # on one OpenAI request per newly discovered job. This keeps 5-minute
    # monitoring responsive even when AI is unavailable or rate-limited.

    return is_new



def refresh_job_from_source(db, job, timeout=20):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/128 Safari/537.36 "
            "AI-Job-Radar/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    collected = fetch_single_job(job.url, timeout, headers, source=job.source or "Career Site")
    if not collected:
        raise ValueError("Could not extract a valid job posting from the source URL")
    # Keep the existing record stable by URL; the publication date and cleaned
    # description are replaced with the latest authoritative extraction.
    detected_company = (getattr(collected, "company_name", "") or "").strip()
    current_company = db.get(Company, job.company_id)
    if detected_company and current_company and detected_company.casefold() != current_company.name.casefold():
        target_company = db.query(Company).filter(Company.name.ilike(detected_company)).first()
        if target_company:
            job.company_id = target_company.id
            current_company = target_company
    job.company_name = detected_company or (current_company.name if current_company else job.company_name)
    job.title = collected.title[:500]
    job.location = (collected.location or job.location or "")[:500]
    job.remote = bool(collected.remote)
    job.source = collected.source[:100]
    job.url = collected.url[:2000]
    job.description = (collected.description or job.description or "")[:30000]
    if collected.posted_at:
        job.posted_at = collected.posted_at
    job.posted_at_source = collected.posted_at_source or job.posted_at_source or ""
    job.last_seen_at = now()
    score = score_job(job.title, job.location, job.description, (current_company or db.get(Company, job.company_id)).priority, (current_company or db.get(Company, job.company_id)).category)
    job.score = score.total
    job.role_score = score.role
    job.technical_score = score.technical
    job.experience_score = score.experience
    job.location_score = score.location
    job.company_score = score.company
    job.industry_score = score.industry
    job.match_reason = score.reason
    db.commit()
    db.refresh(job)
    return job

def _looks_like_job_record(job):
    url = (job.url or "").lower()
    title = (job.title or "").lower()

    bad_path_tokens = (
        "/about",
        "/company",
        "/observability/",
        "/blog/",
        "/news/",
        "/events/",
        "/teams/",
        "/culture/",
        "/benefits/",
        "/privacy",
        "/terms",
        "/search",
    )

    if any(token in url for token in bad_path_tokens):
        return False

    job_path_tokens = (
        "/job/",
        "/jobs/",
        "/career/job",
        "/careers/job",
        "/position/",
        "/positions/",
        "/opening/",
        "/openings/",
        "/vacancy/",
        "/vacancies/",
        "/opportunity/",
        "/opportunities/",
        "/requisition/",
        "/req/",
    )

    if job.source in {"Greenhouse", "Lever", "RSS"}:
        return True

    if any(token in url for token in job_path_tokens):
        return True

    # A structured JobPosting can legitimately use a query-driven URL.
    # Keep substantial records unless the URL is an obvious company/content
    # page. The new collector already enforces stricter acceptance.
    return len(job.description or "") >= 300 and len(job.title or "") <= 220


def cleanup_legacy_jobs(db):
    """Remove seeded/demo records and obvious pre-fix non-job pages."""
    deleted_demo = (
        db.query(Job)
        .filter(Job.source == "Demo")
        .delete(synchronize_session=False)
    )

    candidates = db.query(Job).filter(Job.source == "Career Site").all()
    deleted_invalid = 0
    for job in candidates:
        if not _looks_like_job_record(job):
            db.delete(job)
            deleted_invalid += 1

    db.commit()
    return {
        "demo_deleted": deleted_demo,
        "invalid_deleted": deleted_invalid,
    }



def repair_known_redirected_employers(db):
    """Repair existing jobs whose source redirected to a known employer site."""
    wise = db.query(Company).filter(Company.name.ilike("Wise")).first()
    if not wise:
        return 0
    repaired = 0
    jobs = db.query(Job).filter(Job.url.ilike("%wise.jobs%"), Job.company_name.ilike("Barclays")).all()
    for job in jobs:
        job.company_id = wise.id
        job.company_name = wise.name
        repaired += 1
    if repaired:
        db.commit()
    return repaired

def scan_all(db=None):
    own_session = db is None
    if not SCAN_LOCK.acquire(blocking=False):
        return {
            "started": False,
            "message": "A scan is already running.",
            "running": True,
            "companies": 0,
            "collected": 0,
            "new": 0,
            "errors": [],
        }

    SCAN_STATE["running"] = True
    SCAN_STATE["started_at"] = now().isoformat()
    SCAN_STATE["last_error"] = None

    local_db = db or SessionLocal()

    result = {
        "started": True,
        "companies": 0,
        "collected": 0,
        "new": 0,
        "errors": [],
    }

    try:
        from .config import settings

        timeout = settings.request_timeout_seconds
        companies = (
            local_db.query(Company)
            .filter_by(enabled=True)
            .order_by(desc(Company.priority), Company.name)
            .all()
        )
        result["companies"] = len(companies)

        # Network collection is parallel so a single slow employer cannot
        # block the entire one-minute scheduler cycle.
        def collect_one(company):
            try:
                return company.id, collect(company, timeout=timeout), None
            except Exception as exc:
                return company.id, [], f"{company.name}: {exc}"

        company_map = {company.id: company for company in companies}

        with ThreadPoolExecutor(max_workers=24) as executor:
            futures = [executor.submit(collect_one, company) for company in companies]

            for future in as_completed(futures):
                company_id, jobs, error = future.result()

                if error:
                    result["errors"].append(error)
                    continue

                company = company_map[company_id]
                result["collected"] += len(jobs)

                try:
                    for collected in jobs:
                        result["new"] += int(upsert(local_db, company, collected))
                    local_db.commit()
                except Exception as exc:
                    local_db.rollback()
                    result["errors"].append(f"{company.name}: {exc}")

        SCAN_STATE["last_result"] = result
        SCAN_STATE["finished_at"] = now().isoformat()
        return result

    except Exception as exc:
        local_db.rollback()
        SCAN_STATE["last_error"] = str(exc)
        result["errors"].append(f"Scan failure: {exc}")
        return result

    finally:
        SCAN_STATE["running"] = False
        if own_session:
            local_db.close()
        SCAN_LOCK.release()

def scan_state():
    return {
        **SCAN_STATE,
        "running": bool(SCAN_STATE["running"]),
    }


def seed_demo(db):
    # Kept for backwards compatibility with older callers. Demo records are
    # intentionally disabled for the production dashboard.
    return {"created": 0}


def import_linkedin_alert(db, text):
    from .linkedin import parse_alert

    company = db.query(Company).filter_by(slug="linkedin-alerts").first()
    if not company:
        company = Company(
            name="LinkedIn Alerts",
            slug="linkedin-alerts",
            category="Technology",
            priority=80,
            career_url="https://www.linkedin.com/jobs/",
            source_type="rss",
            adapter_config="{}",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    imported = 0
    for item in parse_alert(text or ""):
        imported += int(upsert(db, company, item))

    db.commit()
    return imported
