"""RescueOps — Streamlit control plane (Track B).

Mission-control aesthetic: dark, editorial, type-driven.
Vertical timeline with connected nodes. Measured confidence, not vibes.
"""
import json
from pathlib import Path

import streamlit as st

import audit
import evaluation
import incidents
import voice
from pipeline import run_incident
from schemas import ApprovalDecision, RemediationPlan, RunResult

TELEMETRY_SOURCES = ["logs", "metrics", "deploys"]

_DEMO_PATH = Path(__file__).parent / "demo_example.json"


def _load_demo_result():
    if not _DEMO_PATH.exists():
        return None
    try:
        return RunResult(**json.loads(_DEMO_PATH.read_text()))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Design system CSS — mission-control / flight-recorder aesthetic
# ---------------------------------------------------------------------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
    --bg: #09090B;
    --fg: #FAFAFA;
    --fg-2: #E4E4E7;
    --muted: #18181B;
    --muted-2: #27272A;
    --muted-fg: #71717A;
    --accent: #EF4444;
    --accent-dim: rgba(239,68,68,0.08);
    --accent-mid: rgba(239,68,68,0.15);
    --green: #22C55E;
    --green-dim: rgba(34,197,94,0.08);
    --amber: #F59E0B;
    --amber-dim: rgba(245,158,11,0.08);
    --border: #27272A;
    --border-subtle: #1E1E22;
}

/* ── Global ── */
.stApp {
    background-color: var(--bg) !important;
    font-family: "Inter Tight", system-ui, -apple-system, sans-serif !important;
    letter-spacing: -0.005em;
    color: var(--fg) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    opacity: 0.02;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-repeat: repeat;
    background-size: 200px 200px;
}

/* ── Kill all radius ── */
.stApp [data-testid], .stApp button, .stApp input, .stApp select,
.stApp textarea, .stApp details, .stApp summary,
.stApp [data-baseweb="select"] > div,
.stApp [data-testid="stExpander"],
.stApp [data-testid="stDataFrame"],
.stApp [data-testid="stAlert"] {
    border-radius: 0px !important;
}

/* ── Typography ── */
h1, .stApp h1 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    line-height: 1.15 !important;
    font-size: 2.6rem !important;
    color: var(--fg) !important;
}
h2, .stApp h2 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    font-size: 1.5rem !important;
    line-height: 1.25 !important;
    color: var(--fg) !important;
}
h3, .stApp h3 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.012em !important;
    font-size: 1.15rem !important;
    line-height: 1.3 !important;
    color: var(--fg) !important;
}
p, li, span, .stMarkdown {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    letter-spacing: -0.003em;
    line-height: 1.6 !important;
}
.stApp p, .stApp li, .stMarkdown p, .stMarkdown li {
    color: var(--fg-2);
}
code, .stCode, [data-testid="stCode"] {
    font-family: "JetBrains Mono", "Fira Code", monospace !important;
    font-size: 0.78rem !important;
    background: var(--muted) !important;
    padding: 0.15em 0.35em !important;
    border: 1px solid var(--border-subtle) !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: var(--bg) !important;
    border-right: 1px solid var(--border) !important;
    width: 320px !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding: 1.5rem 1.25rem !important;
}

/* ── Buttons ── */
.stApp button[kind="primary"],
.stApp button[data-testid="stBaseButton-primary"] {
    background-color: var(--accent) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 0px !important;
    font-family: "JetBrains Mono", monospace !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    font-size: 0.72rem !important;
    transition: all 120ms cubic-bezier(0.25, 0, 0, 1) !important;
    padding: 0.7rem 1.5rem !important;
}
.stApp button[kind="primary"]:hover,
.stApp button[data-testid="stBaseButton-primary"]:hover {
    background-color: #DC2626 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(239,68,68,0.25) !important;
}
.stApp button[kind="primary"]:active,
.stApp button[data-testid="stBaseButton-primary"]:active {
    transform: translateY(0px) !important;
    box-shadow: none !important;
}

