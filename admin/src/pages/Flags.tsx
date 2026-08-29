import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Flag, api } from "../api";

function statusClass(status: string, killed: boolean) {
  if (killed || status === "killed") return "danger";
  if (status === "active") return "live";
  if (status === "paused") return "warn";
  return "";
}

export default function Flags() {
  const [flags, setFlags] = useState<Flag[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .flags()
      .then(setFlags)
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="top">
        <div>
          <h1>Flags</h1>
          <p className="lede">AI variants, sticky rollouts, kill switches.</p>
        </div>
        <Link className="btn primary" to="/flags/new">
          New flag
        </Link>
      </div>
      {err && <p className="err">{err}</p>}
      <div className="cards">
        {flags.map((flag) => {
          const pct = ((flag.rollout?.percentage_bps ?? 0) / 100).toFixed(0);
          return (
            <Link className="card flag-card" key={flag.id} to={`/flags/${flag.id}`}>
              <div className="row">
                <strong>{flag.name}</strong>
                <span className={`pill ${statusClass(flag.status, flag.kill_switch)}`}>
                  {flag.kill_switch ? "killed" : flag.status}
                </span>
              </div>
              <p className="mono muted">{flag.key}</p>
              <p className="muted">{flag.description || "No description"}</p>
              <div className="row">
                <span className="mono">{pct}% · stage {flag.rollout?.stage ?? 0}</span>
                <span className="muted">{flag.flag_type}</span>
              </div>
            </Link>
          );
        })}
      </div>
    </>
  );
}
