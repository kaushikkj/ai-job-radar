import { useEffect, useState } from "react";
import { API, Layout } from "../components/Layout";

export default function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`${API}/analytics`).then((r) => r.json()).then(setData);
  }, []);

  return (
    <Layout scanState={{}} onScan={() => {}}>
      <section className="page">
        <div className="page-heading">
          <div><div className="eyebrow">INSIGHTS</div><h1>Analytics</h1><p>Where your job opportunities are coming from.</p></div>
        </div>
        {!data ? <div className="empty">Loading analytics...</div> : (
          <div className="analytics-grid">
            <div className="panel"><h2>Top companies by job volume</h2>{data.top_companies.map((x) => <div className="bar-row" key={x.company}><span>{x.company}</span><b>{x.jobs}</b><small>{x.average_score}% avg</small></div>)}</div>
            <div className="panel"><h2>Locations</h2>{data.locations.map((x) => <div className="bar-row" key={x.location}><span>{x.location}</span><b>{x.jobs}</b></div>)}</div>
          </div>
        )}
      </section>
    </Layout>
  );
}