.stApp button[kind="secondary"],
.stApp button[data-testid="stBaseButton-secondary"] {
    background-color: transparent !important;
    color: var(--fg-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
    font-family: "JetBrains Mono", monospace !important;
    font-weight: 500 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    font-size: 0.72rem !important;
    transition: all 120ms !important;
}
.stApp button[kind="secondary"]:hover,
.stApp button[data-testid="stBaseButton-secondary"]:hover {
    background-color: var(--muted) !important;
    border-color: var(--muted-fg) !important;
}

/* ── Inputs ── */
.stApp [data-baseweb="select"] > div {
    background-color: var(--muted) !important;
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
    font-size: 0.85rem !important;
}

/* ── Tabs ── */
.stApp [data-testid="stTab"] {
    font-family: "JetBrains Mono", monospace !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    font-size: 0.68rem !important;
    padding: 0.75rem 1.75rem !important;
    border-radius: 0px !important;
    color: var(--muted-fg) !important;
    border-bottom: 2px solid transparent !important;
    transition: all 120ms !important;
}
.stApp [data-testid="stTab"][aria-selected="true"] {
    color: var(--fg) !important;
    border-bottom-color: var(--accent) !important;
    background: transparent !important;
}
.stApp [data-testid="stTab"]:hover {
    color: var(--fg-2) !important;
}
.stApp [data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}

/* ── Metrics (Streamlit native) ── */
[data-testid="stMetric"] {
    background: transparent !important;
    border-left: 2px solid var(--accent) !important;
    padding: 0.5rem 0.75rem !important;
}
[data-testid="stMetric"] label {
    font-family: "JetBrains Mono", monospace !important;
    font-size: 0.6rem !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: var(--muted-fg) !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    font-size: 1.8rem !important;
    letter-spacing: -0.025em !important;
}

/* ── Expander ── */
.stApp [data-testid="stExpander"] {
    border: 1px solid var(--border-subtle) !important;
    border-radius: 0px !important;
    background: transparent !important;
    transition: border-color 150ms !important;
}
.stApp [data-testid="stExpander"]:hover {
    border-color: var(--muted-fg) !important;
}
.stApp [data-testid="stExpander"] summary {
    font-family: "JetBrains Mono", monospace !important;
    font-weight: 500 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    font-size: 0.68rem !important;
    color: var(--muted-fg) !important;
}
.stApp [data-testid="stExpander"] summary:hover {
    color: var(--fg-2) !important;
}

/* ── Alerts ── */
.stApp [data-testid="stAlert"] {
    border-radius: 0px !important;
    border: none !important;
    border-left: 2px solid !important;
    background-color: var(--muted) !important;
}

/* ── Dividers ── */
.stApp hr { border-color: var(--border-subtle) !important; margin: 1.5rem 0 !important; }

/* ── Dataframe ── */
.stApp [data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
}

/* ── Checkboxes & radio ── */
.stApp [data-testid="stCheckbox"] label,
.stApp [data-testid="stRadio"] label {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-size: 0.82rem !important;
}

/* ── Hide chrome ── */
header[data-testid="stHeader"] { background-color: var(--bg) !important; }
footer { display: none !important; }

/* ============================================================
   CUSTOM COMPONENTS
   ============================================================ */

/* ── Mono label (reusable) ── */
.mono-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted-fg);
    line-height: 1;
}

/* ── Hero ── */
.ro-hero {
    padding: 0.5rem 0 1.75rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1.5rem;
}
.ro-hero-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 750;
    font-size: 2.4rem;
    letter-spacing: -0.03em;
    line-height: 1.08;
    color: var(--fg);
}
.ro-hero-title .accent { color: var(--accent); }
.ro-hero-sub {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin-top: 0.6rem;
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
}
.ro-hero-sub span {
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.ro-hero-sub .dot {
    width: 5px; height: 5px;
    background: var(--accent);
    display: inline-block;
    flex-shrink: 0;
}

/* ── Sidebar sections ── */
.sb-section {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.58rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin: 1.5rem 0 0.4rem 0;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--border-subtle);
}
.sb-brand {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 700;
    font-size: 1.2rem;
    letter-spacing: -0.025em;
    color: var(--fg);
    margin-bottom: 0.25rem;
}
.sb-brand .accent { color: var(--accent); }

