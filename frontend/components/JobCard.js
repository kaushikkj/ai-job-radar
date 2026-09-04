import Link from "next/link";
import { API, ageLabel, dateLabel, formatDate } from "./Layout";

function initials(name) {
  return (name || "?").split(/\s+/).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
}

function reasons(text) {
  if (!text) return [];
  return text.split(/[.;•]+/).map((x) => x.trim()).filter(Boolean).slice(0, 3);
}

export default function JobCard({ job, onChange }) {
  async function patch(body) {
    try {
      await fetch(`${API}/jobs/${job.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
      onChange?.();
    } catch {}
  }
  const score = Math.round(job.score || 0);
  const priority = Math.round(job.priority_score || score);
  const reasonList = reasons(job.match_reason);
  const isNew = job.is_new_today || (job.age_days != null && job.age_days < 1);

  return (
    <article className="job-card-v2">
      <div className="job-logo">{initials(job.company_name)}</div>
      <div className="job-card-content">
        <div className="job-card-head">
          <div className="job-card-title-wrap">
            <Link href={`/jobs/${job.id}`} className="job-title">{job.title}</Link>
            <div className="company-line"><b>{job.company_name}</b><span>·</span><span>{job.location || "Location not specified"}</span><span>·</span><span>{job.source || "Career Site"}</span></div>
          </div>
          <div className="job-score-column"><span className={`score-badge ${score >= 81 ? "hot" : score >= 71 ? "good" : ""}`}>{score}% MATCH</span>{isNew && <span className="new-badge">NEW</span>}</div>
        </div>
        <div className="date-row"><span>🗓 {dateLabel(job)}</span><span>•</span><span>{ageLabel(job)}</span><span>•</span><span>Added to Radar {formatDate(job.first_seen_at)}</span></div>
        <div className="tag-list">{(job.skills || []).slice(0, 7).map((s) => <span className="tag" key={s}>{s}</span>)}</div>
        {reasonList.length > 0 && <div className="why-box compact"><div className="why-heading"><strong>Why this matches</strong><span className="priority-badge">Priority {priority}</span></div><ul>{reasonList.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
        <div className="job-bottom"><div className="job-score-meta"><b>Radar Priority {priority}</b><span>Freshness {Math.round(job.freshness_score || 0)}/100</span></div><div className="job-actions-row"><button className="ghost" onClick={() => patch({ saved: !job.saved })}>{job.saved ? "★ Saved" : "☆ Save"}</button><button className="ghost" onClick={() => patch({ status: "interested" })}>Interested</button><Link href={`/jobs/${job.id}`} className="secondary small">View Job</Link><a className="primary small" href={job.url} target="_blank" rel="noreferrer">Apply ↗</a></div></div>
      </div>
    </article>
  );
}
