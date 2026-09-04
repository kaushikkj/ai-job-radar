import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine, get_db, migrate
from .models import AppSetting, Company, Job, Resume, ResumeVersion
from .collectors.ats import _description_text
from .profile import PROFILE
from .services import (
    cleanup_legacy_jobs,
    refresh_job_from_source,
    import_linkedin_alert,
    scan_all,
    scan_state,
    seed_companies,
    repair_known_redirected_employers,
)

Base.metadata.create_all(bind=engine)
migrate()

app = FastAPI(title="AI Job Radar", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        item.strip()
        for item in settings.cors_origins.split(",")
        if item.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = BackgroundScheduler(timezone="UTC")


def scheduled_scan():
    scan_all()


@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        seed_companies(db)
        # Existing databases may contain the old demo records and the
        # pre-fix generic-crawler records. Clean them once at startup.
        cleanup_legacy_jobs(db)
        repair_known_redirected_employers(db)
    finally:
        db.close()

    # Load persisted runtime settings from the database. Environment variables
    # provide the initial defaults, while UI changes survive container restarts.
    db = SessionLocal()
    try:
        # v7.0.7 defaults: scan every 10 minutes and use a 60-second request timeout.
        # Migrate the previous built-in defaults once, while preserving any other
        # value the user has explicitly selected in the application.
        migrations = {
            "scan_interval_seconds": 600,
            "request_timeout_seconds": 60,
        }
        for key, attr in (("scan_interval_seconds", "scan_interval_seconds"), ("request_timeout_seconds", "request_timeout_seconds")):
            saved = db.get(AppSetting, key)
            try:
                if saved is None:
                    value = 600 if key == "scan_interval_seconds" else 60
                    saved = AppSetting(key=key, value=str(value))
                    db.add(saved)
                else:
                    current = int(saved.value)
                    if current == migrations[key]:
                        value = 600 if key == "scan_interval_seconds" else 60
                        saved.value = str(value)
                    else:
                        value = current
                setattr(settings, attr, value)
            except (TypeError, ValueError):
                value = 600 if key == "scan_interval_seconds" else 60
                setattr(settings, attr, value)
        # Migrate the previous 5-minute public-source defaults to 10 minutes.
        source_row = db.get(AppSetting, "source_settings")
        if source_row:
            try:
                source_cfg = json.loads(source_row.value)
                changed = False
                for source in ("career_sites", "greenhouse", "lever", "rss"):
                    cfg = source_cfg.get(source)
                    if isinstance(cfg, dict) and int(cfg.get("interval_seconds", 600)) == 300:
                        cfg["interval_seconds"] = 600
                        changed = True
                if changed:
                    source_row.value = json.dumps(source_cfg)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        db.commit()
    finally:
        db.close()

    if not scheduler.running:
        scheduler.add_job(
            scheduled_scan,
            "interval",
            seconds=max(300, settings.scan_interval_seconds),
            id="career-scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=max(300, settings.scan_interval_seconds)),
        )
        scheduler.start()


@app.on_event("shutdown")
def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/")
def root():
    return {
        "name": "AI Job Radar",
        "version": "2.0",
        "status": "ok",
        "scan_interval_seconds": settings.scan_interval_seconds,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profile")
def profile():
    return PROFILE


@app.get("/scan/status")
def scan_status():
    state = scan_state()
    job = scheduler.get_job("career-scan")

    state["next_run_at"] = (
        job.next_run_time.isoformat() if job and job.next_run_time else None
    )
    return state


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    return {
        "total": db.query(Job).count(),
        "active": db.query(Job).filter(Job.status != "archived").count(),
        "match90": db.query(Job).filter(Job.score >= 91, Job.score <= 100).count(),
        "match80": db.query(Job).filter(Job.score >= 81, Job.score <= 90).count(),
        "match70": db.query(Job).filter(Job.score >= 71, Job.score <= 80).count(),
        "match60": db.query(Job).filter(Job.score >= 61, Job.score <= 70).count(),
        "match50": db.query(Job).filter(Job.score >= 51, Job.score <= 60).count(),
        "match0": db.query(Job).filter(Job.score >= 0, Job.score <= 50).count(),
        "recent3d": db.query(Job).filter(Job.posted_at.is_not(None), Job.posted_at >= recent_cutoff).count(),
        "new_today": db.query(Job).filter(Job.first_seen_at >= start).count(),
        "published_today": db.query(Job).filter(Job.posted_at.is_not(None), Job.posted_at >= start).count(),
        "added_3d": db.query(Job).filter(Job.first_seen_at >= datetime.now(timezone.utc) - timedelta(days=3)).count(),
        "companies": db.query(Company).filter_by(enabled=True).count(),
        "hyderabad": db.query(Job)
        .filter(Job.location.ilike("%hyderabad%"))
        .count(),
        "remote": db.query(Job).filter(Job.remote.is_(True)).count(),
        "shortlist": db.query(Job).filter(Job.saved.is_(True)).count(),
        "applied": db.query(Job).filter(Job.status == "applied").count(),
        "interested": db.query(Job).filter(Job.status == "interested").count(),
        "sources": {
            source or "Unknown": count
            for source, count in db.query(
                Job.source, func.count(Job.id)
            ).group_by(Job.source)
        },
    }


@app.get("/companies")
def companies(
    enabled: bool | None = None,
    category: str = "",
    db: Session = Depends(get_db),
):
    query = db.query(Company)

    if enabled is not None:
        query = query.filter(Company.enabled == enabled)

    if category:
        query = query.filter(Company.category.ilike(f"%{category}%"))

    return query.order_by(desc(Company.priority), Company.name).all()


@app.patch("/companies/{company_id}")
def update_company(
    company_id: int,
    enabled: bool | None = None,
    priority: int | None = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    if enabled is not None:
        company.enabled = enabled
    if priority is not None:
        company.priority = priority

    db.commit()
    db.refresh(company)
    return company


def _as_aware(value):
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _freshness_score(age_days):
    if age_days is None:
        return 25.0
    if age_days <= 0.5:
        return 100.0
    if age_days <= 1:
        return 96.0
    if age_days <= 3:
        return 88.0
    if age_days <= 7:
        return 76.0
    if age_days <= 14:
        return 60.0
    if age_days <= 30:
        return 40.0
    if age_days <= 60:
        return 20.0
    if age_days <= 90:
        return 8.0
    return 0.0


def _job_payload(job):
    data = {
        "id": job.id, "company_id": job.company_id, "company_name": job.company_name,
        "title": job.title, "location": job.location, "remote": job.remote, "source": job.source,
        "url": job.url, "description": _description_text(job.description), "posted_at": job.posted_at,
        "posted_at_source": job.posted_at_source or "", "first_seen_at": job.first_seen_at,
        "last_seen_at": job.last_seen_at, "score": job.score, "role_score": job.role_score,
        "technical_score": job.technical_score, "experience_score": job.experience_score,
        "location_score": job.location_score, "company_score": job.company_score,
        "industry_score": job.industry_score, "match_reason": job.match_reason,
        "ai_analysis": job.ai_analysis, "status": job.status, "saved": job.saved,
        "skills": [],
        "applied_at": job.applied_at, "created_at": job.created_at, "updated_at": job.updated_at,
    }
    posted = _as_aware(job.posted_at)
    now_value = datetime.now(timezone.utc)
    age_days = None
    if posted:
        age_days = max(0.0, round((now_value - posted).total_seconds() / 86400, 1))
    freshness = _freshness_score(age_days)
    priority = round((float(job.score or 0) * 0.70) + (freshness * 0.30), 1)
    data["skills"] = [
        s for s in ["Kubernetes","Terraform","AWS","GCP","Azure","Python","Docker","Helm","ArgoCD","CI/CD","GitOps","Prometheus","Grafana","Datadog","Observability","Microservices","SQL","Kafka","Automation"]
        if s.lower() in (f"{job.title} {job.description}").lower()
    ][:10]
    data.update({
        "age_days": age_days,
        "freshness_score": freshness,
        "priority_score": priority,
        "is_recent": age_days is not None and age_days <= 3,
        "is_new_today": age_days is not None and age_days < 1,
    })
    return data


@app.get("/jobs")
def jobs(
    min_score: float = Query(0, ge=0, le=100),
    max_score: float = Query(100, ge=0, le=100),
    location: str = "",
    status: str = "",
    saved: bool | None = None,
    source: str = "",
    company: str = "",
    search: str = "",
    sort: str = Query("recommended", pattern="^(recommended|match|newest|oldest|added)$"),
    added_since_days: int | None = Query(None, ge=0, le=3650),
    posted_since_days: int | None = Query(None, ge=0, le=3650),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Job).filter(Job.score >= min_score, Job.score <= max_score, Job.status != "archived")

    if location:
        if location.lower() in {"remote india", "remote - india"}:
            query = query.filter(Job.location.ilike("%remote%"), Job.location.ilike("%india%"))
        else:
            query = query.filter(Job.location.ilike(f"%{location}%"))
    if status:
        query = query.filter(Job.status == status)
    if saved is not None:
        query = query.filter(Job.saved == saved)
    if source:
        query = query.filter(Job.source.ilike(f"%{source}%"))
    if company:
        query = query.filter(Job.company_name.ilike(f"%{company}%"))
    if search:
        pattern = f"%{search}%"
        query = query.filter((Job.title.ilike(pattern)) | (Job.company_name.ilike(pattern)) | (Job.description.ilike(pattern)))

    now_utc = datetime.now(timezone.utc)
    if added_since_days is not None:
        query = query.filter(Job.first_seen_at >= now_utc - timedelta(days=added_since_days))
    if posted_since_days is not None:
        query = query.filter(Job.posted_at.is_not(None), Job.posted_at >= now_utc - timedelta(days=posted_since_days))

    # Ranking is intentionally done in Python so freshness can be calculated
    # consistently across SQLite and other databases. Pull a bounded candidate
    # set, enrich it, then sort by the selected strategy.
    candidates = query.order_by(desc(Job.score), desc(Job.first_seen_at)).limit(5000).all()
    payloads = [_job_payload(job) for job in candidates]

    if sort == "newest":
        payloads.sort(key=lambda item: (item["age_days"] is None, item["age_days"] if item["age_days"] is not None else 99999, -item["score"]))
    elif sort == "oldest":
        payloads.sort(key=lambda item: (item["age_days"] is None, -(item["age_days"] if item["age_days"] is not None else -1), -item["score"]))
    elif sort == "match":
        payloads.sort(key=lambda item: (item["score"], item["age_days"] is not None, -(item["age_days"] or 99999)), reverse=True)
    elif sort == "added":
        payloads.sort(key=lambda item: item["first_seen_at"] or "", reverse=True)
    else:
        payloads.sort(key=lambda item: (item["priority_score"], item["score"], -(item["age_days"] if item["age_days"] is not None else 99999)), reverse=True)

    return payloads[offset:offset + limit]


@app.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_payload(job)


@app.post("/jobs/{job_id}/refresh-source")
def refresh_source(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        refresh_job_from_source(db, job, timeout=max(5, settings.request_timeout_seconds))
    except Exception as exc:
        raise HTTPException(502, f"Could not refresh source: {exc}")
    return _job_payload(job)


@app.patch("/jobs/{job_id}")
def update_job(
    job_id: int,
    payload: dict | None = None,
    status: str | None = None,
    saved: bool | None = None,
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    payload = payload or {}
    status = payload.get("status", status)
    saved = payload.get("saved", saved)

    if status is not None:
        allowed = {"new", "interested", "applied", "archived"}
        if status not in allowed:
            raise HTTPException(400, f"Invalid status: {status}")
        job.status = status
        if status == "applied":
            job.applied_at = datetime.now(timezone.utc)

    if saved is not None:
        job.saved = saved

    db.commit()
    db.refresh(job)
    return job


@app.post("/scan")
def scan(background_tasks: BackgroundTasks):
    # Start asynchronously so the UI never looks stuck while 100+ sites are crawled.
    state = scan_state()
    if state.get("running"):
        return {"started": False, "running": True, "message": "A scan is already running."}
    background_tasks.add_task(scan_all)
    return {"started": True, "running": True, "message": "Scan started in the background."}


@app.get("/settings")
def get_settings():
    db = SessionLocal()
    try:
        dashboard_refresh = db.get(AppSetting, "dashboard_refresh_ms")
        default_location = db.get(AppSetting, "default_location")
        source_settings = db.get(AppSetting, "source_settings")
        try:
            source_cfg = json.loads(source_settings.value) if source_settings else {}
        except Exception:
            source_cfg = {}
        return {
            "scan_interval_seconds": max(300, int(settings.scan_interval_seconds)),
            "request_timeout_seconds": max(3, int(settings.request_timeout_seconds)),
            "dashboard_refresh_ms": int(dashboard_refresh.value) if dashboard_refresh else 300000,
            "default_location": default_location.value if default_location else "Hyderabad",
            "source_settings": source_cfg or {
                "career_sites": {"enabled": True, "interval_seconds": 600},
                "greenhouse": {"enabled": True, "interval_seconds": 600},
                "lever": {"enabled": True, "interval_seconds": 600},
                "rss": {"enabled": True, "interval_seconds": 600},
                "linkedin": {"enabled": True, "mode": "alert_import"},
                "naukri": {"enabled": True, "mode": "alert_import"},
            },
            "cors_origins": settings.cors_origins,
            "ai_enabled": bool(settings.openai_api_key),
            "linkedin_mode": "alert import (no authenticated scraping)",
            "naukri_mode": "alert import (no authenticated scraping)",
        }
    finally:
        db.close()


@app.patch("/settings")
def update_settings(payload: dict):
    allowed = {
        "scan_interval_seconds", "request_timeout_seconds",
        "dashboard_refresh_ms", "default_location", "source_settings"
    }
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(400, f"Unsupported settings: {', '.join(sorted(unknown))}")

    values = {}
    if "scan_interval_seconds" in payload:
        try:
            value = int(payload["scan_interval_seconds"])
        except Exception:
            raise HTTPException(400, "scan_interval_seconds must be an integer")
        if value < 300 or value > 3600:
            raise HTTPException(400, "scan_interval_seconds must be between 300 and 3600 seconds (5 minutes to 1 hour)")
        values["scan_interval_seconds"] = value

    if "request_timeout_seconds" in payload:
        try:
            value = int(payload["request_timeout_seconds"])
        except Exception:
            raise HTTPException(400, "request_timeout_seconds must be an integer")
        if value < 3 or value > 120:
            raise HTTPException(400, "request_timeout_seconds must be between 3 and 120")
        values["request_timeout_seconds"] = value

    if "dashboard_refresh_ms" in payload:
        try:
            value = int(payload["dashboard_refresh_ms"])
        except Exception:
            raise HTTPException(400, "dashboard_refresh_ms must be an integer")
        if value != 0 and not 1000 <= value <= 3600000:
            raise HTTPException(400, "dashboard_refresh_ms must be 0 or between 1 second and 1 hour")
        values["dashboard_refresh_ms"] = value

    if "default_location" in payload:
        value = str(payload["default_location"]).strip()
        allowed_locations = {"Hyderabad", "Remote India", "Bengaluru", "India", "All target locations"}
        if value not in allowed_locations:
            raise HTTPException(400, "Unsupported default location")
        values["default_location"] = value

    if "source_settings" in payload:
        source_cfg = payload["source_settings"]
        if not isinstance(source_cfg, dict):
            raise HTTPException(400, "source_settings must be an object")
        for source, cfg in source_cfg.items():
            if not isinstance(cfg, dict):
                raise HTTPException(400, f"Invalid configuration for {source}")
            if "interval_seconds" in cfg:
                try:
                    interval = int(cfg["interval_seconds"])
                except Exception:
                    raise HTTPException(400, f"{source} interval must be an integer")
                if interval < 300 or interval > 3600:
                    raise HTTPException(400, f"{source} interval must be between 300 and 3600 seconds")
        values["source_settings"] = json.dumps(source_cfg)

    db = SessionLocal()
    try:
        for key, value in values.items():
            settings_value = db.get(AppSetting, key)
            if settings_value is None:
                settings_value = AppSetting(key=key, value=str(value))
                db.add(settings_value)
            else:
                settings_value.value = str(value)
            if hasattr(settings, key):
                setattr(settings, key, value)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Could not persist settings")
    finally:
        db.close()

    if "scan_interval_seconds" in values and scheduler.running:
        scheduler.reschedule_job(
            "career-scan", trigger="interval", seconds=values["scan_interval_seconds"]
        )

    return get_settings()


@app.post("/admin/cleanup")
def cleanup(db: Session = Depends(get_db)):
    return cleanup_legacy_jobs(db)


@app.post("/imports/linkedin-alert")
def linkedin(payload: dict, db: Session = Depends(get_db)):
    imported = import_linkedin_alert(db, payload.get("text", ""))
    return {"imported": imported}


@app.get("/sources")
def sources(db: Session = Depends(get_db)):
    cfg_row = db.get(AppSetting, "source_settings")
    try:
        cfg = json.loads(cfg_row.value) if cfg_row else {}
    except Exception:
        cfg = {}
    defaults = {
        "career_sites": {"label": "Company Career Sites", "enabled": True, "interval_seconds": 600},
        "greenhouse": {"label": "Greenhouse", "enabled": True, "interval_seconds": 600},
        "lever": {"label": "Lever", "enabled": True, "interval_seconds": 600},
        "rss": {"label": "RSS / Public Feeds", "enabled": True, "interval_seconds": 600},
        "linkedin": {"label": "LinkedIn", "enabled": True, "mode": "alert_import"},
        "naukri": {"label": "Naukri", "enabled": True, "mode": "alert_import"},
    }
    for key, value in cfg.items():
        defaults.setdefault(key, {}).update(value)
    observed = {
        source: count for source, count in db.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
    }
    return [
        {**value, "key": key, "jobs": observed.get(value.get("label"), observed.get(key, 0))}
        for key, value in defaults.items()
    ]


@app.post("/imports/naukri-alert")
def naukri(payload: dict, db: Session = Depends(get_db)):
    from .linkedin import parse_alert
    imported = 0
    company = db.query(Company).filter_by(slug="naukri-alerts").first()
    if not company:
        company = Company(
            name="Naukri Alerts", slug="naukri-alerts", category="Technology",
            priority=75, career_url="https://www.naukri.com/",
            source_type="rss", adapter_config="{}"
        )
        db.add(company); db.commit(); db.refresh(company)
    for item in parse_alert(payload.get("text", "")):
        item.source = "Naukri Alert"
        imported += int(upsert(db, company, item))
    db.commit()
    return {"imported": imported}


@app.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    companies = (
        db.query(Job.company_name, func.count(Job.id), func.avg(Job.score))
        .group_by(Job.company_name)
        .order_by(desc(func.count(Job.id)))
        .limit(20)
        .all()
    )

    locations = (
        db.query(Job.location, func.count(Job.id))
        .filter(Job.location != "")
        .group_by(Job.location)
        .order_by(desc(func.count(Job.id)))
        .limit(20)
        .all()
    )

    return {
        "top_companies": [
            {
                "company": name,
                "jobs": count,
                "average_score": round(float(avg or 0), 1),
            }
            for name, count, avg in companies
        ],
        "locations": [
            {"location": location, "jobs": count}
            for location, count in locations
        ],
    }


# ---------------- Resume intelligence ----------------
def _resume_coverage(content: str, job: Job):
    from .scoring import TECH_ALIASES
    text=(content or "").lower()
    title=(job.title or "").lower()
    body=f"{title} {job.description or ''}".lower()
    required=[name for name,aliases in TECH_ALIASES.items() if any(a in body for a in aliases)]
    exact=[name for name in required if any(re.search(r"\\b"+re.escape(a)+r"\\b", text) for a in TECH_ALIASES[name])]
    gaps=[x for x in required if x not in exact][:12]
    skill_coverage=round((len(exact)/len(required))*100,1) if required else 75.0

    # Blend the existing Job Match with evidence in the uploaded resume.
    # This makes the percentage useful for application decisions without
    # pretending that keyword overlap is the same as real-world ability.
    job_match=float(job.score or 0)
    compatibility=round((job_match * 0.55) + (skill_coverage * 0.45), 1)
    if title:
        role_words=set(re.findall(r"[a-z]{3,}", title))
        role_overlap=sum(1 for word in role_words if word in text)
        role_bonus=min(5.0, role_overlap * 1.25)
        compatibility=min(100.0, round(compatibility + role_bonus, 1))
    return skill_coverage, compatibility, exact, gaps

def _resume_payload(r):
    return {"id":r.id,"name":r.name,"filename":r.filename,"mime_type":r.mime_type,"content":r.content,"is_default":r.is_default,"coverage":r.coverage,"created_at":r.created_at,"updated_at":r.updated_at}

@app.get("/resumes")
def resumes(db: Session=Depends(get_db)):
    return [_resume_payload(r) for r in db.query(Resume).order_by(desc(Resume.is_default),desc(Resume.updated_at)).all()]

@app.post("/resumes/upload")
def upload_resume(file: UploadFile=File(...), name:str=Form(""), db:Session=Depends(get_db)):
    filename=(file.filename or "resume").lower(); data=file.file.read()
    try:
        import io
        if filename.endswith('.pdf'):
            from pypdf import PdfReader
            content="\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages); mime='application/pdf'
        elif filename.endswith('.docx'):
            from docx import Document
            content="\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs); mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif filename.endswith('.txt'):
            content=data.decode('utf-8','ignore'); mime='text/plain'
        else: raise HTTPException(400,'Supported formats: PDF, DOCX or TXT. Convert legacy DOC to DOCX first.')
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400,f'Could not extract resume text: {exc}')
    if not content.strip(): raise HTTPException(400,'No readable text found in the uploaded resume.')
    r=Resume(name=name.strip() or Path(filename).stem,filename=file.filename or '',mime_type=mime,content=content,is_default=db.query(Resume).count()==0)
    db.add(r); db.flush(); db.add(ResumeVersion(resume_id=r.id,label='Initial upload',content=content,source='upload')); db.commit(); db.refresh(r)
    return _resume_payload(r)

@app.patch("/resumes/{resume_id}")
def update_resume(resume_id:int,payload:dict|None=None,name:str|None=None,content:str|None=None,is_default:bool|None=None,db:Session=Depends(get_db)):
    r=db.get(Resume,resume_id)
    if not r: raise HTTPException(404,'Resume not found')
    payload = payload or {}
    name = payload.get("name", name)
    content = payload.get("content", content)
    is_default = payload.get("is_default", is_default)
    if name is not None: r.name=name.strip() or r.name
    if content is not None and content!=r.content:
        db.add(ResumeVersion(resume_id=r.id,label='Manual edit',content=content,source='manual')); r.content=content
    if is_default:
        db.query(Resume).update({Resume.is_default:False}); r.is_default=True
    db.commit(); db.refresh(r); return _resume_payload(r)

@app.get("/resumes/{resume_id}/versions")
def resume_versions(resume_id:int,db:Session=Depends(get_db)):
    if not db.get(Resume,resume_id): raise HTTPException(404,'Resume not found')
    return [{"id":v.id,"resume_id":v.resume_id,"label":v.label,"source":v.source,"created_at":v.created_at} for v in db.query(ResumeVersion).filter_by(resume_id=resume_id).order_by(desc(ResumeVersion.created_at)).all()]

@app.post("/resumes/{resume_id}/versions/{version_id}/restore")
def restore_resume_version(resume_id:int, version_id:int, db:Session=Depends(get_db)):
    r=db.get(Resume,resume_id)
    v=db.get(ResumeVersion,version_id)
    if not r or not v or v.resume_id != resume_id: raise HTTPException(404,"Resume/version not found")
    db.add(ResumeVersion(resume_id=r.id,label=f"Restored v{v.id}",content=v.content,source="restore"))
    r.content=v.content
    db.commit(); db.refresh(r)
    return _resume_payload(r)


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id:int, db:Session=Depends(get_db)):
    r=db.get(Resume,resume_id)
    if not r: raise HTTPException(404,"Resume not found")
    was_default=r.is_default
    db.query(ResumeVersion).filter(ResumeVersion.resume_id==resume_id).delete(synchronize_session=False)
    db.delete(r); db.commit()
    if was_default:
        replacement=db.query(Resume).order_by(desc(Resume.updated_at)).first()
        if replacement:
            replacement.is_default=True; db.commit()
    return {"deleted":True}

@app.get("/resumes/{resume_id}/export")
def export_resume(resume_id:int,format:str=Query('docx',pattern='^(docx|pdf|txt)$'),db:Session=Depends(get_db)):
    r=db.get(Resume,resume_id)
    if not r: raise HTTPException(404,'Resume not found')
    import io
    safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in r.name).strip('_') or 'resume'
    if format=='txt': return Response(r.content,media_type='text/plain',headers={'Content-Disposition':f'attachment; filename="{safe}.txt"'})
    if format=='docx':
        from docx import Document
        doc=Document()
        for line in r.content.splitlines(): doc.add_paragraph(line)
        out=io.BytesIO(); doc.save(out)
        return Response(out.getvalue(),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="{safe}.docx"'})
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=LETTER); _,height=LETTER; y=height-50
    for raw in r.content.splitlines():
        c.drawString(40,y,raw[:110]); y-=14
        if y<45: c.showPage(); y=height-50
    c.save(); return Response(out.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{safe}.pdf"'})

@app.post("/jobs/{job_id}/analyze")
def analyze_job_endpoint(job_id:int, db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,"Job not found")
    if not settings.openai_api_key:
        return {"status":"unavailable","message":"AI analysis is not configured. Add a valid OPENAI_API_KEY to .env and recreate the backend container."}
    analysis=analyze_job(job.title,job.company_name,job.location,job.description or "",float(job.score or 0))
    if not analysis:
        return {"status":"unavailable","message":"AI analysis is unavailable right now. The Job Match score is still available."}
    job.ai_analysis=analysis
    db.commit(); db.refresh(job)
    return {"status":"ok","analysis":analysis}

@app.get("/jobs/{job_id}/resume-analysis")
def job_resume_analysis(job_id:int,resume_id:int|None=None,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Job not found')
    r=db.get(Resume,resume_id) if resume_id else db.query(Resume).filter_by(is_default=True).first()
    if not r: return {"resume":None,"coverage":None,"exact_skills":[],"gaps":[],"message":"Upload a resume to calculate coverage."}
    coverage,compatibility,exact,gaps=_resume_coverage(r.content,job)
    return {"resume":_resume_payload(r),"job_match":float(job.score or 0),"coverage":coverage,"compatibility":compatibility,"exact_skills":exact,"gaps":gaps,"message":"Compatibility blends Job Match with resume evidence coverage."}

@app.post("/jobs/{job_id}/optimize-resume")
def optimize_resume(job_id:int,resume_id:int|None=None,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job: raise HTTPException(404,'Job not found')
    r=db.get(Resume,resume_id) if resume_id else db.query(Resume).filter_by(is_default=True).first()
    if not r: raise HTTPException(400,'Upload a resume first')
    coverage,compatibility,exact,gaps=_resume_coverage(r.content,job)
    suggestions=[f'Surface truthful evidence for {g} if you have it.' for g in gaps[:6]]
    suggestions += ['Prioritize bullets that demonstrate the target role and measurable reliability impact.','Never add a technology, responsibility, metric or certification you do not actually have.']
    optimized=None
    if settings.openai_api_key:
        try:
            from openai import OpenAI
            c=OpenAI(api_key=settings.openai_api_key)
            prompt=f"""Rewrite this resume for the target job. Preserve only truthful facts already present. Do not invent skills, employers, metrics or responsibilities. Improve ordering, wording and emphasis. Return only the complete revised resume text.\nJOB: {job.title} at {job.company_name}\nJD:\n{job.description[:12000]}\nRESUME:\n{r.content[:30000]}"""
            optimized=c.responses.create(model=settings.openai_model,input=prompt).output_text.strip()
        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "invalid_api_key" in msg or "Incorrect API key" in msg:
                suggestions.append('AI generation unavailable. Add a valid OPENAI_API_KEY in .env and restart the backend.')
            else:
                suggestions.append('AI generation is temporarily unavailable. Your resume match and coverage scores are still available.')
    return {"resume_id":r.id,"job_match":float(job.score or 0),"coverage":coverage,"compatibility":compatibility,"exact_skills":exact,"gaps":gaps,"suggestions":suggestions,"optimized_content":optimized}
