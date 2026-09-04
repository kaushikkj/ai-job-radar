from app.collectors.ats import _looks_like_job_path, fingerprint
from app.scoring import score_job


def test_lpl_job_url_is_recognized():
    url = (
        "https://careers.lplfinancial.in/in/en/job/"
        "R-052374/Engineer-II-Cloud-Monitoring-Engineer?source=LinkedIn"
    )
    assert _looks_like_job_path(url)


def test_company_career_homepage_is_not_job():
    assert not _looks_like_job_path("https://careers.microsoft.com/")
    assert not _looks_like_job_path("https://www.elastic.co/observability/llm-monitoring")


def test_tracking_parameter_does_not_change_fingerprint():
    a = fingerprint(
        "Senior SRE",
        "https://example.com/job/123?source=LinkedIn",
        "Example",
    )
    b = fingerprint(
        "Senior SRE",
        "https://example.com/job/123?utm_source=linkedin",
        "Example",
    )
    assert a == b


def test_hyderabad_has_highest_location_priority():
    score = score_job(
        "Senior Site Reliability Engineer",
        "Hyderabad, Telangana, India",
        "Python Kubernetes AWS Terraform observability CI/CD",
        100,
        "Technology",
    )
    assert score.location == 15
