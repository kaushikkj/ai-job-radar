import { useEffect, useState } from "react";
import { API, Layout } from "../components/Layout";

export default function Profile() {
  const [profile, setProfile] = useState(null);
  useEffect(() => { fetch(`${API}/profile`).then((r) => r.json()).then(setProfile); }, []);
  return (
    <Layout scanState={{}} onScan={() => {}}>
      <section className="page">
        <div className="page-heading"><div><div className="eyebrow">MATCHING PROFILE</div><h1>Your Profile</h1><p>The profile used by the scoring engine.</p></div></div>
        {!profile ? <div className="empty">Loading profile...</div> : <div className="profile-grid">
          <div className="panel"><h2>Target roles</h2><div className="tag-list">{profile.target_roles.map((x) => <span className="tag" key={x}>{x}</span>)}</div></div>
          <div className="panel"><h2>Skills</h2><div className="tag-list">{profile.skills.map((x) => <span className="tag" key={x}>{x}</span>)}</div></div>
          <div className="panel"><h2>Location priorities</h2>{profile.target_locations.map((x, i) => <p key={x}><b>{i + 1}.</b> {x}</p>)}</div>
          <div className="panel"><h2>Experience</h2><div className="big-number">{profile.experience_years} years</div></div>
        </div>}
      </section>
    </Layout>
  );
}
