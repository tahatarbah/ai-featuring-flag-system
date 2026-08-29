import { FormEvent, useState } from "react";
import { AskResult, api } from "../api";

type HistoryItem = AskResult & { user_key: string; at: string };

export default function Playground() {
  const [userKey, setUserKey] = useState("alice");
  const [question, setQuestion] = useState("Our staging deploy is stuck on migrations. What should I check first?");
  const [result, setResult] = useState<AskResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [simNote, setSimNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [thumbNote, setThumbNote] = useState("");

  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setThumbNote("");
    try {
      const res = await api.ask(userKey, question);
      setResult(res);
      setHistory((h) => [{ ...res, user_key: userKey, at: new Date().toISOString() }, ...h].slice(0, 10));
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function thumb(score: number) {
    if (!result) return;
    await api.thumbs({
      user_key: userKey,
      variant_key: result.evaluation.variant_key,
      score,
      flag_key: "support_assistant",
    });
    setThumbNote(score >= 4 ? "Thumb up recorded" : "Thumb down recorded");
  }

  async function simulate() {
    setBusy(true);
    setErr("");
    setSimNote("");
    try {
      const out = await api.simulate(24, question);
      setSimNote(
        `Simulated ${out.asked} users → ${JSON.stringify(out.variants)}` +
          (out.avg_judge != null ? ` · avg judge ${out.avg_judge.toFixed(2)}` : ""),
      );
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="top">
        <div>
          <h1>Playground</h1>
          <p className="lede">Impersonate users, watch sticky assignment, and feed the quality monitor.</p>
        </div>
        <button className="btn" disabled={busy} type="button" onClick={simulate}>
          Simulate 24 users
        </button>
      </div>
      {err && <p className="err">{err}</p>}
      {simNote && <p className="ok">{simNote}</p>}
      <form className="card stack" onSubmit={ask}>
        <div>
          <label htmlFor="user">User key</label>
          <input id="user" value={userKey} onChange={(e) => setUserKey(e.target.value)} />
          <div className="spread" style={{ marginTop: 8 }}>
            {["alice", "bob", "carol", "dave", "eve"].map((u) => (
              <button key={u} type="button" className="btn" onClick={() => setUserKey(u)}>
                {u}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label htmlFor="q">Question</label>
          <textarea id="q" value={question} onChange={(e) => setQuestion(e.target.value)} />
        </div>
        <button className="btn primary" disabled={busy} type="submit">
          {busy ? "Working…" : "Ask support assistant"}
        </button>
      </form>
      {result && (
        <section className="card stack" style={{ marginTop: 16 }}>
          <div className="row">
            <span className="pill live">{result.evaluation.variant_key}</span>
            <span className="mono muted">{result.evaluation.reason}</span>
          </div>
          <p className="muted">
            {result.model} · {result.latency_ms}ms · {result.tokens_in}+{result.tokens_out} tokens
            {result.judge_score != null && ` · judge ${result.judge_score.toFixed(1)}/5`}
            {result.evaluation.bucket != null && ` · bucket ${result.evaluation.bucket}`}
          </p>
          {result.error_code && <p className="err">{result.error_code} — enable DEMO_MOCK_LLM or start Ollama</p>}
          <div className="answer">{result.answer || "No answer."}</div>
          {result.confidence_shown && <p className="pill">Confidence line on (show_confidence)</p>}
          {result.judge_reason && <p className="muted">{result.judge_reason}</p>}
          <div className="spread">
            <button className="btn" type="button" onClick={() => thumb(5)}>
              Thumb up
            </button>
            <button className="btn" type="button" onClick={() => thumb(1)}>
              Thumb down
            </button>
            {thumbNote && <span className="ok">{thumbNote}</span>}
          </div>
        </section>
      )}
      {history.length > 0 && (
        <section className="card" style={{ marginTop: 16 }}>
          <strong>Session history</strong>
          <table className="table">
            <thead>
              <tr>
                <th>user</th>
                <th>variant</th>
                <th>reason</th>
                <th>judge</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={`${h.at}-${i}`}>
                  <td className="mono">{h.user_key}</td>
                  <td>{h.evaluation.variant_key}</td>
                  <td className="mono">{h.evaluation.reason}</td>
                  <td>{h.judge_score?.toFixed(1) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
