import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import JobCard from "../components/JobCard";
import { API, Layout, getDefaultLocation } from "../components/Layout";

const config = {
  jobs: {
    title: "All Jobs",
    subtitle: "Every active job collected from monitored sources.",
    min: 0,
  },
  matches: {title:"91–100% Matches",subtitle:"Exceptional profile matches.",min:91,max:100},
  "matches-81": {title:"81–90% Matches",subtitle:"Excellent profile matches.",min:81,max:90},
  "matches-71": {title:"71–80% Matches",subtitle:"Strong profile matches.",min:71,max:80},
  "matches-61": {title:"61–70% Matches",subtitle:"Relevant profile matches.",min:61,max:70},
  "matches-51": {title:"51–60% Matches",subtitle:"Potential profile matches.",min:51,max:60},
  "matches-0": {title:"0–50% Matches",subtitle:"Low-fit jobs for review.",min:0,max:50},
  shortlist: {
    title: "Shortlist",
    subtitle: "Jobs you marked for follow-up.",
    saved: true,
  },
  applied: {
    title: "Applied",
    subtitle: "Your application pipeline.",
    status: "applied",
  },
};

export default function View() {
  const { query } = useRouter();
  const view = query.view;
  const [jobs, setJobs] = useState([]);
  const [search, setSearch] = useState("");
  const [location, setLocation] = useState("Hyderabad");
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState(view === "jobs" ? "newest" : "recommended");
  const [message, setMessage] = useState("");
  const [postedSince, setPostedSince] = useState("");

  const settings = config[view] || config.jobs;

  async function reload() {
    setLoading(true);
    const params = new URLSearchParams({
      limit: "500",
      min_score: String(settings.min ?? 0),
      max_score: String(settings.max ?? 100),
    });
    if (settings.saved) params.set("saved", "true");
    if (settings.status) params.set("status", settings.status);
    if (search) params.set("search", search);
    if (location) params.set("location", location);
    params.set("sort", sort);
    if (postedSince) params.set("posted_since_days", postedSince);

    try {
      const response = await fetch(`${API}/jobs?${params}`);
      setJobs(await response.json());
    } catch {
      setMessage("Unable to load jobs.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (typeof window !== "undefined") setLocation(getDefaultLocation());
    if (typeof window !== "undefined") setPostedSince(new URLSearchParams(window.location.search).get("posted_since_days") || "");
  }, [view]);
  useEffect(() => { if (view) reload(); }, [view, search, location, sort, postedSince]);



  return (
    <Layout
      scanState={{}}
      onScan={() => {
        setMessage("Use Scan Now in the sidebar to start a scan.");
      }}
    >
      <section className="page">
        <div className="page-heading">
          <div>
            <div className="eyebrow">JOB PIPELINE</div>
            <h1>{settings.title}</h1>
            <p>{settings.subtitle}</p>
          </div>
          <Link href="/" className="secondary button-link">← Dashboard</Link>
        </div>

        <div className="filter-bar">
          <input
            placeholder="Search title, company or skill..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select value={location} onChange={(e) => setLocation(e.target.value)}>
            <option value="">All locations</option>
            <option>Hyderabad</option>
            <option>Remote India</option>
            <option>Bengaluru</option>
            <option>India</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="recommended">Recommended</option><option value="newest">Newest published</option><option value="added">Recently added to Radar</option><option value="match">Highest match</option><option value="oldest">Oldest published</option>
          </select>
          <select value={postedSince} onChange={(e)=>{ const v=e.target.value; setPostedSince(v); const url=new URL(window.location.href); url.searchParams.delete("posted_since_days"); if(v) url.searchParams.set("posted_since_days",v); window.history.replaceState({},"",url); }}><option value="">Published: Any time</option><option value="1">Published: Last 24h</option><option value="3">Published: Last 3d</option><option value="7">Published: Last 7d</option><option value="14">Published: Last 14d</option><option value="30">Published: Last 30d</option></select>
          <span className="result-count">{jobs.length} jobs</span>
        </div>

        {message && <div className="notice">{message}</div>}

        {loading ? (
          <div className="empty">Loading jobs...</div>
        ) : jobs.length === 0 ? (
          <div className="empty">
            <h3>No jobs here yet</h3>
            <p>Run a scan or change your filters.</p>
          </div>
        ) : (
          jobs.map((job) => <JobCard key={job.id} job={job} onChange={reload} />)
        )}
      </section>
    </Layout>
  );
}
