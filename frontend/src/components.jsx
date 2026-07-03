// Presentational components for the RescueOps console.
import React from "react";

export function Card({ title, badge, accent, children }) {
  return (
    <section className={`card${accent ? ` accent-${accent}` : ""}`}>
      <header className="card-head">
        <h3>{title}</h3>
        {badge}
      </header>
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Pill({ tone = "neutral", children }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

function sevTone(sev) {
  if (sev === "SEV-1") return "danger";
  if (sev === "SEV-2") return "warn";
  return "neutral";
}

// ── Incident picker ────────────────────────────────────────────────────────
export function IncidentPicker({ incidents, value, onChange, disabled }) {
  return (
    <div className="picker">
      <label>Incident</label>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {incidents.map((inc) => (
          <option key={inc.id} value={inc.id}>
            {inc.title || inc.id}
          </option>
        ))}
      </select>
      <p className="alert-line">
        {incidents.find((i) => i.id === value)?.alert}
      </p>
    </div>
  );
}

// ── Chaos console ──────────────────────────────────────────────────────────
const SOURCES = ["logs", "metrics", "deploys"];

export function ChaosConsole({ chaos, setChaos, disabled }) {
  const toggleSource = (src) => {
    const next = new Set(chaos.disable_sources);
    next.has(src) ? next.delete(src) : next.add(src);
    setChaos({ ...chaos, disable_sources: next });
  };
  const anyActive =
    chaos.disable_sources.size > 0 || chaos.break_primary_model;

  return (
    <Card
      title="Chaos Console"
      accent={anyActive ? "warn" : null}
      badge={anyActive ? <Pill tone="warn">degradation armed</Pill> : null}
    >
      <p className="muted small">
        Disable a telemetry source and confidence drops mechanically — a computed
        drop, not an LLM guess.
      </p>
      <div className="toggles">
        {SOURCES.map((src) => (
          <label key={src} className="toggle">
            <input
              type="checkbox"
              disabled={disabled}
              checked={chaos.disable_sources.has(src)}
              onChange={() => toggleSource(src)}
            />
            <span>disable {src}</span>
          </label>
        ))}
        <label className="toggle">
          <input
            type="checkbox"
            disabled={disabled}
            checked={chaos.break_primary_model}
            onChange={() =>
              setChaos({
                ...chaos,
                break_primary_model: !chaos.break_primary_model,
              })
            }
          />
          <span>break primary model (force fallback)</span>
        </label>
      </div>
    </Card>
  );
}

// ── Artifact panels ────────────────────────────────────────────────────────
export function TriagePanel({ triage }) {
  return (
    <Card
      title="① Triage"
      badge={<Pill tone={sevTone(triage.severity)}>{triage.severity}</Pill>}
    >
      <p className="lead">{triage.summary}</p>
      <dl className="kv">
        <dt>Customer-facing</dt>
        <dd>{triage.customer_facing ? "yes" : "no"}</dd>
        <dt>Route to</dt>
        <dd>{triage.route_to}</dd>
        <dt>Reason</dt>
        <dd>{triage.reason}</dd>
      </dl>
    </Card>
  );
}

export function DiagnosisPanel({ diagnosis, chaosActive }) {
  const pct = Math.round(diagnosis.confidence * 100);
  const tone = pct >= 80 ? "good" : pct >= 50 ? "warn" : "danger";
  return (
    <Card
      title="② Diagnosis"
      badge={<Pill tone={tone}>confidence {pct}%</Pill>}
    >
      <p className="lead">{diagnosis.root_cause}</p>
      <div className="confidence-bar">
        <div className={`fill fill-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {chaosActive && (
        <p className="muted small">
          Confidence reflects reduced telemetry coverage under active chaos.
        </p>
      )}
      <h4>Cited evidence</h4>
      <ul className="evidence">
        {diagnosis.cited_evidence.length === 0 && (
          <li className="muted">none cited</li>
        )}
        {diagnosis.cited_evidence.map((e, i) => (
          <li key={i}><code>{e}</code></li>
        ))}
      </ul>
      <h4>Reasoning</h4>
      <p className="muted">{diagnosis.reasoning}</p>
    </Card>
  );
}

function ActionList({ actions, tone }) {
  if (!actions.length) return <p className="muted small">none</p>;
  return (
    <ul className="actions">
      {actions.map((a, i) => (
        <li key={i}>
          <span className={`dot dot-${tone}`} />
          <div>
            <strong>{a.action}</strong>
            <p className="muted small">{a.rationale}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function RemediationPanel({ remediation, executedSafe }) {
  const safe = executedSafe && executedSafe.length ? executedSafe : remediation.safe;
  const hasRisky = remediation.risky.length > 0;
  return (
    <Card
      title="③ Remediation Plan"
      badge={
        safe.length ? (
          <Pill tone="good">{safe.length} safe auto-applied</Pill>
        ) : null
      }
    >
      <h4 className="safe-h">Safe — auto-executed ✓</h4>
      <ActionList actions={safe} tone="good" />
      <h4 className="risky-h">
        {hasRisky ? "Risky — require approval" : "Risky — none proposed"}
      </h4>
      <ActionList actions={remediation.risky} tone="danger" />
    </Card>
  );
}

export function ApprovalBar({ remediation, onDecide, busy }) {
  const hasRisky = remediation.risky.length > 0;
  return (
    <div className="approval-bar">
      <div>
        <strong>Approval gate</strong>
        <p className="muted small">
          {hasRisky
            ? `${remediation.risky.length} risky action(s) await a human decision.`
            : "No risky actions — approve to finalize."}
        </p>
      </div>
      <div className="approval-buttons">
        <button
          className="btn btn-danger"
          disabled={busy}
          onClick={() => onDecide(false)}
        >
          Deny
        </button>
        <button
          className="btn btn-primary"
          disabled={busy}
          onClick={() => onDecide(true)}
        >
          Approve
        </button>
      </div>
    </div>
  );
}

export function ApprovalPanel({ approval }) {
  return (
    <Card
      title="④ Approval"
      badge={
        <Pill tone={approval.approved ? "good" : "danger"}>
          {approval.approved ? "approved" : "denied"}
        </Pill>
      }
    >
      <dl className="kv">
        <dt>Approver</dt>
        <dd>{approval.approver}</dd>
        <dt>Note</dt>
        <dd>{approval.note || "—"}</dd>
      </dl>
    </Card>
  );
}

export function VerificationPanel({ verification }) {
  return (
    <Card
      title="⑤ Verification"
      badge={
        <Pill tone={verification.recovered ? "good" : "danger"}>
          {verification.recovered ? "recovered" : "not recovered"}
        </Pill>
      }
    >
      <dl className="kv">
        <dt>Metric</dt>
        <dd><code>{verification.metric_name}</code></dd>
        <dt>Observed</dt>
        <dd>{verification.observed_value}</dd>
        <dt>Threshold</dt>
        <dd>{verification.threshold}</dd>
        <dt>Note</dt>
        <dd>{verification.note}</dd>
      </dl>
    </Card>
  );
}

export function PostmortemPanel({ postmortem }) {
  return (
    <Card title="⑥ Postmortem">
      <p className="lead">{postmortem.summary}</p>
      <h4>Confirmed root cause</h4>
      <p className="muted">{postmortem.root_cause}</p>
      <h4>Timeline</h4>
      <ol className="timeline">
        {postmortem.timeline.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ol>
      <h4>Actions taken</h4>
      <ul>{postmortem.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
      <h4>Follow-ups</h4>
      <ul>{postmortem.follow_ups.map((f, i) => <li key={i}>{f}</li>)}</ul>
    </Card>
  );
}

// ── Eval dashboard ─────────────────────────────────────────────────────────
function pctText(x) {
  return `${Math.round(x * 100)}%`;
}

export function EvalDashboard({ summary, onRun, running }) {
  return (
    <div>
      <div className="eval-head">
        <div>
          <h2>Evaluation</h2>
          <p className="muted small">
            Scores the pipeline against 5 labeled incidents. Ground truth is read
            only here — agents never see it.
          </p>
        </div>
        <button className="btn btn-primary" disabled={running} onClick={onRun}>
          {running ? "Running…" : "Run evaluation (all 5)"}
        </button>
      </div>

      {!summary && !running && (
        <p className="muted">No evaluation has been run yet.</p>
      )}

      {summary && (
        <>
          <div className="stat-grid">
            <Stat
              label="Severity accuracy"
              value={pctText(summary.aggregate.severity_accuracy)}
            />
            <Stat
              label="Mean evidence recall"
              value={pctText(summary.aggregate.mean_evidence_recall)}
            />
            <Stat
              label="Mean remediation overlap"
              value={pctText(summary.aggregate.mean_remediation_overlap)}
            />
            <Stat
              label="Recovery rate"
              value={pctText(summary.aggregate.recovery_rate)}
            />
          </div>

          <table className="eval-table">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Severity</th>
                <th>Evidence recall</th>
                <th>Remediation overlap</th>
                <th>Confidence</th>
                <th>Recovered</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_incident.map((r) => (
                <tr key={r.incident_id}>
                  <td>{r.incident_id}</td>
                  <td>{r.severity_correct ? "✓" : "✗"}</td>
                  <td>{pctText(r.evidence_recall)}</td>
                  <td>{pctText(r.remediation_overlap)}</td>
                  <td>{pctText(r.confidence)}</td>
                  <td>{r.recovered ? "✓" : "✗"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
