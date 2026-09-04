import { useEffect, useMemo, useState } from "react";
import { API, Layout } from "../components/Layout";

function parseResume(text){
  const lines=(text||"").split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  const sections={summary:[],skills:[],experience:[],education:[],projects:[],other:[]};
  let current="summary";
  const aliases={
    summary:/^(summary|professional summary|profile|objective)$/i,
    skills:/^(skills|technical skills|core skills|technologies|technical expertise)$/i,
    experience:/^(experience|work experience|professional experience|employment|career history)$/i,
    education:/^(education|academic background|qualifications)$/i,
    projects:/^(projects|selected projects|personal projects)$/i
  };
  for(const line of lines){
    const hit=Object.entries(aliases).find(([,r])=>r.test(line.replace(/[:|-]+$/,"")));
    if(hit){current=hit[0];continue;}
    sections[current].push(line);
  }
  if(!sections.summary.length) sections.summary=lines.slice(0,3);
  return sections;
}

function Count({label,value,sub}){return <div className="resume-stat"><span>{label}</span><b>{value}</b>{sub&&<small>{sub}</small>}</div>}

export default function Resumes(){
  const [items,setItems]=useState([]),[selected,setSelected]=useState(null),[name,setName]=useState(""),[content,setContent]=useState(""),[file,setFile]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(""),[tab,setTab]=useState("overview"),[versions,setVersions]=useState([]),[jobs,setJobs]=useState([]),[jobId,setJobId]=useState(""),[analysis,setAnalysis]=useState(null),[optimized,setOptimized]=useState(""),[suggestions,setSuggestions]=useState([]);
  const overview=useMemo(()=>parseResume(content),[content]);
  const wordCount=content.split(/\s+/).filter(Boolean).length;

  async function load(){
    try{
      const r=await fetch(`${API}/resumes?_t=${Date.now()}`,{cache:"no-store"});
      if(!r.ok) throw new Error("Could not load resumes from the backend.");
      const d=await r.json();
      setItems(Array.isArray(d)?d:[]);
      if(!selected && d[0]) await pick(d[0]);
    }catch(e){setMessage(e?.message === "Failed to fetch" ? "Backend unavailable. Please try again in a moment." : (e.message||"Could not load resumes."))}
  }
  async function pick(r){
    setSelected(r.id);setName(r.name);setContent(r.content||"");setTab("overview");setMessage("");setOptimized("");setSuggestions([]);setAnalysis(null);
    try{const v=await fetch(`${API}/resumes/${r.id}/versions?_t=${Date.now()}`,{cache:"no-store"});if(v.ok)setVersions(await v.json());else setVersions([])}catch{setVersions([])}
  }
  useEffect(()=>{
    load();
    fetch(`${API}/jobs?location=Hyderabad&min_score=0&max_score=100&sort=recommended&limit=100`,{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setJobs).catch(()=>{});
  },[]);

  function chooseTopFile(e){const f=e.target.files?.[0]||null;if(f){setFile(f);setMessage("")}}
  async function upload(){
    if(!file)return;setBusy(true);setMessage("");
    const fd=new FormData();fd.append("file",file);fd.append("name",name||file.name.replace(/\.[^.]+$/, ""));
    try{
      const r=await fetch(`${API}/resumes/upload`,{method:"POST",body:fd});
      let d={};try{d=await r.json()}catch{}
      if(!r.ok) throw new Error(d.detail||"Resume upload failed. Please check that the backend is running.");
      setFile(null);await load();await pick(d);setMessage("Resume uploaded and parsed successfully.");
    }catch(e){setMessage(e.message||"Resume upload failed.")}
    finally{setBusy(false)}
  }
  async function save(){
    if(!selected)return;setBusy(true);setMessage("");
    try{const r=await fetch(`${API}/resumes/${selected}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,content}),cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Save failed");setName(d.name);setContent(d.content||content);setItems(prev=>prev.map(x=>x.id===d.id?d:x));const v=await fetch(`${API}/resumes/${selected}/versions`,{cache:"no-store"});if(v.ok)setVersions(await v.json());setMessage("Saved. A new version snapshot was created.")}catch(e){setMessage(e.message||"Save failed")}finally{setBusy(false)}
  }
  async function makeDefault(){if(!selected)return;const r=await fetch(`${API}/resumes/${selected}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({is_default:true})});if(r.ok){await load();setMessage("Default resume updated.")}}
  async function remove(){if(!selected||!confirm("Delete this resume and its versions?"))return;const r=await fetch(`${API}/resumes/${selected}`,{method:"DELETE"});if(!r.ok){setMessage("Could not delete the resume.");return}setSelected(null);setContent("");await load();setMessage("Resume deleted.")}
  async function restore(v){const r=await fetch(`${API}/resumes/${selected}/versions/${v.id}/restore`,{method:"POST"});if(r.ok){const d=await r.json();await pick(d);setMessage(`Restored version ${v.id}.`)}}
  async function analyze(){if(!selected||!jobId)return;setBusy(true);setMessage("");try{const r=await fetch(`${API}/jobs/${jobId}/resume-analysis?resume_id=${selected}`,{cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Coverage analysis failed");setAnalysis(d);setTab("tailor")}catch(e){setMessage(e?.message === "Failed to fetch" ? "Backend unavailable. Please try again in a moment." : (e.message||"Coverage analysis failed"))}finally{setBusy(false)}}
  async function optimize(){if(!jobId||!selected)return;setBusy(true);setMessage("");try{const r=await fetch(`${API}/jobs/${jobId}/optimize-resume?resume_id=${selected}`,{method:"POST",cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Optimization failed");setAnalysis(d);setSuggestions(d.suggestions||[]);setOptimized(d.optimized_content||"");setTab("tailor")}catch(e){setMessage(e?.message === "Failed to fetch" ? "Backend unavailable. Please try again in a moment." : (e.message||"Optimization failed"))}finally{setBusy(false)}}

  return <Layout scanState={{}} onScan={()=>{}}>
    <section className="page resume-page">
      <div className="page-heading">
        <div><div className="eyebrow">RESUME INTELLIGENCE</div><h1>Resume Management</h1><p>Keep one master resume, inspect the parsed evidence, and tailor a copy for each opportunity.</p></div>
        <label className="primary upload-top">＋ Upload New Resume<input type="file" accept=".pdf,.docx,.txt" onChange={chooseTopFile} hidden/></label>
      </div>
      {file&&<div className="upload-pending"><span><b>{file.name}</b> ready to upload</span><button className="primary" disabled={busy} onClick={upload}>{busy?"Uploading…":"Upload & Parse"}</button><button className="secondary" onClick={()=>setFile(null)}>Cancel</button></div>}
      {message&&<div className={`notice ${/failed|could not|error/i.test(message)?"notice-error":""}`}>{message}</div>}

      <div className="resume-workspace">
        <aside className="panel resume-list">
          <div className="section-title"><div><h2>My Resumes</h2><p>{items.length} master resume{items.length===1?"":"s"}</p></div></div>
          <div className="resume-drop"><input value={name} onChange={e=>setName(e.target.value)} placeholder="Resume name"/><input type="file" accept=".pdf,.docx,.txt" onChange={e=>setFile(e.target.files?.[0]||null)}/><button className="primary full" disabled={!file||busy} onClick={upload}>{busy?"Processing…":"Upload & Parse Resume"}</button><small>PDF, DOCX, TXT · max 10MB</small></div>
          {items.map(r=><button key={r.id} className={`resume-item ${selected===r.id?"active":""}`} onClick={()=>pick(r)}><span className="file-icon">{r.filename?.toLowerCase().endsWith("pdf")?"PDF":"DOC"}</span><div><b>{r.name}</b><small>{r.is_default?"DEFAULT · ":""}{new Date(r.updated_at).toLocaleDateString()}</small></div></button>)}
        </aside>

        <main className="panel resume-center">
          {selected?<>
            <div className="resume-header"><div><div className="resume-title-row"><h2>{name}</h2>{items.find(x=>x.id===selected)?.is_default&&<span className="default-pill">DEFAULT</span>}</div><p>{items.find(x=>x.id===selected)?.filename||"Resume"} · {wordCount} words</p></div><div className="resume-actions"><button className="secondary" onClick={makeDefault}>Set Default</button><a className="secondary button-link" href={`${API}/resumes/${selected}/export?format=docx`} target="_blank">DOCX</a><a className="secondary button-link" href={`${API}/resumes/${selected}/export?format=pdf`} target="_blank">PDF</a><button className="danger-button" onClick={remove}>Delete</button></div></div>
            <div className="resume-tabs">{[["overview","Overview"],["editor","Resume Editor"],["tailor","Tailor Resume"],["history","Resume History"]].map(([x,l])=><button key={x} className={tab===x?"active":""} onClick={()=>setTab(x)}>{l}</button>)}</div>

            {tab==="overview"&&<div className="resume-overview-v2">
              <div className="resume-overview-intro"><div><span className="section-kicker">MASTER RESUME</span><h3>Parsed resume profile</h3><p>Review the information Radar extracted before using it for job compatibility or optimization.</p></div><button className="secondary" onClick={()=>setTab("editor")}>Edit master resume</button></div>
              <div className="resume-stats-grid"><Count label="Words" value={wordCount} sub="Parsed text"/><Count label="Skills" value={overview.skills.length} sub="Detected entries"/><Count label="Experience" value={overview.experience.length} sub="Parsed lines"/><Count label="Projects" value={overview.projects.length} sub="Detected entries"/></div>
              <section className="resume-feature-card"><div className="resume-feature-head"><div><span className="section-kicker">PROFILE</span><h3>Professional Summary</h3></div><span>{overview.summary.length} lines</span></div>{overview.summary.length?<div className="summary-copy">{overview.summary.slice(0,5).map((x,i)=><p key={i}>{x}</p>)}</div>:<p className="muted">No summary section detected.</p>}</section>
              <div className="resume-content-grid">
                <section className="resume-feature-card"><div className="resume-feature-head"><div><span className="section-kicker">EXPERTISE</span><h3>Technical Skills</h3></div><span>{overview.skills.length}</span></div><div className="skill-cloud">{overview.skills.length?overview.skills.slice(0,24).map((x,i)=><span key={i}>{x}</span>):<p className="muted">No skills section detected.</p>}</div></section>
                <section className="resume-feature-card"><div className="resume-feature-head"><div><span className="section-kicker">EDUCATION</span><h3>Education</h3></div><span>{overview.education.length}</span></div>{overview.education.length?<ul className="clean-list">{overview.education.slice(0,8).map((x,i)=><li key={i}>{x}</li>)}</ul>:<p className="muted">No education section detected.</p>}</section>
              </div>
              <section className="resume-feature-card"><div className="resume-feature-head"><div><span className="section-kicker">CAREER</span><h3>Experience</h3></div><span>{overview.experience.length} entries</span></div>{overview.experience.length?<ul className="resume-timeline">{overview.experience.slice(0,14).map((x,i)=><li key={i}><span className="timeline-dot"/><div>{x}</div></li>)}</ul>:<p className="muted">No experience section detected.</p>}</section>
              <section className="resume-feature-card"><div className="resume-feature-head"><div><span className="section-kicker">PROJECTS</span><h3>Selected Projects</h3></div><span>{overview.projects.length}</span></div>{overview.projects.length?<ul className="clean-list">{overview.projects.slice(0,12).map((x,i)=><li key={i}>{x}</li>)}</ul>:<p className="muted">No projects section detected.</p>}</section>
            </div>}

            {tab==="editor"&&<div className="editor-view"><div className="editor-tip"><b>Master copy</b><span>Edit freely. Every save creates a version snapshot.</span></div><textarea className="resume-editor" value={content} onChange={e=>setContent(e.target.value)}/><div className="editor-foot"><span>{content.length} characters · {wordCount} words</span><button className="primary" disabled={busy} onClick={save}>Save New Version</button></div></div>}

            {tab==="tailor"&&<div className="tailor-view"><div className="tailor-select-v2"><div><span className="section-kicker">JOB TARGET</span><h3>Tailor this resume to a job</h3><p>Compatibility combines the existing Job Match with evidence coverage from this resume.</p></div><div className="tailor-controls"><select value={jobId} onChange={e=>{setJobId(e.target.value);setAnalysis(null);setOptimized("")}}><option value="">Select a Hyderabad job</option>{jobs.map(j=><option key={j.id} value={j.id}>{Math.round(j.score)}% · {j.company_name} — {j.title}</option>)}</select><button className="secondary" disabled={!jobId||busy} onClick={analyze}>Analyze Coverage</button><button className="primary" disabled={!jobId||busy} onClick={optimize}>{busy?"Working…":"✨ Optimize Resume"}</button></div></div>{analysis&&<div className="tailor-results"><div className="compatibility-hero-v2"><div className="compatibility-main"><span>Application compatibility</span><strong>{Math.round(analysis.compatibility||0)}%</strong><small>Resume ↔ target job</small></div><div><span>Job Match</span><b>{Math.round(analysis.job_match||0)}%</b><small>Capability fit</small></div><div><span>Resume Coverage</span><b>{Math.round(analysis.coverage||0)}%</b><small>Evidence found</small></div><div><span>Gaps</span><b>{analysis.gaps?.length||0}</b><small>Review before applying</small></div></div><div className="coverage-columns"><div className="overview-card"><h3>✓ Demonstrated</h3><div className="tag-list">{(analysis.exact_skills||[]).map(x=><span className="tag" key={x}>{x}</span>)}</div></div><div className="overview-card"><h3>⚠ Not demonstrated</h3><div className="tag-list">{(analysis.gaps||[]).map(x=><span className="tag gap" key={x}>{x}</span>)}</div></div></div>{suggestions.length>0&&<div className="overview-card"><h3>Smart suggestions</h3>{suggestions.map((x,i)=><p key={i}>• {x}</p>)}</div>}{optimized&&<div className="optimized-draft"><div className="panel-title-row"><h3>Optimized draft — review before applying</h3><button className="secondary" onClick={()=>{setContent(optimized);setTab("editor")}}>Use as draft</button></div><textarea className="resume-editor draft" value={optimized} onChange={e=>setOptimized(e.target.value)}/></div>}</div>}</div>}

            {tab==="history"&&<div className="history-list">{versions.length?versions.map(v=><div className="history-row" key={v.id}><div><b>{v.label}</b><span>{v.source} · {new Date(v.created_at).toLocaleString()}</span></div><button className="secondary" onClick={()=>restore(v)}>Restore</button></div>):<div className="empty">No versions yet.</div>}</div>}
          </>:<div className="empty resume-empty"><div className="upload-big">↑</div><h2>Upload your first resume</h2><p>Start with your master resume. Radar will parse it into a structured, editable workspace.</p><button className="primary" onClick={()=>document.querySelector('.resume-drop input[type=file]')?.click()}>Choose Resume</button></div>}
        </main>

        <aside className="resume-right"><div className="panel optimizer-panel"><div className="optimizer-icon">✦</div><span className="section-kicker">RESUME INTELLIGENCE</span><h2>AI Resume Optimizer</h2><p>Build a job-specific draft without changing your master resume.</p><div className="optimizer-steps"><div><b>01</b><span>Requirements</span><small>Extract role, skills and seniority.</small></div><div><b>02</b><span>Compatibility</span><small>Blend Job Match with resume evidence.</small></div><div><b>03</b><span>Coverage & gaps</span><small>Show demonstrated and missing skills.</small></div><div><b>04</b><span>Optimize & review</span><small>Generate a truthful draft for review.</small></div></div><button className="primary full" onClick={()=>setTab("tailor")} disabled={!selected}>Tailor Resume for a Job</button></div><div className="panel resume-principles"><h3>Resume principles</h3><div><b>Master stays safe</b><span>Tailoring never overwrites the original.</span></div><div><b>Evidence first</b><span>Only demonstrated skills count as coverage.</span></div><div><b>Truthful optimization</b><span>Never invent skills, metrics or experience.</span></div></div></aside>
      </div>
    </section>
  </Layout>
}