/* ── Production path ── */
.prod-path {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.04em;
    color: var(--muted-fg);
    line-height: 1.65;
    border-top: 1px solid var(--border-subtle);
    padding-top: 0.75rem;
    margin-top: 1rem;
}
.prod-path strong { color: var(--accent); }

/* ── Section header ── */
.sec-header {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 650;
    font-size: 1.6rem;
    letter-spacing: -0.025em;
    line-height: 1.2;
    color: var(--fg);
}
.sec-sub {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.85rem;
    color: var(--muted-fg);
    line-height: 1.6;
    margin-top: 0.35rem;
}

/* ── Timeline stage ── */
.tl-stage {
    display: flex;
    gap: 1.25rem;
    padding: 1.25rem 0;
    position: relative;
}
.tl-rail {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 36px;
    flex-shrink: 0;
    position: relative;
}
.tl-node {
    width: 36px;
    height: 36px;
    border: 2px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: "JetBrains Mono", monospace;
    font-weight: 700;
    font-size: 0.72rem;
    color: var(--muted-fg);
    background: var(--bg);
    z-index: 2;
    flex-shrink: 0;
    transition: all 200ms;
}
.tl-node.done {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-dim);
}
.tl-node.held {
    border-color: var(--amber);
    color: var(--amber);
    background: var(--amber-dim);
}
.tl-node.pass {
    border-color: var(--green);
    color: var(--green);
    background: var(--green-dim);
}
.tl-line {
    width: 2px;
    flex-grow: 1;
    background: var(--border-subtle);
    min-height: 12px;
}
.tl-line.done { background: var(--accent); opacity: 0.3; }

.tl-body {
    flex-grow: 1;
    min-width: 0;
    padding-top: 0.35rem;
}
.tl-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 1rem;
    letter-spacing: -0.01em;
    color: var(--fg);
    margin-bottom: 0.1rem;
}
.tl-title-label {
    font-family: "JetBrains Mono", monospace;
    font-weight: 500;
    font-size: 0.6rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin-bottom: 0.2rem;
}

/* ── Metric row ── */
.m-row {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin: 0.6rem 0;
}
.m-item {
    border-left: 2px solid var(--border);
    padding: 0.35rem 0 0.35rem 0.65rem;
    min-width: 100px;
    transition: border-color 150ms;
}
.m-item:hover { border-color: var(--muted-fg); }
.m-item.accent-border { border-color: var(--accent); }
.m-item.green-border { border-color: var(--green); }
.m-item.amber-border { border-color: var(--amber); }

.m-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.55rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin-bottom: 0.1rem;
}
.m-val {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 1.5rem;
    letter-spacing: -0.025em;
    color: var(--fg);
    line-height: 1.2;
}
.m-val.red { color: var(--accent); }
.m-val.green { color: var(--green); }
.m-val.amber { color: var(--amber); }
.m-val.lg {
    font-size: 2.25rem;
    letter-spacing: -0.03em;
}

/* ── Evidence ── */
.ev-item {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.75rem;
    color: var(--fg-2);
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid var(--border-subtle);
    transition: background 120ms;
    letter-spacing: -0.01em;
}
.ev-item:hover { background: var(--muted); }
.ev-item:last-child { border-bottom: none; }
.ev-item::before {
    content: "";
    display: inline-block;
    width: 4px; height: 4px;
    background: var(--accent);
    margin-right: 0.6rem;
    vertical-align: middle;
}

