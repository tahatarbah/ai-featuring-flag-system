import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Flag, Quality, api } from "../api";
import MetricBars from "../components/MetricBars";

const STAGES = [0, 1, 5, 25, 50, 100];

export default function FlagDetail() {
  const { id = "" } = useParams();
  const [flag, setFlag] = useState<Flag | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ruleAttr, setRuleAttr] = useState("user");
  const [ruleOp, setRuleOp] = useState("eq");
  const [ruleValue, setRuleValue] = useState("");
  const [ruleVariant, setRuleVariant] = useState("");

  async function reload() {
    const [f, q] = await Promise.all([api.flag(id), api.quality(id)]);
    setFlag(f);
    setQuality(q);
  }

  useEffect(() => {
    reload().catch((e) => setErr(e.message));
  }, [id]);

  const pct = useMemo(() => Math.round((flag?.rollout?.percentage_bps ?? 0) / 100), [flag]);

  async function act(fn: () => Promise<Flag>) {
    setBusy(true);
    setErr("");
    try {
      setFlag(await fn());
      setQuality(await api.quality(id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!flag) return <p className="muted">{err || "Loading…"}</p>;

  async function saveRules(e: FormEvent) {
    e.preventDefault();
    const existing = flag.rules.map((r) => ({
      priority: r.priority,
      attribute: r.attribute,
      op: r.op,
      value: r.value,
      variant_key: r.variant_key,
    }));
    existing.push({
      priority: existing.length,
      attribute: ruleAttr,
      op: ruleOp,
      value: ruleValue,
      variant_key: ruleVariant || flag.variants.find((v) => !v.is_control)?.key || "treatment",
    });
    await act(() => api.setRules(flag.id, existing));
    setRuleValue("");
  }

  return (
    <>
      <div className="top">
        <div>
          <h1>{flag.name}</h1>
          <p className="lede mono">{flag.key}</p>
        </div>
        <div className="spread">
          <button className="btn primary" disabled={busy} onClick={() => act(() => api.publish(flag.id))}>
            Publish
          </button>
          <button className="btn" disabled={busy} onClick={() => act(() => api.pause(flag.id))}>
            Pause
          </button>
          <button className="btn" disabled={busy} onClick={() => act(() => api.advance(flag.id))}>
            Advance stage
          </button>
          <button className="btn danger" disabled={busy} onClick={() => act(() => api.kill(flag.id))}>
            Kill switch
          </button>
          <button className="btn" disabled={busy} onClick={() => act(() => api.restore(flag.id))}>
            Restore
          </button>
        </div>
      </div>
      {err && <p className="err">{err}</p>}

      <div className="grid" style={{ gridTemplateColumns: "1.2fr 0.8fr" }}>
        <section className="card stack">
          <div className="row">
            <strong>Rollout</strong>
            <span className={`pill ${flag.kill_switch ? "danger" : flag.status === "active" ? "live" : "warn"}`}>
              {flag.kill_switch ? "killed" : flag.status} · {pct}%
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={pct}
            onChange={(e) => {
              const next = Number(e.target.value);
              act(() => api.patchFlag(flag.id, { percentage_bps: next * 100 }));
            }}
          />
          <div className="spread">
            {STAGES.map((s) => (
              <button key={s} className="btn" onClick={() => act(() => api.patchFlag(flag.id, { percentage_bps: s * 100 }))}>
                {s}%
              </button>
            ))}
          </div>
          <label>
            <input
              type="checkbox"
              checked={flag.rollout?.auto_advance ?? false}
              onChange={(e) => act(() => api.patchFlag(flag.id, { auto_advance: e.target.checked }))}
              style={{ width: "auto", marginRight: 8 }}
            />
            Auto-advance when SLOs pass
          </label>
        </section>

        <section className="card">
          <strong>Quality window</strong>
          {quality ? <MetricBars quality={quality} /> : <p className="muted">No samples yet.</p>}
          {quality?.last_decision && (
            <p className="muted">
              Last gate: <span className="mono">{quality.last_decision.action}</span> — {quality.last_decision.reason}
            </p>
          )}
        </section>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 16 }}>
        <section className="card">
          <strong>Variants</strong>
          {flag.variants.map((v) => (
            <div key={v.id} style={{ marginTop: 12 }}>
              <div className="row">
                <span className="mono">{v.key}</span>
                {v.is_control && <span className="pill">control</span>}
              </div>
              <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>
                {JSON.stringify(v.payload, null, 2)}
              </pre>
            </div>
          ))}
        </section>

        <section className="card stack">
          <strong>Targeting</strong>
          <table className="table">
            <thead>
              <tr>
                <th>attr</th>
                <th>op</th>
                <th>value</th>
                <th>variant</th>
              </tr>
            </thead>
            <tbody>
              {flag.rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.attribute}</td>
                  <td>{r.op}</td>
                  <td className="mono">{r.value}</td>
                  <td>{r.variant_key}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form className="stack" onSubmit={saveRules}>
            <div className="spread">
              <input placeholder="attribute" value={ruleAttr} onChange={(e) => setRuleAttr(e.target.value)} />
              <select value={ruleOp} onChange={(e) => setRuleOp(e.target.value)}>
                <option value="eq">eq</option>
                <option value="in">in</option>
                <option value="contains">contains</option>
              </select>
              <input placeholder="value" value={ruleValue} onChange={(e) => setRuleValue(e.target.value)} />
              <select value={ruleVariant} onChange={(e) => setRuleVariant(e.target.value)}>
                <option value="">variant</option>
                {flag.variants.map((v) => (
                  <option key={v.key} value={v.key}>
                    {v.key}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn" type="submit">
              Add rule
            </button>
          </form>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <strong>SLOs</strong>
        <table className="table">
          <thead>
            <tr>
              <th>metric</th>
              <th>threshold</th>
              <th>min samples</th>
              <th>action</th>
            </tr>
          </thead>
          <tbody>
            {flag.slos.map((s) => (
              <tr key={s.id}>
                <td className="mono">{s.metric}</td>
                <td>{s.threshold}</td>
                <td>{s.min_samples}</td>
                <td>{s.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
