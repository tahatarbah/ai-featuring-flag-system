import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Flag, GateDecision, Quality, api } from "../api";
import MetricBars from "../components/MetricBars";

export default function QualityPage() {
  const [rows, setRows] = useState<{ flag: Flag; quality: Quality }[]>([]);
  const [gates, setGates] = useState<GateDecision[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const flags = await api.flags();
        const packed = await Promise.all(
          flags.map(async (flag) => ({ flag, quality: await api.quality(flag.id) })),
        );
        setRows(packed);
        setGates(await api.gateDecisions());
      } catch (e) {
        setErr((e as Error).message);
      }
    })();
  }, []);

  return (
    <>
      <div className="top">
        <div>
          <h1>Quality</h1>
          <p className="lede">Treatment vs control in the sliding window. Gates pause or roll back when SLOs break.</p>
        </div>
      </div>
      {err && <p className="err">{err}</p>}
      <div className="grid">
        {rows.map(({ flag, quality }) => (
          <section className="card" key={flag.id}>
            <div className="row">
              <Link to={`/flags/${flag.id}`}>
                <strong>{flag.name}</strong>
              </Link>
              <span className="mono muted">{flag.key}</span>
            </div>
            <MetricBars quality={quality} />
            {quality.last_decision && (
              <p className="muted">
                Last gate <span className="mono">{quality.last_decision.action}</span>: {quality.last_decision.reason}
              </p>
            )}
          </section>
        ))}
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <strong>Gate decisions</strong>
        <table className="table">
          <thead>
            <tr>
              <th>when</th>
              <th>flag</th>
              <th>action</th>
              <th>reason</th>
            </tr>
          </thead>
          <tbody>
            {gates.map((g) => (
              <tr key={g.id}>
                <td className="mono">{g.ts ? new Date(g.ts).toLocaleString() : "—"}</td>
                <td className="mono">{g.flag_key}</td>
                <td>
                  <span className={`pill ${g.action === "rollback" || g.action === "pause" ? "danger" : "live"}`}>
                    {g.action}
                  </span>
                </td>
                <td className="muted">{g.reason}</td>
              </tr>
            ))}
            {gates.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No gate actions yet. Simulate traffic in the playground, then wait for the 15s worker.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}