/* ── Action cards ── */
.act-card {
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border-subtle);
}
.act-card:last-child { border-bottom: none; }
.act-name {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.82rem;
    color: var(--fg);
    line-height: 1.35;
}
.act-rationale {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.75rem;
    color: var(--muted-fg);
    margin-top: 0.15rem;
    line-height: 1.4;
}
.badge {
    display: inline-block;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.55rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 0.1rem 0.45rem;
    margin-left: 0.5rem;
    vertical-align: middle;
}
.badge-safe { border: 1px solid var(--muted-fg); color: var(--muted-fg); }
.badge-ok { border: 1px solid var(--green); color: var(--green); }
.badge-held { border: 1px solid var(--amber); color: var(--amber); }

/* ── Gate panel (approval) ── */
.gate-panel {
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
}
.gate-panel.approved {
    border-left: 3px solid var(--green);
    background: var(--green-dim);
}
.gate-panel.held {
    border-left: 3px solid var(--amber);
    background: var(--amber-dim);
}
.gate-status {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}
.gate-status.approved { color: var(--green); }
.gate-status.held { color: var(--amber); }
.gate-detail {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.8rem;
    color: var(--fg-2);
}

/* ── Chaos banner ── */
.chaos-bar {
    border: 1px solid var(--accent);
    border-left: 3px solid var(--accent);
    background: var(--accent-dim);
    padding: 0.65rem 1rem;
    margin-bottom: 1.25rem;
    position: relative;
    overflow: hidden;
}
.chaos-bar::after {
    content: "";
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(239,68,68,0.04), transparent);
    animation: chaos-scan 3s linear infinite;
}
@keyframes chaos-scan {
    0% { left: -100%; }
    100% { left: 100%; }
}
.chaos-bar .mono-label { color: var(--accent); margin-bottom: 0.2rem; }
.chaos-bar .detail {
    font-size: 0.8rem;
    color: var(--fg-2);
    line-height: 1.45;
    position: relative;
    z-index: 1;
}

/* Demo banner */
.demo-bar {
    border: 1px solid var(--border);
    border-left: 3px solid var(--muted-fg);
    background: rgba(255,255,255,0.015);
    padding: 0.65rem 1rem;
    margin-bottom: 1.25rem;
}

/* ── Audit log ── */
.aud-row {
    display: flex;
    gap: 0.75rem;
    padding: 0.25rem 0;
    border-bottom: 1px solid var(--border-subtle);
    align-items: baseline;
}
.aud-row:last-child { border-bottom: none; }
.aud-time {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.62rem;
    color: var(--muted-fg);
    flex-shrink: 0;
}
.aud-stage {
    font-family: "JetBrains Mono", monospace;
    font-weight: 600;
    font-size: 0.68rem;
    color: var(--fg-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Timeline entries (postmortem) ── */
.tl-entry {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.25rem 0;
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.8rem;
    color: var(--fg-2);
    line-height: 1.4;
}
.tl-entry-dot {
    width: 5px; height: 5px;
    background: var(--accent);
    flex-shrink: 0;
    margin-top: 0.4rem;
}

/* ── Empty state ── */
.empty {
    text-align: center;
    padding: 5rem 2rem;
    border: 1px dashed var(--border);
}
.empty-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 700;
    font-size: 1rem;
    color: var(--muted-fg);
    margin-bottom: 0.4rem;
}
.empty-hint {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-fg);
    opacity: 0.5;
}

/* ── Eval per-incident row ── */
.eval-row {
    display: grid;
    grid-template-columns: 2fr repeat(4, 1fr);
    gap: 0;
    border-bottom: 1px solid var(--border-subtle);
    padding: 0.6rem 0;
    align-items: center;
    font-size: 0.8rem;
    transition: background 120ms;
}
.eval-row:hover { background: var(--muted); }
.eval-row-header {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.58rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted-fg);
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem;
    margin-bottom: 0.2rem;
}
.eval-cell {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
    color: var(--fg-2);
    padding: 0 0.5rem;
}
.eval-cell.name {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.8rem;
    color: var(--fg);
}
.eval-pass { color: var(--green); }
.eval-fail { color: var(--accent); }
.eval-mid { color: var(--amber); }
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_chaos_config(disable_sources: list[str], break_primary_model: bool) -> dict | None:
    if not disable_sources and not break_primary_model:
        return None
    return {"disable_sources": list(disable_sources), "break_primary_model": break_primary_model}


