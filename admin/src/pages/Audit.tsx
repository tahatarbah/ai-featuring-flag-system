import { useEffect, useState } from "react";
import { Audit, api } from "../api";

export default function AuditPage() {
  const [rows, setRows] = useState<Audit[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api
      .audit()
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="top">
        <div>
          <h1>Audit</h1>
          <p className="lede">Who published, killed, advanced, or got rolled back by a gate.</p>
        </div>
      </div>
      {err && <p className="err">{err}</p>}
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>when</th>
              <th>actor</th>
              <th>action</th>
              <th>after</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="mono">{new Date(r.ts).toLocaleString()}</td>
                <td>{r.actor}</td>
                <td className="mono">{r.action}</td>
                <td className="muted">{r.after ? JSON.stringify(r.after) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
