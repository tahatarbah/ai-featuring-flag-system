import { FormEvent, useEffect, useState } from "react";
import { EvalResult, Flag, api } from "../api";

export default function EvaluatePage() {
  const [flags, setFlags] = useState<Flag[]>([]);
  const [flagKey, setFlagKey] = useState("support_assistant");
  const [userKey, setUserKey] = useState("alice");
  const [attrJson, setAttrJson] = useState('{"plan":"pro"}');
  const [result, setResult] = useState<EvalResult | null>(null);
  const [history, setHistory] = useState<EvalResult[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.flags().then((f) => {
      setFlags(f);
      if (f[0]) setFlagKey(f[0].key);
    });
  }, []);

  async function run(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      let attributes: Record<string, string> = {};
      if (attrJson.trim()) attributes = JSON.parse(attrJson);
      const res = await api.evaluate(flagKey, userKey, attributes);
      setResult(res);
      setHistory((h) => [res, ...h].slice(0, 12));
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  return (
    <>
      <div className="top">
        <div>
          <h1>Assignment debugger</h1>
          <p className="lede">See which variant a user gets and why — kill switch, targeting, or sticky percentage.</p>
        </div>
      </div>
      {err && <p className="err">{err}</p>}
      <form className="card stack" onSubmit={run}>
        <div className="grid two">
          <div>
            <label htmlFor="flag">Flag</label>
            <select id="flag" value={flagKey} onChange={(e) => setFlagKey(e.target.value)}>
              {flags.map((f) => (
                <option key={f.id} value={f.key}>
                  {f.key}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="user">User key</label>
            <input id="user" value={userKey} onChange={(e) => setUserKey(e.target.value)} />
          </div>
        </div>
        <div>
          <label htmlFor="attrs">Attributes (JSON)</label>
          <textarea id="attrs" value={attrJson} onChange={(e) => setAttrJson(e.target.value)} />
        </div>
        <div className="spread">
          {["alice", "bob", "carol", "dave", "eve"].map((u) => (
            <button key={u} type="button" className="btn" onClick={() => setUserKey(u)}>
              {u}
            </button>
          ))}
        </div>
        <button className="btn primary" type="submit">
          Evaluate
        </button>
      </form>

      {result && (
        <section className="card stack" style={{ marginTop: 16 }}>
          <div className="row">
            <span className="pill live">{result.variant_key}</span>
            <span className="mono muted">{result.reason}</span>
          </div>
          <p className="muted">
            bucket {result.bucket ?? "—"} · flag <span className="mono">{result.flag_key}</span>
          </p>
          <pre className="code-block">{JSON.stringify(result.payload, null, 2)}</pre>
        </section>
      )}

      {history.length > 0 && (
        <section className="card" style={{ marginTop: 16 }}>
          <strong>Recent evaluations</strong>
          <table className="table">
            <thead>
              <tr>
                <th>flag</th>
                <th>variant</th>
                <th>reason</th>
                <th>bucket</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={`${h.flag_key}-${i}`}>
                  <td className="mono">{h.flag_key}</td>
                  <td>{h.variant_key}</td>
                  <td className="mono">{h.reason}</td>
                  <td className="mono">{h.bucket ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