def make_approval_callback(approve_risky: bool):
    def _callback(plan: RemediationPlan) -> ApprovalDecision:
        note = (
            "Operator approved risky actions via UI"
            if approve_risky
            else "Operator held risky actions (safe default)"
        )
        return ApprovalDecision(approved=approve_risky, approver="human-ui", note=note)
    return _callback


def _html(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


def _m(label: str, value: str, color: str = "", size: str = "", border: str = "accent-border") -> str:
    """Build one metric-item HTML."""
    vcls = "m-val"
    if color:
        vcls += f" {color}"
    if size:
        vcls += f" {size}"
    return f"""<div class="m-item {border}">
        <div class="m-label">{label}</div>
        <div class="{vcls}">{value}</div>
    </div>"""


def _tl_open(num: int, title: str, label: str = "", node_cls: str = "done") -> None:
    """Open a timeline stage block (call _tl_close after content)."""
    label_html = f'<div class="tl-title-label">{label}</div>' if label else ""
    _html(f"""<div class="tl-stage">
        <div class="tl-rail">
            <div class="tl-node {node_cls}">{num:02d}</div>
            <div class="tl-line done"></div>
        </div>
        <div class="tl-body">
            {label_html}
            <div class="tl-title">{title}</div>""")


def _tl_close() -> None:
    _html("</div></div>")


# ---------------------------------------------------------------------------
# Rendering — each pipeline stage
# ---------------------------------------------------------------------------

def _render_triage(t) -> None:
    sev_color = "red" if t.severity == "SEV-1" else ("amber" if t.severity == "SEV-2" else "")
    cust_color = "amber" if t.customer_facing else ""
    _tl_open(1, "Triage", "Stage 1")
    _html(f"""<div class="m-row">
        {_m("Severity", t.severity, sev_color, "lg")}
        {_m("Customer Facing", "YES" if t.customer_facing else "NO", cust_color, "", "amber-border" if t.customer_facing else "accent-border")}
        {_m("Route To", t.route_to, "", "", "accent-border")}
    </div>""")
    _html(f'<div style="font-size:0.85rem; color:var(--fg-2); margin:0.5rem 0; line-height:1.5;">{t.summary}</div>')
    _html(f'<div class="mono-label" style="margin-top:0.25rem;">Reason: {t.reason}</div>')
    _tl_close()


def _render_diagnosis(d, chaos_config) -> None:
    conf_color = "green" if d.confidence >= 0.8 else ("amber" if d.confidence >= 0.5 else "red")
    conf_border = "green-border" if d.confidence >= 0.8 else ("amber-border" if d.confidence >= 0.5 else "accent-border")
    _tl_open(2, "Diagnosis", "Stage 2")

    _html(f"""<div class="m-row">
        {_m("Confidence", f"{d.confidence:.2f}", conf_color, "lg", conf_border)}
    </div>""")

    if chaos_config and chaos_config.get("disable_sources"):
        sources = ", ".join(chaos_config["disable_sources"])
        _html(f"""<div class="chaos-bar" style="margin-top:0.6rem;">
            <div class="mono-label">Telemetry Degraded</div>
            <div class="detail">Sources disabled: <strong>{sources}</strong>. Confidence computed from remaining sources — not by the LLM.</div>
        </div>""")

    _html(f"""<div style="margin-top:0.5rem;">
        <div class="mono-label">Root Cause</div>
        <div style="font-size:0.88rem; color:var(--fg); line-height:1.5; margin-top:0.2rem;">{d.root_cause}</div>
    </div>""")
    _tl_close()

    with st.expander("CITED EVIDENCE"):
        if d.cited_evidence:
            _html("".join(f'<div class="ev-item">{ev}</div>' for ev in d.cited_evidence))
        else:
            _html('<div class="ev-item" style="color:var(--muted-fg);">No evidence cited</div>')

    with st.expander("REASONING"):
        st.write(d.reasoning)


def _render_remediation(plan, decision, diagnosis=None) -> None:
    _tl_open(3, "Remediation Plan", "Stage 3")
    _tl_close()

    col_safe, col_risky = st.columns(2)
    with col_safe:
        _html('<div class="mono-label" style="margin-bottom:0.4rem;">Safe — Auto-Applied</div>')
        for a in plan.safe:
            _html(f"""<div class="act-card">
                <div class="act-name">{a.action}<span class="badge badge-safe">safe</span></div>
                <div class="act-rationale">{a.rationale}</div>
            </div>""")

    with col_risky:
        _html('<div class="mono-label" style="margin-bottom:0.4rem;">Risky — Require Approval</div>')
        for a in plan.risky:
            bcls = "badge-ok" if decision.approved else "badge-held"
            btxt = "approved" if decision.approved else "held"
            _html(f"""<div class="act-card">
                <div class="act-name">{a.action}<span class="badge {bcls}">{btxt}</span></div>
                <div class="act-rationale">{a.rationale}</div>
            </div>""")

    # Approval gate
    gate_cls = "approved" if decision.approved else "held"
    status_label = "APPROVED" if decision.approved else "HELD"
    node_cls = "pass" if decision.approved else "held"
    _tl_open(4, "Approval Gate", "Stage 4 — Human-in-the-Loop", node_cls)
    _html(f"""<div class="gate-panel {gate_cls}">
        <div class="gate-status {gate_cls}">{status_label}</div>
        <div class="gate-detail">{decision.approver} — {decision.note}</div>
    </div>""")
    _tl_close()

    if st.session_state.get("voice_enabled") and diagnosis is not None and voice.available():
        if st.button("SPEAK DIAGNOSIS"):
            voice.speak(voice.approval_prompt(diagnosis.root_cause, len(plan.risky)))


def _render_verification(v) -> None:
    node_cls = "pass" if v.recovered else "held"
    rec_color = "green" if v.recovered else "red"
    rec_border = "green-border" if v.recovered else "accent-border"
    _tl_open(5, "Verification", "Stage 5", node_cls)
    _html(f"""<div class="m-row">
        {_m("Recovered", "YES" if v.recovered else "NO", rec_color, "lg", rec_border)}
        {_m(v.metric_name, f"{v.observed_value}", "", "", "accent-border")}
        {_m("Threshold", f"{v.threshold}", "", "", "accent-border")}
    </div>""")
    _html(f'<div class="mono-label" style="margin-top:0.35rem;">{v.note}</div>')
    _tl_close()


def _render_postmortem(p) -> None:
    _tl_open(6, "Postmortem", "Stage 6")
    _html(f'<div style="font-size:0.85rem; color:var(--fg-2); line-height:1.55; margin:0.3rem 0;">{p.summary}</div>')
    _tl_close()

    with st.expander("TIMELINE"):
        _html("".join(
            f'<div class="tl-entry"><div class="tl-entry-dot"></div>{item}</div>'
            for item in p.timeline
        ))

    with st.expander("ACTIONS & FOLLOW-UPS"):
        _html('<div class="mono-label" style="margin-bottom:0.3rem;">Actions Taken</div>')
        for a in p.actions_taken:
            _html(f'<div class="tl-entry"><div class="tl-entry-dot"></div>{a}</div>')
        _html('<div class="mono-label" style="margin:0.6rem 0 0.3rem 0;">Follow-Ups</div>')
        for f in p.follow_ups:
            _html(f'<div class="tl-entry"><div class="tl-entry-dot"></div>{f}</div>')


def _render_timeline(result, chaos_config) -> None:
    _render_triage(result.triage)
    _render_diagnosis(result.diagnosis, chaos_config)
    _render_remediation(result.remediation, result.approval, result.diagnosis)
    _render_verification(result.verification)
    _render_postmortem(result.postmortem)


def _render_audit(run_id: str) -> None:
    events = audit.get_run(run_id)
    with st.expander(f"AUDIT LOG — {len(events)} EVENTS"):
        for e in events:
            _html(f"""<div class="aud-row">
                <span class="aud-time">{e['created_at'][:19]}</span>
                <span class="aud-stage">{e['stage']}</span>
            </div>""")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def _incident_response_tab(incident_map: dict) -> None:
    result = st.session_state.get("result")
    is_demo = False
    if result is None:
        result = _load_demo_result()
        is_demo = result is not None
    if result is None:
        _html("""<div class="empty">
            <div class="empty-title">No incident loaded</div>
            <div class="empty-hint">Select an incident in the sidebar and press Run</div>
        </div>""")
        return

    chaos_config = result.chaos_config
    title = incident_map.get(result.incident_id, result.incident_id)

    _html(f'<div class="sec-header">{title}</div>')
    _html(f'<div class="sec-sub">Run <code>{result.run_id[:12]}</code></div>')
    _html('<div style="height:1rem;"></div>')

    if is_demo:
        _html("""<div class="demo-bar">
            <div class="mono-label">Pre-Loaded Example</div>
            <div style="font-size:0.8rem; color:var(--fg-2); margin-top:0.15rem;">
                A prior run shown instantly. Click <strong>RUN INCIDENT</strong> to execute a fresh one.
            </div>
        </div>""")

    if chaos_config:
        bits = []
        if chaos_config.get("disable_sources"):
            bits.append("sources disabled: <strong>" + ", ".join(chaos_config["disable_sources"]) + "</strong>")
        if chaos_config.get("break_primary_model"):
            bits.append("primary model broken — gateway failing over")
        _html(f"""<div class="chaos-bar">
            <div class="mono-label">Chaos Active</div>
            <div class="detail">{"&ensp;·&ensp;".join(bits)}</div>
        </div>""")

    _render_timeline(result, chaos_config)
    _render_audit(result.run_id)


def _score_color(val: float, threshold: float = 0.7) -> str:
    if val >= threshold:
        return "eval-pass"
    if val >= 0.4:
        return "eval-mid"
    return "eval-fail"


def _evaluation_tab() -> None:
    _html('<div class="sec-header">Evaluation</div>')
    _html("""<div class="sec-sub" style="margin-bottom:1.25rem;">
        Measured accuracy vs labeled ground truth across all 5 incidents.
        No chaos, auto-approve. Agents never see ground truth.
    </div>""")

    if st.button("RUN EVALUATION — ALL 5 INCIDENTS", type="primary"):
        with st.spinner("Scoring all incidents against ground truth..."):
            st.session_state["eval"] = evaluation.evaluate_all()

    summary = st.session_state.get("eval") or evaluation.get_latest_eval()
    if not summary:
        _html("""<div class="empty" style="margin-top:1.25rem;">
            <div class="empty-title">No evaluation run yet</div>
            <div class="empty-hint">Click above to score all 5 incidents</div>
        </div>""")
        return

    agg = summary["aggregate"]

    # Aggregate metrics
    sev_c = "green" if agg["severity_accuracy"] >= 0.8 else "amber"
    ev_c = "green" if agg["mean_evidence_recall"] >= 0.7 else "amber"
    rem_c = "green" if agg["mean_remediation_overlap"] >= 0.7 else "amber"
    rec_c = "green" if agg["recovery_rate"] >= 0.8 else "amber"
    sev_b = "green-border" if agg["severity_accuracy"] >= 0.8 else "amber-border"
    ev_b = "green-border" if agg["mean_evidence_recall"] >= 0.7 else "amber-border"
    rem_b = "green-border" if agg["mean_remediation_overlap"] >= 0.7 else "amber-border"
    rec_b = "green-border" if agg["recovery_rate"] >= 0.8 else "amber-border"

    _html(f"""<div class="m-row" style="margin:1.25rem 0;">
        {_m("Severity Accuracy", f"{agg['severity_accuracy']:.0%}", sev_c, "lg", sev_b)}
        {_m("Evidence Recall", f"{agg['mean_evidence_recall']:.0%}", ev_c, "lg", ev_b)}
        {_m("Remediation Overlap", f"{agg['mean_remediation_overlap']:.0%}", rem_c, "lg", rem_b)}
        {_m("Recovery Rate", f"{agg['recovery_rate']:.0%}", rec_c, "lg", rec_b)}
    </div>""")

    # Per-incident table
    _html("""<div class="eval-row eval-row-header">
        <div class="eval-cell">Incident</div>
        <div class="eval-cell">Severity</div>
        <div class="eval-cell">Evidence</div>
        <div class="eval-cell">Remediation</div>
        <div class="eval-cell">Recovered</div>
    </div>""")

    for inc in summary["by_incident"]:
        sev_cls = "eval-pass" if inc["severity_correct"] else "eval-fail"
        ev_cls = _score_color(inc["evidence_recall"])
        rem_cls = _score_color(inc["remediation_overlap"])
        rec_cls = "eval-pass" if inc["recovered"] else "eval-fail"
        _html(f"""<div class="eval-row">
            <div class="eval-cell name">{inc['incident_id']}</div>
            <div class="eval-cell {sev_cls}">{"PASS" if inc['severity_correct'] else "FAIL"}</div>
            <div class="eval-cell {ev_cls}">{inc['evidence_recall']:.0%}</div>
            <div class="eval-cell {rem_cls}">{inc['remediation_overlap']:.0%}</div>
            <div class="eval-cell {rec_cls}">{"YES" if inc['recovered'] else "NO"}</div>
        </div>""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="RescueOps", page_icon="🔥", layout="wide")
    _html(_CSS)
    audit.init_db()

    # Hero
    _html("""<div class="ro-hero">
        <div class="ro-hero-title">RESCUE<span class="accent">OPS</span></div>
        <div class="ro-hero-sub">
            <span><span class="dot"></span>CrewAI Agents</span>
            <span><span class="dot"></span>TrueFoundry Gateway</span>
            <span><span class="dot"></span>Human-in-the-Loop</span>
        </div>
    </div>""")

    incident_list = incidents.load_incidents()
    incident_map = {inc["id"]: inc.get("title", inc["id"]) for inc in incident_list}

    # Sidebar
    with st.sidebar:
        _html('<div class="sb-brand">RESCUE<span class="accent">OPS</span></div>')
        _html('<div class="mono-label">Mission Control</div>')

        _html('<div class="sb-section">Incident</div>')
        incident_id = st.selectbox(
            "Select incident",
            options=[inc["id"] for inc in incident_list],
            format_func=lambda i: incident_map[i],
            label_visibility="collapsed",
        )

        _html('<div class="sb-section">Chaos Console</div>')
        disabled = [s for s in TELEMETRY_SOURCES if st.checkbox(f"Disable {s}", key=f"chaos_{s}")]
        break_model = st.checkbox("Break primary model")

        _html('<div class="sb-section">Governance</div>')
        approve_risky = st.radio(
            "Risky actions",
            options=[False, True],
            format_func=lambda v: "APPROVE — allow risky" if v else "DENY — hold risky",
            index=0,
            label_visibility="collapsed",
        )
        st.session_state["voice_enabled"] = st.checkbox("Voice narration", value=False)

        _html('<div style="height:0.75rem;"></div>')
        if st.button("RUN INCIDENT", type="primary", use_container_width=True):
            chaos_config = build_chaos_config(disabled, break_model)
            callback = make_approval_callback(approve_risky)
            with st.spinner("Running pipeline..."):
                st.session_state["result"] = run_incident(incident_id, chaos_config, callback)

        _html("""<div class="prod-path">
            <strong>Path to production:</strong><br>
            Live telemetry sources · TrueFoundry guardrails ·
            Approval + audit controls · Gateway failover
        </div>""")

    # Tabs
    tab_run, tab_eval = st.tabs(["INCIDENT RESPONSE", "EVALUATION"])
    with tab_run:
        _incident_response_tab(incident_map)
    with tab_eval:
        _evaluation_tab()


if __name__ == "__main__":
    main()
