import { Quality } from "../api";

function pct(n: number) {
  return `${Math.round(n * 1000) / 10}%`;
}

export default function MetricBars({ quality }: { quality: Quality }) {
  const control = quality.control;
  const treatment = quality.treatment;
  const maxErr = Math.max(control?.error_rate || 0, treatment?.error_rate || 0, 0.01);
  const maxLat = Math.max(control?.latency_p95 || 0, treatment?.latency_p95 || 0, 1);
  const maxTok = Math.max(control?.tokens_per_request || 0, treatment?.tokens_per_request || 0, 1);

  function row(label: string, c: number, t: number, max: number, fmt: (n: number) => string) {
    return (
      <div className="stack" key={label}>
        <span className="muted">{label}</span>
        <div className="bar-row">
          <span>control</span>
          <div className="bar">
            <span style={{ width: `${(c / max) * 100}%` }} />
          </div>
          <span className="mono">{fmt(c)}</span>
        </div>
        <div className="bar-row">
          <span>treatment</span>
          <div className="bar treat">
            <span style={{ width: `${(t / max) * 100}%` }} />
          </div>
          <span className="mono">{fmt(t)}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bars" style={{ marginTop: 12 }}>
      <p className="muted">
        Last {quality.window_minutes}m · samples {control?.samples ?? 0} / {treatment?.samples ?? 0}
      </p>
      {row("Error rate", control?.error_rate ?? 0, treatment?.error_rate ?? 0, maxErr, pct)}
      {row("Latency p95", control?.latency_p95 ?? 0, treatment?.latency_p95 ?? 0, maxLat, (n) => `${Math.round(n)}ms`)}
      {row("Judge mean", control?.judge_mean ?? 0, treatment?.judge_mean ?? 0, 5, (n) => n.toFixed(2))}
      {row("Tokens / req", control?.tokens_per_request ?? 0, treatment?.tokens_per_request ?? 0, maxTok, (n) => `${Math.round(n)}`)}
    </div>
  );
}
