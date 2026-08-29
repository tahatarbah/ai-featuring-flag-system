import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const DEFAULT_SLOS = [
  { metric: "error_rate", comparator: "max_delta", threshold: 0.05, min_samples: 20, action: "pause" },
  { metric: "latency_p95", comparator: "max_delta", threshold: 0.3, min_samples: 20, action: "pause" },
  { metric: "judge_mean", comparator: "max_delta", threshold: 0.4, min_samples: 20, action: "rollback" },
  { metric: "tokens_per_request", comparator: "max_delta", threshold: 2.0, min_samples: 20, action: "pause" },
];

export default function CreateFlag() {
  const nav = useNavigate();
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [flagType, setFlagType] = useState("multivariate");
  const [pct, setPct] = useState(5);
  const [controlPrompt, setControlPrompt] = useState("You are a concise support assistant. Answer in 3-6 sentences.");
  const [treatmentPrompt, setTreatmentPrompt] = useState(
    "You are a cautious support assistant. Prefer safety. Offer a short checklist.",
  );
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const isBool = flagType === "boolean";
      const variants = isBool
        ? [
            { key: "off", is_control: true, payload: { enabled: false } },
            { key: "on", is_control: false, payload: { enabled: true } },
          ]
        : [
            {
              key: "control",
              is_control: true,
              payload: {
                model: "llama3.2",
                prompt_id: "v1",
                temperature: 0.2,
                max_tokens: 512,
                system_prompt: controlPrompt,
              },
            },
            {
              key: "treatment",
              is_control: false,
              payload: {
                model: "llama3.2",
                prompt_id: "v2",
                temperature: 0.2,
                max_tokens: 640,
                system_prompt: treatmentPrompt,
              },
            },
          ];
      const flag = await api.createFlag({
        key: key.trim(),
        name: name.trim() || key.trim(),
        description,
        flag_type: flagType,
        percentage_bps: pct * 100,
        variants,
        slos: isBool ? [] : DEFAULT_SLOS,
      });
      await api.publish(flag.id);
      nav(`/flags/${flag.id}`);
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
          <h1>New flag</h1>
          <p className="lede">Create a boolean toggle or a multivariate AI variant payload, then publish.</p>
        </div>
      </div>
      {err && <p className="err">{err}</p>}
      <form className="card stack" onSubmit={submit} style={{ maxWidth: 720 }}>
        <div className="grid two">
          <div>
            <label htmlFor="key">Key</label>
            <input id="key" className="mono" required value={key} onChange={(e) => setKey(e.target.value)} placeholder="new_assistant" />
          </div>
          <div>
            <label htmlFor="name">Name</label>
            <input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New assistant" />
          </div>
        </div>
        <div>
          <label htmlFor="desc">Description</label>
          <textarea id="desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="grid two">
          <div>
            <label htmlFor="type">Type</label>
            <select id="type" value={flagType} onChange={(e) => setFlagType(e.target.value)}>
              <option value="multivariate">multivariate (AI payload)</option>
              <option value="boolean">boolean</option>
            </select>
          </div>
          <div>
            <label htmlFor="pct">Initial rollout ({pct}%)</label>
            <input id="pct" type="range" min={0} max={100} value={pct} onChange={(e) => setPct(Number(e.target.value))} />
          </div>
        </div>
        {flagType === "multivariate" && (
          <>
            <div>
              <label htmlFor="c">Control system prompt</label>
              <textarea id="c" value={controlPrompt} onChange={(e) => setControlPrompt(e.target.value)} />
            </div>
            <div>
              <label htmlFor="t">Treatment system prompt</label>
              <textarea id="t" value={treatmentPrompt} onChange={(e) => setTreatmentPrompt(e.target.value)} />
            </div>
          </>
        )}
        <button className="btn primary" disabled={busy} type="submit">
          {busy ? "Creating…" : "Create & publish"}
        </button>
      </form>
    </>
  );
}
