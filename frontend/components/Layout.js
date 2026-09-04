import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const REFRESH_OPTIONS = [
  { label: "5 minutes", value: 300000 }, { label: "10 minutes", value: 600000 },
  { label: "15 minutes", value: 900000 }, { label: "30 minutes", value: 1800000 },
  { label: "1 hour", value: 3600000 }, { label: "Off", value: 0 },
];
export const SCAN_OPTIONS = [
  { label: "5 minutes", value: 300 }, { label: "10 minutes", value: 600 },
  { label: "15 minutes", value: 900 }, { label: "30 minutes", value: 1800 },
  { label: "1 hour", value: 3600 },
];
const REFRESH_KEY = "ai-job-radar-dashboard-refresh-ms";
const THEME_KEY = "ai-job-radar-theme";
const LOCATION_KEY = "ai-job-radar-default-location";

export function useRefreshRate() {
  const [refreshMs, setRefreshMs] = useState(300000);
  useEffect(() => {
    let active = true;
    const sync = async () => {
      const saved = window.localStorage.getItem(REFRESH_KEY);
      if (saved !== null) setRefreshMs(Number(saved) || 0);
      try {
        const r = await fetch(`${API}/settings?_t=${Date.now()}`, { cache: "no-store" });
        if (r.ok && active) {
          const d = await r.json();
          const value = Number(d.dashboard_refresh_ms ?? 300000);
          setRefreshMs(value);
          window.localStorage.setItem(REFRESH_KEY, String(value));
        }
      } catch {}
    };
    sync();
    window.addEventListener("radar-refresh-change", sync);
    window.addEventListener("storage", sync);
    return () => { active = false; window.removeEventListener("radar-refresh-change", sync); window.removeEventListener("storage", sync); };
  }, []);
  return refreshMs;
}

export function getDefaultLocation() {
  if (typeof window === "undefined") return "Hyderabad";
  return window.localStorage.getItem(LOCATION_KEY) || "Hyderabad";
}
export function setDefaultLocation(value) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LOCATION_KEY, value || "Hyderabad");
  window.dispatchEvent(new Event("radar-location-change"));
}

function RefreshControl() {
  const refreshMs = useRefreshRate();
  async function change(value) {
    const ms = Number(value);
    window.localStorage.setItem(REFRESH_KEY, String(ms));
    window.dispatchEvent(new Event("radar-refresh-change"));
    try {
      const r = await fetch(`${API}/settings`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({dashboard_refresh_ms:ms})});
      if (r.ok) {
        const d = await r.json();
        const saved = Number(d.dashboard_refresh_ms ?? ms);
        window.localStorage.setItem(REFRESH_KEY, String(saved));
        window.dispatchEvent(new Event("radar-refresh-change"));
      }
    } catch {}
  }
  return <label className="refresh-control" title="Dashboard-only data refresh interval"><span>↻</span><select value={refreshMs} onChange={e => change(e.target.value)} aria-label="Dashboard refresh interval">{REFRESH_OPTIONS.map(x => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>{refreshMs ? `Dashboard ${REFRESH_OPTIONS.find(x => x.value === refreshMs)?.label || ""}` : "Dashboard refresh off"}</small></label>;
}

function ThemeButton() {
  const [theme, setTheme] = useState("dark");
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY) || "dark"; setTheme(saved); document.documentElement.dataset.theme = saved;
  }, []);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark"; setTheme(next); localStorage.setItem(THEME_KEY, next); document.documentElement.dataset.theme = next; window.dispatchEvent(new Event("radar-theme-change"));
  }
  return <button className="icon-button" onClick={toggle} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} aria-label="Toggle theme">{theme === "dark" ? "☀" : "☾"}</button>;
}

