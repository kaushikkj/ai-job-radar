import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import JobCard from "../components/JobCard";
import { API, Layout, formatDate, getDefaultLocation, useRefreshRate } from "../components/Layout";

const bands = [
  ["91–100%", "91-100", "Exceptional", "match90", "/matches"],
  ["81–90%", "81-90", "Excellent", "match80", "/matches-81"],
  ["71–80%", "71-80", "Strong", "match70", "/matches-71"],
  ["61–70%", "61-70", "Relevant", "match60", "/matches-61"],
];

export default function Dashboard() {
  const [stats,setStats]=useState({}),[jobs,setJobs]=useState([]),[scan,setScan]=useState({}),[location,setLocation]=useState("Hyderabad"),[greeting,setGreeting]=useState("Good day"),[scoreBand,setScoreBand]=useState("all"),[sort,setSort]=useState("recommended"),[freshness,setFreshness]=useState(""),[loading,setLoading]=useState(false),[message,setMessage]=useState(""),[lastRefresh,setLastRefresh]=useState(null),[scanInterval,setScanInterval]=useState(300);
  const refreshMs=useRefreshRate(), requestSeq=useRef(0), mounted=useRef(true);
  useEffect(()=>{setLocation(getDefaultLocation()); return ()=>{mounted.current=false}},[]);
  useEffect(()=>{
    const updateGreeting=()=>{
      const hour=new Date().getHours();
      if(hour>=5 && hour<12) setGreeting("Good morning");
      else if(hour>=12 && hour<17) setGreeting("Good afternoon");
      else if(hour>=17 && hour<21) setGreeting("Good evening");
      else setGreeting("Good night");
    };
    updateGreeting();
    const timer=setInterval(updateGreeting,60000);
    return()=>clearInterval(timer);
  },[]);
  const reload=useCallback(async({silent=true}={})=>{const seq=++requestSeq.current;if(!silent)setLoading(true);const band=scoreBand==="all"?[0,100]:scoreBand.split("-").map(Number);const url=new URL(`${API}/jobs`);url.searchParams.set("min_score",band[0]);url.searchParams.set("max_score",band[1]);url.searchParams.set("location",location);url.searchParams.set("sort",sort);url.searchParams.set("limit","100");if(freshness.startsWith("posted:"))url.searchParams.set("posted_since_days",freshness.split(":")[1]);if(freshness.startsWith("added:"))url.searchParams.set("added_since_days",freshness.split(":")[1]);try{const [a,b,c,d]=await Promise.all([fetch(`${API}/stats?_t=${Date.now()}`,{cache:"no-store"}),fetch(url.toString(),{cache:"no-store"}),fetch(`${API}/scan/status?_t=${Date.now()}`,{cache:"no-store"}),fetch(`${API}/settings?_t=${Date.now()}`,{cache:"no-store"})]);if(!a.ok||!b.ok||!c.ok)throw new Error();const [ns,nj,nc]=await Promise.all([a.json(),b.json(),c.json()]);if(!mounted.current||seq!==requestSeq.current)return;setStats(ns);setJobs(Array.isArray(nj)?nj:[]);setScan(nc||{});if(d.ok){const cfg=await d.json();setScanInterval(cfg.scan_interval_seconds||300)}setLastRefresh(new Date())}catch{if(!silent&&mounted.current)setMessage("Could not refresh. Keeping the last successful results.")}finally{if(!silent&&mounted.current)setLoading(false)}},[scoreBand,location,sort,freshness]);
  useEffect(()=>{reload({silent:false})},[reload]);
  useEffect(()=>{if(!refreshMs)return;const t=setInterval(()=>reload({silent:true}),refreshMs);return()=>clearInterval(t)},[refreshMs,reload]);
  // Poll scanner status independently; this does not reload the dashboard jobs.
  useEffect(()=>{let active=true;const poll=async()=>{try{const r=await fetch(`${API}/scan/status?_t=${Date.now()}`,{cache:"no-store"});if(r.ok&&active)setScan(await r.json())}catch{}};poll();const t=setInterval(poll,1000);return()=>{active=false;clearInterval(t)}},[]);
  async function runScan(){if(loading||scan.running)return;setMessage("Starting background scan…");try{const r=await fetch(`${API}/scan`,{method:"POST",cache:"no-store"});const d=await r.json();setMessage(d.started?"Scan started in the background. New jobs will appear after each site is processed.":(d.message||"A scan is already running."));setTimeout(()=>reload({silent:true}),700)}catch{setMessage("Scan request failed. Existing results were kept.")}}
  async function changeScanInterval(value){const seconds=Number(value);setScanInterval(seconds);try{const r=await fetch(`${API}/settings`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({scan_interval_seconds:seconds})});if(!r.ok)throw new Error();setMessage(`Career-site monitoring interval saved: ${seconds < 60 ? `${seconds}s` : `${seconds/60}m`}.`)}catch{setMessage("Could not change the scanner interval.")}}
  return <Layout scanState={scan} onScan={runScan} scanning={false}>
    <section className="page dashboard-page">
      <div className="dashboard-hero">
        <div><div className="eyebrow">PERSONAL JOB RADAR</div><h1>{greeting}, Kaushik! <span>👋</span></h1><p>Hyderabad-first opportunities ranked by match, freshness and application priority.</p></div>
        <div className="dashboard-hero-actions"><div className="scan-setting-inline"><span>Career scan</span><select value={scanInterval} onChange={e=>changeScanInterval(e.target.value)}>{[{label:"5m",value:300},{label:"10m",value:600},{label:"15m",value:900},{label:"30m",value:1800},{label:"1h",value:3600}].map(x=><option key={x.value} value={x.value}>{x.label}</option>)}</select></div><button className="primary scan-button" onClick={runScan} disabled={scan.running}>{scan.running?"Scanning…":"↻ Scan now"}</button></div>
      </div>
      {message&&<div className="notice">{message}</div>}

      <div className="dashboard-section-head"><div><span className="section-kicker">OVERVIEW</span><h2>Job pipeline</h2></div><span className="muted">Updated {lastRefresh?lastRefresh.toLocaleTimeString():"just now"}</span></div>
      <div className="overview-grid">
        <Link href="/jobs" className="overview-card-link"><div className="overview-card primary-stat"><span>Total jobs</span><strong>{stats.total||0}</strong><small>Across monitored sources</small></div></Link>
        <Link href="/jobs?new=today" className="overview-card-link"><div className="overview-card"><span>New today</span><strong>{stats.published_today||0}</strong><small>Fresh opportunities</small></div></Link>
        <Link href="/applied" className="overview-card-link"><div className="overview-card"><span>Applied</span><strong>{stats.applied||0}</strong><small>Applications tracked</small></div></Link>
        <Link href="/shortlist" className="overview-card-link"><div className="overview-card"><span>Shortlisted</span><strong>{stats.shortlist||0}</strong><small>Saved for later</small></div></Link>
      </div>

      <div className="dashboard-section-head match-section-head"><div><span className="section-kicker">MATCH QUALITY</span><h2>Best-fit opportunities</h2></div><Link href="/jobs" className="text-link">View all jobs →</Link></div>
      <div className="match-band-grid">{bands.map(([label,range,caption,key,href])=><Link href={href} key={label} className="match-band-link"><div className={`match-band-card ${key}`}><div className="match-band-top"><span>{label}</span><span>→</span></div><strong>{stats[key]||0}</strong><p>{caption} matches</p><small>Open matching jobs</small></div></Link>)}</div>

      <div className="dashboard-main-grid">
        <div className="main-column">
          <div className="dashboard-list-head"><div><span className="section-kicker">LIVE JOB FEED</span><h2>Hyderabad opportunities</h2><p>Prioritized by match score and freshness.</p></div><div className="dashboard-filterbar"><label><span>Location</span><select value={location} onChange={e=>setLocation(e.target.value)}><option>Hyderabad</option><option>Remote India</option><option>Bengaluru</option><option>India</option><option value="">All locations</option></select></label><label><span>Match</span><select value={scoreBand} onChange={e=>setScoreBand(e.target.value)}><option value="all">All scores</option>{bands.map(([label,value])=><option key={value} value={value}>{label}</option>)}</select></label><label><span>Sort</span><select value={sort} onChange={e=>setSort(e.target.value)}><option value="recommended">Recommended</option><option value="newest">Newest</option><option value="added">Recently added</option><option value="match">Highest match</option><option value="oldest">Oldest</option></select></label><label><span>Freshness</span><select value={freshness} onChange={e=>setFreshness(e.target.value)}><option value="">Any time</option><option value="posted:1">Published · 24h</option><option value="posted:3">Published · 3d</option><option value="posted:7">Published · 7d</option><option value="posted:14">Published · 14d</option><option value="posted:30">Published · 30d</option><option value="added:1">Added · 24h</option><option value="added:3">Added · 3d</option><option value="added:7">Added · 7d</option><option value="added:30">Added · 30d</option></select></label></div></div>
          <div className="list-toolbar"><span><b>{jobs.length}</b> opportunities</span><span className="list-note">Dashboard refreshes automatically</span></div>
          {jobs.length===0?<div className="empty"><h3>No Hyderabad jobs yet</h3><p>The next scan will refresh monitored career sources. You can also run a scan now.</p></div>:jobs.slice(0,25).map(job=><JobCard key={job.id} job={job} onChange={()=>reload({silent:true})}/>)}
        </div>
        <aside className="dashboard-side">
          <div className="panel scanner-panel dashboard-side-card"><div className="panel-title-row"><div><span className="section-kicker">MONITORING</span><h3>Career scanner</h3></div><span className={`live-pill ${scan.running?"live":""}`}>● {scan.running?"SCANNING":"READY"}</span></div><div className="scanner-status"><span className={`status-dot ${scan.running?"busy":""}`}/>{scan.running?"Processing monitored sources":"Automatic monitoring enabled"}</div><div className="scanner-control-row"><span>Scan every</span><select value={scanInterval} onChange={e=>changeScanInterval(e.target.value)}>{[{label:"5 min",value:300},{label:"10 min",value:600},{label:"15 min",value:900},{label:"30 min",value:1800},{label:"1 hour",value:3600}].map(x=><option key={x.value} value={x.value}>{x.label}</option>)}</select></div><p>Career sites · ATS feeds · LinkedIn/Naukri alert imports</p>{scan.finished_at&&<div className="scanner-last"><span>Last completed</span><b>{formatDate(scan.finished_at)}</b></div>}{scan.last_result&&<div className="scanner-last"><span>Last result</span><b>{scan.last_result.collected||0} postings · {scan.last_result.new||0} new</b></div>}{scan.next_run_at&&<div className="scanner-last"><span>Next scan</span><b>{formatDate(scan.next_run_at)}</b></div>}</div>
          <div className="panel dashboard-side-card focus-card"><div className="panel-title-row"><h3>Focus</h3><span className="source-chip">Hyderabad</span></div><div className="focus-stat"><strong>{stats.match70||0}</strong><span>71%+ matches</span></div><div className="focus-stat"><strong>{stats.published_today||0}</strong><span>New today</span></div><Link href="/companies" className="secondary full button-link">Manage companies →</Link></div>
        </aside>
      </div>
    </section>
  </Layout>;
}
