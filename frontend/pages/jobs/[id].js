import {useEffect,useMemo,useState} from "react";
import Link from "next/link";
import {useRouter} from "next/router";
import {API,Layout,formatDate,ageLabel,dateLabel} from "../../components/Layout";

function clean(text){let t=(text||"");for(let i=0;i<3;i++){t=t.replace(/&lt;/gi,"<").replace(/&gt;/gi,">").replace(/&amp;/gi,"&").replace(/&#39;/gi,"'").replace(/&quot;/gi,'"')}t=t.replace(/<br\s*\/?>(?=\S)/gi," ").replace(/<[^>]+>/g," ");return t.replace(/\s+/g," ").trim()}
function sentenceChunks(text){
  const t=clean(text); if(!t) return [];
  const parts=t.split(/(?<=[.!?])\s+(?=[A-Z0-9])/).map(clean).filter(Boolean);
  const out=[]; for(let i=0;i<parts.length;i+=2) out.push(parts.slice(i,i+2).join(" ")); return out;
}
function structureDescription(text){
  const raw=(text||"").replace(/\r/g,"").trim();
  if(!raw) return {summary:[],sections:[]};
  const normalized=raw.replace(/[ \t]+/g," ");
  const headings=[
    "key responsibilities","responsibilities","what you'll do","what you will do","your responsibilities",
    "requirements","required qualifications","basic qualifications","minimum qualifications","preferred qualifications",
    "must-have skills","must have skills","preferred skills","qualifications","about the role","job summary","overview"
  ];
  const matches=[];
  const re=new RegExp(`(^|\\n|\\.\\s+)(${headings.map(x=>x.replace(/[.*+?^${}()|[\\]\\]/g,"\\$&")).join("|")})\\s*:?`,"ig");
  let m; while((m=re.exec(raw))) matches.push({index:m.index+(m[1]?m[1].length:0),title:m[2]});
  if(!matches.length){
    const chunks=sentenceChunks(normalized); return {summary:chunks.slice(0,2),sections:[{title:"Job description",items:chunks.slice(2,14)}]};
  }
  const summaryText=clean(raw.slice(0,matches[0].index));
  const sections=[];
  for(let i=0;i<matches.length;i++){
    const start=matches[i].index+matches[i].title.length;
    const end=i+1<matches.length?matches[i+1].index:raw.length;
    const block=raw.slice(start,end).replace(/^\s*[:\-–—]?\s*/,"").trim();
    const lines=block.split(/\n|•|\u2022|\s+-\s+/).map(clean).filter(Boolean);
    const items=lines.length>1?lines:sentenceChunks(block);
    if(items.length) sections.push({title:matches[i].title.replace(/\b\w/g,c=>c.toUpperCase()),items:items.slice(0,12)});
  }
  return {summary:sentenceChunks(summaryText).slice(0,3),sections};
}

export default function JobDetail(){
 const router=useRouter();
 const [job,setJob]=useState(null),[analysis,setAnalysis]=useState(null),[loading,setLoading]=useState(true),[aiLoading,setAiLoading]=useState(false),[optimizing,setOptimizing]=useState(false),[suggestions,setSuggestions]=useState([]),[optimized,setOptimized]=useState("");
 async function load(){if(!router.query.id)return;setLoading(true);try{let r=await fetch(`${API}/jobs/${router.query.id}?_t=${Date.now()}`,{cache:"no-store"});if(r.ok){let d=await r.json();setJob(d);const refresh=await fetch(`${API}/jobs/${router.query.id}/refresh-source`,{method:"POST",cache:"no-store"});if(refresh.ok)d=await refresh.json();setJob(d);const a=await fetch(`${API}/jobs/${router.query.id}/resume-analysis?_t=${Date.now()}`,{cache:"no-store"});if(a.ok)setAnalysis(await a.json())}}finally{setLoading(false)}}
 useEffect(()=>{load()},[router.query.id]);
 async function patch(params){await fetch(`${API}/jobs/${job.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(params),cache:"no-store"});await load()}
 async function optimize(){setOptimizing(true);try{const r=await fetch(`${API}/jobs/${job.id}/optimize-resume`,{method:"POST",cache:"no-store"});const d=await r.json();setSuggestions(d.suggestions||[]);setOptimized(d.optimized_content||"")}finally{setOptimizing(false)}}
 const structured=useMemo(()=>structureDescription(job?.description),[job?.description]);
 let aiView=null;
 if(job?.ai_analysis){
  try{
   const a=JSON.parse(job.ai_analysis);
   if(a?.status==="unavailable"||a?.status==="error"||String(a?.message||"").toLowerCase().includes("api key")){
    aiView=<div className="ai-status-message">{a.message||"AI analysis is unavailable. Your Job Match score is still available."}</div>;
   }else{
    aiView=<div className="ai-result-grid">
     {a.verdict&&<div><span>Verdict</span><b>{a.verdict}</b></div>}
     {a.fit_score!=null&&<div><span>AI fit</span><b>{a.fit_score}%</b></div>}
     {a.why_apply&&<div className="ai-result-wide"><span>Why this role</span><p>{a.why_apply}</p></div>}
     {Array.isArray(a.strengths)&&a.strengths.length>0&&<div><span>Strengths</span><ul>{a.strengths.map((x,i)=><li key={i}>{x}</li>)}</ul></div>}
     {Array.isArray(a.gaps)&&a.gaps.length>0&&<div><span>Gaps</span><ul>{a.gaps.map((x,i)=><li key={i}>{x}</li>)}</ul></div>}
    </div>;
   }
  }catch{aiView=<div className="ai-status-message">AI analysis is unavailable. Check OPENAI_API_KEY in .env and recreate the backend container.</div>}
 }
 return <Layout scanState={{}} onScan={()=>{}}>
  <section className="page">
   <Link href="/jobs" className="back-link">← Back to Jobs</Link>
   {loading?<div className="empty">Loading job…</div>:!job?<div className="empty">Job not found</div>:
   <>
    <div className="detail-hero-v2"><div className="company-logo large">{(job.company_name||"?").slice(0,2).toUpperCase()}</div><div><div className="eyebrow">{job.company_name}</div><h1>{job.title}</h1><p>📍 {job.location||"Location not specified"}{job.remote?" · Remote":""} · {job.source||"Career Site"}</p><div className="detail-date-strip"><span>{dateLabel(job)}</span><span>{ageLabel(job)}</span><span>Added {formatDate(job.first_seen_at)}</span></div></div><div className="detail-actions"><a href={job.url} target="_blank" rel="noreferrer" className="primary button-link">Apply Now ↗</a><button className="secondary" onClick={()=>patch({saved:!job.saved})}>{job.saved?"★ Shortlisted":"☆ Shortlist"}</button></div></div>
    <div className="detail-grid-v2">
      <article className="detail-content">
       <div className="panel match-panel"><div className="panel-title-row"><h2>Job Match</h2><span className="big-match">{Math.round(job.score)}%</span></div><p className="match-summary">{job.match_reason||"Profile fit calculated from role, technical, experience, location and company signals."}</p><div className="metrics"><span>Role <b>{Math.round(job.role_score)}/30</b></span><span>Tech <b>{Math.round(job.technical_score)}/25</b></span><span>Experience <b>{Math.round(job.experience_score)}/15</b></span><span>Location <b>{Math.round(job.location_score)}/15</b></span><span>Company <b>{Math.round(job.company_score)}/10</b></span></div></div>
       <div className="panel"><div className="panel-title-row"><h2>Job Description</h2><span className="source-chip">Structured view</span></div>{structured.summary.length>0&&<div className="jd-summary">{structured.summary.map((x,i)=><p key={i}>{x}</p>)}</div>}{structured.sections.map((section,i)=><section className="jd-section" key={`${section.title}-${i}`}><h3>{section.title}</h3><ul>{section.items.map((x,j)=><li key={j}>{x}</li>)}</ul></section>)}</div>
       <div className="panel ai-analysis-panel"><div className="panel-title-row"><div><span className="section-kicker">OPTIONAL</span><h2>AI Job Analysis</h2></div>{!job.ai_analysis&&<button className="secondary small" onClick={async()=>{setAiLoading(true);try{const r=await fetch(`${API}/jobs/${job.id}/analyze`,{method:"POST",cache:"no-store"});const d=await r.json();if(d.analysis)setJob({...job,ai_analysis:d.analysis});else setJob({...job,ai_analysis:JSON.stringify(d)})}finally{setAiLoading(false)}}} disabled={aiLoading}>{aiLoading?"Analyzing…":"✨ Analyze with AI"}</button>}</div>{job.ai_analysis?aiView:<p className="muted">AI analysis is on-demand so career-site scanning stays fast. Your deterministic Job Match score is always available.</p>}</div>
       <div className="panel"><div className="panel-title-row"><h2>📄 Resume Coverage</h2>{analysis?.coverage!=null&&<span className="coverage-pill">{Math.round(analysis.coverage)}% coverage</span>}</div>{analysis?.resume?<><p><b>{analysis.resume.name}</b> is the selected resume for this job.</p><div className="coverage-grid"><div><b>Exact evidence</b><div className="tag-list">{(analysis.exact_skills||[]).map(x=><span className="tag" key={x}>✓ {x}</span>)}</div></div><div><b>Not demonstrated</b><div className="tag-list">{(analysis.gaps||[]).map(x=><span className="tag gap" key={x}>⚠ {x}</span>)}</div></div></div><p className="muted">Resume coverage does not reduce your Job Match. It tells you whether the selected resume proves the fit.</p><button className="primary" onClick={optimize} disabled={optimizing}>{optimizing?"Analyzing…":"✨ Tailor Resume for This Job"}</button>{suggestions.length>0&&<div className="ai-suggestions"><h3>AI suggestions</h3>{suggestions.map((x,i)=><p key={i}>• {x}</p>)}{optimized&&<><h3>Generated draft</h3><textarea className="resume-editor" value={optimized} readOnly/></>}</div>}</>:<><p>Upload a resume to calculate resume coverage and tailor it for this job.</p><Link href="/resumes" className="primary button-link">Upload / Manage Resumes</Link></>}</div>
      </article>
      <aside className="detail-side"><div className="panel"><div className="panel-title-row"><h3>Dates & Freshness</h3><span className="source-chip">Source verified</span></div><div className="date-inline"><span><b>Published</b> {job.posted_at?new Date(job.posted_at).toLocaleDateString([], {year:"numeric", month:"short", day:"numeric"}):"Unavailable"}</span><span>•</span><span>{ageLabel(job)}</span><span>•</span><span>Added {formatDate(job.first_seen_at)}</span><span>•</span><span>Seen {formatDate(job.last_seen_at)}</span></div><div className="score-line"><span>Freshness</span><b>{Math.round(job.freshness_score||0)}/100</b></div><div className="score-line"><span>Radar priority</span><b>{Math.round(job.priority_score||job.score)}/100</b></div></div><div className="panel"><h3>Quick Actions</h3><a href={job.url} target="_blank" rel="noreferrer" className="primary full button-link">↗ Apply Now</a><button className="secondary full" onClick={()=>patch({saved:!job.saved})}>{job.saved?"★ Saved":"☆ Save Job"}</button><button className="secondary full" onClick={()=>patch({status:"interested"})}>♡ Interested</button><button className="secondary full" onClick={()=>patch({status:"archived"})}>× Not Interested</button></div><div className="panel"><h3>Application</h3><p>Status: <b>{job.status}</b></p>{job.status!=="applied"?<button className="primary full" onClick={()=>patch({status:"applied"})}>✓ Mark as Applied</button>:<div className="success">✓ Application recorded</div>}</div></aside>
    </div>
   </>}
  </section>
 </Layout>
}