export function formatDate(value) { if (!value) return "Not available"; const date = new Date(value); if (Number.isNaN(date.getTime())) return "Not available"; return date.toLocaleString([], { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
export function shortDate(value) { if (!value) return "Date unavailable"; const date = new Date(value); if (Number.isNaN(date.getTime())) return "Date unavailable"; return date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }); }
export function ageLabel(job) { if (job?.age_days === null || job?.age_days === undefined) return "Date unavailable"; const age = Number(job.age_days); if (age < 0.04) return "Posted just now"; if (age < 1) return `Posted ${Math.max(1, Math.round(age * 24))}h ago`; if (age < 2) return "Posted yesterday"; if (age < 7) return `Posted ${Math.floor(age)}d ago`; if (age < 30) return `Posted ${Math.floor(age / 7)}w ago`; return `Posted ${Math.floor(age / 30)}mo ago`; }
export function dateLabel(job) { if (!job?.posted_at) return "Publication date unavailable"; const source = (job.posted_at_source || "").toLowerCase(); const label = source.includes("updated") || source.includes("modified") ? "Updated" : "Published"; return `${label} ${shortDate(job.posted_at)}`; }

export function Layout({ children, scanState, onScan, scanning = false }) {
  const router = useRouter(); const [stats, setStats] = useState({}); const [scan, setScan] = useState(scanState || {});
  useEffect(() => {
    let active = true;
    Promise.all([fetch(`${API}/stats`, { cache: "no-store" }), fetch(`${API}/scan/status`, { cache: "no-store" })]).then(async ([a,b]) => {
      if (!active) return; if (a.ok) setStats(await a.json()); if (b.ok) setScan(await b.json());
    }).catch(() => {});
    return () => { active = false; };
  }, [router.pathname]);
  const counts = useMemo(() => ({ match90: stats.match90 || 0, match80: stats.match80 || 0, match70: stats.match70 || 0, shortlist: stats.shortlist || 0, applied: stats.applied || 0 }), [stats]);
  const activeJobs = router.pathname === "/jobs" || router.pathname.startsWith("/jobs/") || router.pathname.startsWith("/matches");
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-top"><Link href="/" className="brand"><span className="brand-mark">⚡</span><span>AI Job Radar</span></Link><div className="brand-subtitle">Your personal job radar</div></div>
      <nav className="nav">
        <Link href="/" className={`nav-link ${router.pathname === "/" ? "active" : ""}`}><span className="nav-icon">⌂</span><span className="nav-label">Dashboard</span></Link>
        <Link href="/jobs" className={`nav-link ${activeJobs ? "active-parent" : ""}`}><span className="nav-icon">▣</span><span className="nav-label">Jobs</span></Link>
        <Link href="/shortlist" className={`nav-link ${router.pathname === "/shortlist" ? "active" : ""}`}><span className="nav-icon">♡</span><span className="nav-label">Shortlist</span><span className="nav-count">{counts.shortlist}</span></Link>
        <Link href="/applied" className={`nav-link ${router.pathname === "/applied" ? "active" : ""}`}><span className="nav-icon">✓</span><span className="nav-label">Applied</span><span className="nav-count">{counts.applied}</span></Link>
        {[['/companies','▤','Companies'],['/resumes','▤','Resumes'],['/analytics','◫','Analytics'],['/alerts','♧','Alerts'],['/profile','♙','Profile'],['/settings','⚙','Settings']].map(([href,icon,label]) => <Link key={href} href={href} className={`nav-link ${router.pathname === href ? "active" : ""}`}><span className="nav-icon">{icon}</span><span className="nav-label">{label}</span></Link>)}
      </nav>
      <div className="scanner-card"><div className="scanner-title"><span className={`pulse ${scan.running || scanning ? "running" : ""}`} />{scan.running || scanning ? "AI Scanning" : "AI Scanner"}<span className="scanner-live">{scan.running || scanning ? "LIVE" : "Ready"}</span></div><div className="scanner-copy">Career sites · LinkedIn Alerts · RSS · ATS · Naukri Alerts · {scan?.scan_interval_seconds ? `${Math.round(scan.scan_interval_seconds/60)}-min scan` : "scheduled scan"}</div><div className="scanner-time">{scan?.next_run_at ? `Next scan: ${formatDate(scan.next_run_at)}` : "Scanner ready"}</div><button className="primary full" onClick={onScan} disabled={scanning || scan.running}>{scanning || scan.running ? "Scan running…" : "Run Scan Now"}</button></div>
    </aside>
    <main className="main"><header className="topbar"><div className="search-placeholder">⌕ <span>Search jobs, companies, skills...</span></div><div className="top-actions"><RefreshControl/><span>🔔</span><ThemeButton/><span className="avatar">K</span><b>Kaushik</b><span>▾</span></div></header>{children}</main>
  </div>;
}

export function useScan(onComplete) { return async function runScan() { try { const response = await fetch(`${API}/scan`, { method: "POST", cache: "no-store" }); const result = await response.json(); onComplete?.(result); return result; } catch { const result = { started: false, errors: ["Unable to reach the backend."] }; onComplete?.(result); return result; } }; }
