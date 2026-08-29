import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Overview, SystemStatus, api } from "../api";

export default function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.overview(), api.status()])
      .then(([o, s]) => {
        setOverview(o);
        setStatus(s);
      })
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="top">
        <div>
          <h1>Operations</h1>
          <p className="lede">Rollout health, assignment traffic, and gate activity at a glance.</p>
        </div>
        <Link className="btn primary" to="/flags/new">
          New flag
        </Link>
      </div>
      {err && <p className="err">{err}</p>}

      {status && (
        <div className="stat-grid">
          <div className="stat">
            <span className="stat-label">System</span>
            <strong className={status.status === "ok" ? "live-text" : "danger-text"}>{status.status}</strong>
          </div>
          <div className="stat">
            <span className="stat-label">Postgres</span>
            <strong>{status.database}</strong>
          </div>
          <div className="stat">
            <span className="stat-label">Ollama</span>
            <strong>
              {status.ollama}
              {status.demo_mock_llm ? " · mock on" : ""}
            </strong>
          </div>
          <div className="stat">
            <span className="stat-label">Active flags</span>
            <strong>
              {status.active_flags}/{status.flag_count}
            </strong>
          </div>
          <div className="stat">
            <span className="stat-label">Generations (window)</span>
            <strong>{status.generations_15m}</strong>
          </div>
          <div className="stat">
            <span className="stat-label">Last gate</span>
            <strong className="mono">{status.last_gate_action || "—"}</strong>
          </div>
        </div>
      )}

      <div className="grid two" style={{ marginTop: 18 }}>
        <section className="card">
          <div className="row">
            <strong>Flags</strong>
            <Link className="muted" to="/flags">
              View all
            </Link>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>flag</th>
                <th>status</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.flags || []).map((f) => (
                <tr key={f.id}>
                  <td>
                    <Link to={`/flags/${f.id}`}>
                      <span className="mono">{f.key}</span>
                    </Link>
                  </td>
                  <td>
                    <span className={`pill ${f.kill_switch ? "danger" : f.status === "active" ? "live" : "warn"}`}>
                      {f.kill_switch ? "killed" : f.status}
                    </span>
                  </td>
                  <td className="mono">{(f.percentage_bps / 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <div className="row">
            <strong>Recent audit</strong>
            <Link className="muted" to="/audit">
              Full log
            </Link>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>when</th>
                <th>actor</th>
                <th>action</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.recent_audit || []).map((a) => (
                <tr key={a.id}>
                  <td className="mono">{a.ts ? new Date(a.ts).toLocaleString() : "—"}</td>
                  <td>{a.actor}</td>
                  <td className="mono">{a.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {status?.last_gate_reason && (
            <p className="muted" style={{ marginTop: 12 }}>
              Gate note: {status.last_gate_reason}
            </p>
          )}
        </section>
      </div>

      <div className="spread" style={{ marginTop: 18 }}>
        <Link className="btn" to="/playground">
          Open playground
        </Link>
        <Link className="btn" to="/evaluate">
          Assignment debugger
        </Link>
        <Link className="btn" to="/quality">
          Quality monitor
        </Link>
      </div>
    </>
  );
}
