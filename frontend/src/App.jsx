import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import {
  Card,
  IncidentPicker,
  ChaosConsole,
  TriagePanel,
  DiagnosisPanel,
  RemediationPanel,
  ApprovalBar,
  ApprovalPanel,
  VerificationPanel,
  PostmortemPanel,
  EvalDashboard,
} from "./components.jsx";

// Pipeline lifecycle:
//   idle -> running -> awaiting_approval -> resuming -> done
export default function App() {
  const [tab, setTab] = useState("incident");

  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [chaos, setChaos] = useState({
    disable_sources: new Set(),
    break_primary_model: false,
  });

  const [phase, setPhase] = useState("idle");
  const [partial, setPartial] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const [evalSummary, setEvalSummary] = useState(null);
  const [evalRunning, setEvalRunning] = useState(false);

  const chaosActive =
    chaos.disable_sources.size > 0 || chaos.break_primary_model;
  const busy = phase === "running" || phase === "resuming";

  useEffect(() => {
    api
      .listIncidents()
      .then((list) => {
        setIncidents(list);
        if (list.length) setSelectedId(list[0].id);
      })
      .catch((e) => setError(e.message));
    api.latestEval().then(setEvalSummary).catch(() => {});
  }, []);

  function chaosConfig() {
    if (!chaosActive) return null;
    return {
      disable_sources: [...chaos.disable_sources],
      break_primary_model: chaos.break_primary_model,
    };
  }

  async function startRun() {
    setError(null);
    setResult(null);
    setPartial(null);
    setPhase("running");
    try {
      const r = await api.startRun(selectedId, chaosConfig());
      setPartial(r);
      if (r.status === "resolved") {
        // Fully autonomous — no risky actions, so it ran to completion with no gate.
        setResult(r);
        setPhase("done");
      } else {
        setPhase("awaiting_approval");
      }
    } catch (e) {
      setError(e.message);
      setPhase("idle");
    }
  }

  async function decide(approved) {
    setError(null);
    setPhase("resuming");
    try {
      const r = await api.approve(
        partial.run_id,
        approved,
        approved ? "Approved via console" : "Denied via console"
      );
      setResult(r);
      setPhase("done");
    } catch (e) {
      setError(e.message);
      setPhase("awaiting_approval");
    }
  }

  async function runEval() {
    setEvalRunning(true);
    setError(null);
    try {
      setEvalSummary(await api.runEval());
    } catch (e) {
      setError(e.message);
    } finally {
      setEvalRunning(false);
    }
  }

  const statusLabel =
    phase === "running" || phase === "resuming"
      ? "crew dispatched"
      : chaosActive
      ? "chaos armed"
      : "systems nominal";
  const statusTone =
    phase === "running" || phase === "resuming"
      ? "amber"
      : chaosActive
      ? "amber"
      : "green";

  return (
    <div className="app">
      <div className="bg" aria-hidden="true">
        <div className="bg-glow" />
        <div className="bg-grid" />
        <div className="bg-sweep" />
        <div className="bg-scan" />
      </div>

      <header className="topbar">
        <div className="brand">
          <span className="logo">◎</span>
          <div>
            <h1>RescueOps</h1>
            <p>Incident First Responder</p>
          </div>
        </div>
        <nav className="tabs">
          <button
            className={tab === "incident" ? "active" : ""}
            onClick={() => setTab("incident")}
          >
            Response
          </button>
          <button
            className={tab === "eval" ? "active" : ""}
            onClick={() => setTab("eval")}
          >
            Eval
          </button>
        </nav>
        <div className="status">
          <span
            className="beacon"
            style={{
              background: statusTone === "green" ? "var(--green)" : "var(--amber)",
              boxShadow:
                statusTone === "green"
                  ? "0 0 0 0 rgba(47,245,160,0.6)"
                  : "0 0 0 0 rgba(255,176,0,0.6)",
            }}
          />
          {statusLabel} · gateway truefoundry
        </div>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {tab === "incident" && (
        <main className="layout">
          <aside className="sidebar">
            <Card title="Run an incident">
              <IncidentPicker
                incidents={incidents}
                value={selectedId}
                onChange={setSelectedId}
                disabled={busy}
              />
              <button
                className="btn btn-primary btn-block"
                disabled={busy || !selectedId}
                onClick={startRun}
              >
                {phase === "running" ? "Responding…" : "▶ Run incident"}
              </button>
            </Card>

            <ChaosConsole chaos={chaos} setChaos={setChaos} disabled={busy} />
          </aside>

          <section className="timeline">
            {phase === "idle" && !partial && (
              <div className="empty">
                Select an incident and press <strong>Run</strong> to dispatch the
                crew.
              </div>
            )}

            {phase === "running" && (
              <div className="empty pulse">
                Crew responding — triage → diagnosis → remediation…
              </div>
            )}

            {partial && (
              <>
                <TriagePanel triage={partial.triage} />
                <DiagnosisPanel
                  diagnosis={partial.diagnosis}
                  chaosActive={!!partial.chaos_config}
                />
                <RemediationPanel
                  remediation={partial.remediation}
                  executedSafe={partial.executed_safe}
                />

                {phase === "done" && partial.status === "resolved" &&
                  !partial.remediation.risky.length && (
                    <div className="empty" style={{ color: "var(--green)" }}>
                      ✓ Resolved autonomously — no risky actions, so the safe fixes
                      were applied without a human gate.
                    </div>
                  )}

                {phase === "awaiting_approval" && (
                  <ApprovalBar
                    remediation={partial.remediation}
                    onDecide={decide}
                    busy={busy}
                  />
                )}
                {phase === "resuming" && (
                  <div className="empty pulse">
                    Applying decision — verification → postmortem…
                  </div>
                )}
              </>
            )}

            {result && (
              <>
                <ApprovalPanel approval={result.approval} />
                <VerificationPanel verification={result.verification} />
                <PostmortemPanel postmortem={result.postmortem} />
                <div className="run-footer muted small">
                  run_id {result.run_id}
                </div>
              </>
            )}
          </section>
        </main>
      )}

      {tab === "eval" && (
        <main className="eval-main">
          <EvalDashboard
            summary={evalSummary}
            onRun={runEval}
            running={evalRunning}
          />
        </main>
      )}
    </div>
  );
}
