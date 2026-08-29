import { FormEvent, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { clearToken, getToken, setToken } from "./api";
import AuditPage from "./pages/Audit";
import CreateFlag from "./pages/CreateFlag";
import Dashboard from "./pages/Dashboard";
import EvaluatePage from "./pages/Evaluate";
import FlagDetail from "./pages/FlagDetail";
import Flags from "./pages/Flags";
import Playground from "./pages/Playground";
import QualityPage from "./pages/Quality";

function Login() {
  const nav = useNavigate();
  const [token, setLocal] = useState("dev-admin-token");
  const [err, setErr] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) {
      setErr("Token required");
      return;
    }
    setToken(token.trim());
    nav("/");
  }

  return (
    <div className="login">
      <form className="card stack login-card" onSubmit={submit}>
        <div>
          <p className="eyebrow">AI FEATURE FLAGS</p>
          <strong className="brand-mark">WARDEN</strong>
          <p className="lede">Gradual rollout control plane with quality gates and kill switches.</p>
        </div>
        {err && <p className="err">{err}</p>}
        <div>
          <label htmlFor="token">Admin token</label>
          <input id="token" value={token} onChange={(e) => setLocal(e.target.value)} autoFocus />
        </div>
        <button className="btn primary" type="submit">
          Enter console
        </button>
      </form>
    </div>
  );
}

function Shell() {
  if (!getToken()) return <Navigate to="/login" replace />;
  return (
    <div className="shell">
      <aside className="nav">
        <div className="brand">
          <strong>Warden</strong>
          <span>rollout + quality</span>
        </div>
        <nav className="nav-links">
          <NavLink end to="/">
            Operations
          </NavLink>
          <NavLink to="/flags">Flags</NavLink>
          <NavLink to="/quality">Quality</NavLink>
          <NavLink to="/playground">Playground</NavLink>
          <NavLink to="/evaluate">Debugger</NavLink>
          <NavLink to="/audit">Audit</NavLink>
        </nav>
        <div className="nav-foot">
          <a className="muted" href="/docs/TUTORIAL.md" onClick={(e) => e.preventDefault()}>
            See docs/TUTORIAL.md
          </a>
          <button
            className="btn"
            onClick={() => {
              clearToken();
              window.location.href = "/login";
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/flags" element={<Flags />} />
          <Route path="/flags/new" element={<CreateFlag />} />
          <Route path="/flags/:id" element={<FlagDetail />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/playground" element={<Playground />} />
          <Route path="/evaluate" element={<EvaluatePage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<Shell />} />
    </Routes>
  );
}
