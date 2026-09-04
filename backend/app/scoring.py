import re
from dataclasses import dataclass

from .profile import PROFILE


GROUPS = {
    "sre": [
        "sre", "site reliability", "reliability engineer", "production engineer",
        "infrastructure reliability", "reliability", "production engineering",
    ],
    "devops": [
        "devops", "cloud engineer", "cloud infrastructure", "infrastructure engineer",
        "cloud platform", "devops engineer", "cloud operations",
    ],
    "platform": [
        "platform engineer", "platform reliability", "developer platform",
        "infrastructure platform", "platform engineering", "developer infrastructure",
    ],
    "software": [
        "senior software engineer", "senior backend engineer", "software engineer - infrastructure",
        "software engineer - platform", "software engineer - cloud", "software engineer - devops",
        "software engineer", "backend engineer", "software development engineer",
    ],
    "dbre": [
        "database reliability", "dbre", "database platform", "database infrastructure",
        "database engineer", "database reliability engineer",
    ],
}

TECH_ALIASES = {
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Azure": ["azure", "microsoft azure"],
    "Python": ["python"],
    "Docker": ["docker", "containerization", "containers"],
    "Helm": ["helm"],
    "ArgoCD": ["argocd", "argo cd", "argo-cd"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "GitOps": ["gitops"],
    "Prometheus": ["prometheus"],
    "Grafana": ["grafana"],
    "Datadog": ["datadog"],
    "Observability": ["observability", "monitoring", "telemetry"],
    "Microservices": ["microservices", "microservices architecture"],
    "SQL": ["sql", "postgresql", "mysql", "oracle database", "relational database"],
    "Kafka": ["kafka", "apache kafka"],
    "Automation": ["automation", "scripting", "python automation"],
}

LOCATION_WEIGHTS = [
    ("hyderabad", 15),
    ("remote india", 13),
    ("remote - india", 13),
    ("bengaluru", 10),
    ("bangalore", 10),
    ("remote", 12),
    ("india", 5),
]


@dataclass
class Score:
    total: float
    role: float
    technical: float
    experience: float
    location: float
    company: float
    industry: float
    reason: str
    skills: list[str]
    gaps: list[str]


def normalize(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _has_alias(text, aliases):
    return any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text) for alias in aliases)


def score_job(title, location, description, priority, category):
    title_n = normalize(title)
    body = normalize(f"{title} {description}")
    location_n = normalize(location)

    title_groups = [group for group, terms in GROUPS.items() if any(term in title_n for term in terms)]
    body_groups = [group for group, terms in GROUPS.items() if any(term in body for term in terms)]
    groups = list(dict.fromkeys(title_groups or body_groups))

    if title_groups:
        role = 28
    elif body_groups:
        role = 20
    else:
        role = 7

    seniority_terms = ("senior", "staff", "lead", "principal", "architect", " iii", " ii", "level 3", "level 4")
    if any(term in f" {title_n}" for term in seniority_terms):
        role += 2
    role = min(30, role)

    skills = [name for name, aliases in TECH_ALIASES.items() if _has_alias(body, aliases)]
    technical = min(25, round(len(skills) / 10 * 25, 1))

    match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|yrs)", body)
    required_years = float(match.group(1)) if match else None
    if required_years is not None:
        if required_years <= PROFILE["experience_years"]:
            experience = 15
        else:
            experience = max(5, 15 - (required_years - PROFILE["experience_years"]) * 2.5)
    elif any(term in title_n for term in ("senior", "staff", "lead", "principal", " ii", " iii")):
        experience = 14
    else:
        experience = 11

    location_score = next((weight for key, weight in LOCATION_WEIGHTS if key in location_n), 5)
    company = min(10, max(1, priority / 10))

    preferred = [normalize(x) for x in PROFILE["preferred_industries"]]
    category_n = normalize(category)
    industry = 5 if any(x in category_n for x in preferred) else 3

    total = min(100, round(role + technical + experience + location_score + company + industry, 1))

    core_gaps = ["Kubernetes", "Terraform", "AWS", "Python", "Observability", "CI/CD"]
    gaps = [skill for skill in core_gaps if skill not in skills][:4]

    reason_parts = []
    if title_groups:
        reason_parts.append("Target role family appears directly in the title.")
    elif body_groups:
        reason_parts.append("Role family is inferred from the job description.")
    else:
        reason_parts.append("Limited direct role-family overlap.")
    if skills:
        reason_parts.append(f"Technical overlap: {', '.join(skills[:7])}.")
    if location_score >= 13:
        reason_parts.append("High-priority Hyderabad/Remote India location signal.")
    elif location_score >= 10:
        reason_parts.append("Strong Bengaluru location signal.")

    return Score(
        total,
        round(role, 1),
        technical,
        round(experience, 1),
        location_score,
        round(company, 1),
        industry,
        " ".join(reason_parts),
        skills[:10],
        gaps,
    )
