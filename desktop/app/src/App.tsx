// desktop/app/src/App.tsx
// Desktop UI (Tauri + React) with Connection panel, Strategies Catalog (presets + start), richer Status/Logs,
// and friendly UI for Settings, Bot Status, and Activity Log.
// API base comes from VITE_API_BASE (defaults to http://127.0.0.1:8000)

import { useEffect, useRef, useState } from 'react';
import { createPortal } from "react-dom";

// ---------- Config ----------
const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const API_BASE =
  (import.meta as any)?.env?.VITE_API_BASE?.toString() || DEFAULT_API_BASE;

// ---------- Styles ----------
const css = `
:root {
  --bg:#0b0d11; --panel:#12161c; --card:#161b22; --muted:#94a3b8; --text:#e5e7eb; --text-dim:#cbd5e1;
  --brand:#7c3aed; --brand2:#06b6d4; --red:#ef4444; --amber:#f59e0b; --green:#22c55e; --border:#1f2937; --hover:#0f172a;
}
*{box-sizing:border-box} html,body,#root{height:100%}
body{margin:0;background:var(--bg);
 color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}
.app{max-width:1180px;margin:0 auto;padding:28px 20px 28px}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.title{display:flex;align-items:center;gap:12px}
.badge{font-size:12px;color:var(--text-dim);background:linear-gradient(135deg, rgba(124,58,237,.25), rgba(6,182,212,.25));
  border:1px solid rgba(124,58,237,.35);padding:4px 8px;border-radius:999px}
.badge.good{color:var(--green);border-color:rgba(16,185,129,.45);background:linear-gradient(135deg, rgba(16,185,129,.18), rgba(16,185,129,.06))}
.badge.bad{color:var(--red);border-color:rgba(239,68,68,.45);background:linear-gradient(135deg, rgba(239,68,68,.18), rgba(239,68,68,.06))}
.tabs{display:flex;gap:8px;margin:8px 0 18px}
.tab{padding:8px 12px;border-radius:8px;background:var(--panel);color:var(--text-dim);
  border:1px solid var(--border);cursor:pointer;transition:.18s ease}
.tab:hover{background:var(--hover)}
.tab.active{color:var(--text);background:linear-gradient(180deg, rgba(124,58,237,.25), rgba(6,182,212,.25));border-color:rgba(124,58,237,.45)}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap: 8px}
@media (max-width:900px){.grid-3{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}
.card-lg{padding:18px}
.card h3{margin:0 0 6px;font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.card .value{font-size:20px;font-weight:600}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stack{display:grid;gap: 8px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:8px 12px;border-radius:10px;border:1px solid var(--border);
  background:#0e1320;color:var(--text);cursor:pointer;transition:transform .04s ease, background .18s ease;user-select:none}
.btn[disabled]{opacity:.55;cursor:not-allowed}
.btn:hover{background:var(--hover)} .btn:active{transform:translateY(1px)}
.btn.brand{background:linear-gradient(180deg, rgba(124,58,237,.5), rgba(6,182,212,.4));border-color:rgba(124,58,237,.5)}
.btn.red{background:linear-gradient(180deg, rgba(239,68,68,.25), rgba(239,68,68,.15));border-color:rgba(239,68,68,.4)}
.btn.amber{background:linear-gradient(180deg, rgba(245,158,11,.25), rgba(245,158,11,.15));border-color:rgba(245,158,11,.4)}
.input,.select{width:100%;padding:8px 10px;border-radius:8px;background:#0c111b;color:var(--text);border:1px solid var(--border);outline:none;transition:border-color .18s}
.input:focus,.select:focus{border-color:rgba(124,58,237,.6)}
/* Symbol search: consistent across tables/logs */
.input.search{
  padding-left: 28px;                   /* room for icon */
  background-image: url('data:image/svg+xml;utf8,<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="11" cy="11" r="7" stroke="%23cbd5e1" stroke-width="2"/><path d="M20 20l-3.5-3.5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round"/></svg>');
  background-repeat:no-repeat;
  background-position: 8px 50%;
  background-size: 16px 16px;
}
.input.search:focus{ border-color: var(--border); box-shadow:none; }

.select {
  -webkit-appearance: none;
  appearance: none;
  background-image: url('data:image/svg+xml;utf8,<svg width="12" height="12" viewBox="0 0 20 20" fill="%23cbd5e1" xmlns="http://www.w3.org/2000/svg"><path d="M5.25 7.5l4.75 5 4.75-5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
  background-repeat: no-repeat;
  background-position: right 8px center;
  background-size: 12px 12px;
  padding-right: 28px;
}
.select::-ms-expand { display: none; }

/* Subtle motion */
@keyframes fadeSlide {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.panel { animation: fadeSlide .18s ease both; }
.btn { transition: transform .06s ease, box-shadow .18s ease, background .18s ease; }
.btn:hover { box-shadow: 0 6px 18px rgba(0,0,0,.24); }
.btn:active { transform: translateY(1px) scale(.99); }

/* Scrollbars (WebKit) */
.table-wrap::-webkit-scrollbar, .menu::-webkit-scrollbar { width: 8px; height: 8px; }
.table-wrap::-webkit-scrollbar-thumb, .menu::-webkit-scrollbar-thumb {
  background: rgba(124,58,237,.35);
  border-radius: 10px;
}
.table-wrap::-webkit-scrollbar-thumb:hover, .menu::-webkit-scrollbar-thumb:hover {
  background: rgba(124,58,237,.6);
}

/* Custom dropdown (NiceSelect / NiceCombobox) */
.custom-select { position: relative; display: inline-block; }
.custom-trigger {
  width: 100%;
  min-height: 34px;
  background: #0c111b;
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 10px;
  padding: 8px 28px 8px 10px;
  text-align: left;
  cursor: pointer;
}
.custom-trigger:hover { background: var(--hover); }
.custom-trigger:after {
  content: "";
  position: absolute; right: 10px; top: 50%; width: 12px; height: 12px; transform: translateY(-50%);
  background-image: url('data:image/svg+xml;utf8,<svg width="12" height="12" viewBox="0 0 20 20" fill="%23cbd5e1" xmlns="http://www.w3.org/2000/svg"><path d="M5.25 7.5l4.75 5 4.75-5" stroke="%23cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
  background-size: 12px 12px; background-repeat: no-repeat;
}
.menu {
  position: absolute; left: 0; right: 0; z-index: 50; margin-top: 6px;
  background: rgba(16,20,31,.98);
  border: 1px solid var(--border); border-radius: 12px; padding: 6px;
  box-shadow: 0 16px 40px rgba(0,0,0,.35);
  max-height: 260px; overflow: auto; animation: fadeSlide .16s ease both;
  backdrop-filter: blur(6px);
}
.menu .item {
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
}
/* slight vertical gap between items */
.menu .item + .item { margin-top: 6px; }
.menu .item:hover, .menu .item.active {
  background: rgba(124,58,237,.18);
}
/* Combobox search input inside menu */
.menu .search {
  width: 100%; margin: 4px 0 6px; padding: 8px 10px;
  background: #0c111b; border: 1px solid var(--border); border-radius: 8px; color: var(--text);
}

.label{font-size:12px;color:var(--muted);margin-bottom:6px}
.form-row{display:grid;gap:12px;grid-template-columns:repeat(3,1fr)} @media (max-width:900px){.form-row{grid-template-columns:1fr}}
.table-wrap{overflow:auto;border-radius:10px}
table{width:100%;border-collapse:collapse;background:var(--panel)}
th,td{padding:8px 10px;border-top:1px solid var(--border)} th{text-align:left;font-size:12px;color:var(--muted);background:#0f1420;position:sticky;top:0;z-index:1}
tr:hover td{background:rgba(124,58,237,.08)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap: 8px} @media (max-width:900px){.kpis{grid-template-columns:1fr}}
.help{color:var(--muted);font-size:12px}
.toast{position:fixed;right:16px;bottom:16px;padding:10px 12px;border-radius:10px;background:#0e1320;border:1px solid var(--border);color:var(--text);box-shadow:0 10px 30px rgba(0,0,0,.35);max-width:360px}
small.code{font-family:ui-monospace, SFMono-Regular, Menlo, monospace;background:rgba(124,58,237,.18);padding:2px 6px;border-radius:6px}

.indicator{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320}
.dot{width:8px;height:8px;border-radius:50%}
.dot.green{background:var(--green)} .dot.red{background:var(--red)}
.header-quick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;min-width:320px}

.sticky-controls{position: sticky; top: 0; background: #0f1420; padding: 6px 0; z-index: 2; border-bottom: 1px solid var(--border);}
.activity .sticky-controls{ background: transparent; border-bottom: 0; }
.note{font-size:12px;color:var(--muted)}

/* indicator font tweak */
.indicator{font-size:12px;font-weight:600}

.header, .title, .header-quick{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial }
.panel h2{ margin:0 0 6px; font-size:15px; color:var(--text); text-transform:uppercase; letter-spacing:.06em }
.title-lg{ font-size:20px; }

.grid-2{display:grid;grid-template-columns:2fr 1fr;gap: 8px}
@media (max-width:980px){.grid-2{grid-template-columns:1fr}}
.panel.thick{padding:22px}
/* Autopilot switch (solid color) */
.switch-lg{position:relative;width:60px;height:30px;border-radius:999px;background:#334155;border:1px solid #475569;display:inline-flex;align-items:center;transition:background .18s ease,border-color .18s ease}
.switch-lg .thumb{position:absolute;left:3px;width:24px;height:24px;border-radius:999px;background:#0b1220;box-shadow:0 6px 16px rgba(0,0,0,.35);transition:transform .2s ease, background .2s ease}
.switch-lg.on{background:#22a6f2;border-color:#22a6f2}
.switch-lg.on .thumb{transform:translateX(30px);background:#ffffff}
.help.strong{font-weight:600;color:var(--text)}

/* Align with KPI 3-column track; panels span to align edges */
.panels3{display:grid;grid-template-columns:repeat(3, minmax(0,1fr));gap: 8px}
.panels3 .span-2{grid-column:span 2 / span 2}
@media (max-width:980px){.panels3{grid-template-columns:1fr}.panels3 .span-2{grid-column:auto}}

.panels2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap: 8px}
@media (max-width:980px){.panels2{grid-template-columns:1fr}}

/* Fixed gradient overlay to avoid scroll seams */
.bgfx{position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(139,92,246,.12), transparent 60%),
    radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,.10), transparent 60%);

/* --- UI tweaks (0826) --- */
.health { display:grid; grid-template-columns:auto 1fr; grid-template-areas:"top metrics"; gap:12px 18px; align-items:start; }
.health .health-top { grid-area:top; display:flex; align-items:center; gap:10px; margin-top:14px; }
.health .health-badge { font-size: 18px; padding: 9px 16px; border-radius: 999px; }
.health .health-metrics { grid-area:metrics; display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:10px 22px; align-items:start; justify-self:end; align-self:start; text-align:left; }
.health .stat { font-size:13px; color:var(--muted); letter-spacing:.02em; }

/* Split card (top/bottom halves) */
.split-card { display: flex; flex-direction: column; }
.split-card .section { flex: 1 1 0; display: flex; flex-direction: column; justify-content: center; }
.split-card .section + .section { margin-top: 8px; padding-top: 8px; }
.split-card .section.top{padding-bottom:6px padding-top:10px}
.split-card .section.bottom{padding-top:32px}
}
/* --- Autopilot Health layout --- */
.health { display:grid; grid-template-columns:auto 1fr; grid-template-areas:"top metrics"; gap:12px 18px; align-items:start; }
.health .health-top { grid-area:top; display:flex; align-items:center; gap:10px; margin-top:14px; }
.health .health-metrics { grid-area:metrics; display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px 16px; align-items:start; justify-self:end; align-self:start; text-align:left; }
.health .stat { font-size:13px; color:var(--muted); letter-spacing:.02em; }
/* --- end health --- */

.split-card .section.top .row{ margin-top:6px }

/* === Advanced layout & widgets (added) === */
.panel.no-bottom-line{border-bottom:0}

/* Compact variant for tighter cards */
.panel.compact{padding:12px}
.panel.compact h2{margin-bottom:6px}
.panel.compact .form-row{gap:8px}
.panel.compact .label{margin-bottom:4px}
.panel.compact .input,.panel.compact .select,.panel.compact .custom-trigger{padding:6px 8px}
.panel.compact .custom-trigger{min-height:30px}
.panel.compact .row{gap:8px}
.prefs-grid{margin-top:12px}

.panels2.vsplit{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:12px}
.panels2.vsplit > .panel{min-height:0}
@media (max-width:980px){.panels2.vsplit{grid-template-columns:1fr;grid-template-rows:auto}}

.strat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap: 8px}
@media (max-width:980px){.strat-grid{grid-template-columns:1fr}}
.strat{border:1px solid var(--border);border-radius:12px;background:#151d26;
  padding:12px; display:flex; align-items:flex-start; gap:12px; cursor:pointer; transition:transform .06s ease, border-color .18s ease; min-height:74px;}
.strat:hover{ box-shadow:none; }

/* === Modern tables & utilities === */
.table-modern{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}
.table-modern thead th{
  position:sticky; top:0; z-index:1;
  background:#0f1420;                  /* solid (no gradient) */
  color:var(--muted);                   /* same tone as KPI titles */
  font-weight:700; font-size:12px; letter-spacing:.05em;
  text-transform:uppercase;
  border-bottom:1px solid var(--border);
}

.table-modern thead th.num{ text-align:right; }

.table-modern th, .table-modern td{
  padding:10px 12px;
  vertical-align:middle;
  border-bottom:1px solid var(--border);
}

.table-modern thead th.num{ text-align:right; }

.table-modern tbody tr:hover{ background:var(--hover); }
.table-modern .small{ font-size:12px; opacity:.9; }
.mono{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums; }
.num { text-align:right; font-variant-numeric:tabular-nums; }

/* table containers share the same, subtle scrollbar as page */
.table-wrap{ overflow:auto; border-radius:0; }
.table-wrap::-webkit-scrollbar{ height:10px; width:10px; }
.table-wrap::-webkit-scrollbar-track{ background:#0c111b; border-radius:8px; }
.table-wrap::-webkit-scrollbar-thumb{ background:#1f2937; border-radius:8px; }
.table-wrap::-webkit-scrollbar-thumb:hover{ background:#2a3446; }

/* Text-only status (no dot/pill) */
.status{
  display:inline-flex; flex-direction:column; align-items:flex-start;
  font-size:12px; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
  color:var(--muted);
}
.status::after{ content:""; height:2px; width:100%; border-radius:2px; margin-top:2px; background:currentColor; opacity:.24; }
.status.good{ color:var(--green); }
.status.bad { color:var(--red);   }
.status.warn{ color:var(--amber); }

/* truncation helper for long ids */
.truncate{ max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.strat.on{ border-color: rgba(16,185,129,.45); box-shadow:none; background: rgba(16,185,129,.05); }
.strat .dot{ width:10px; height:10px; margin-top:3px; }
.strat .info{ flex:1 1 auto; }
.strat .name{ font-weight:700; margin-bottom:2px; }
.strat .desc{ font-size:12px; color:var(--muted); }
.btn-ghost{ background:linear-gradient(180deg, rgba(124,58,237,.14), rgba(6,182,212,.10)); border:1px solid rgba(124,58,237,.45); padding:6px 10px; border-radius:8px; }

.pref-list{display:grid;gap:8px}
.pref-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.pref-row .k{font-size:12px;color:var(--muted)}
.delta{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320;display:inline-flex;align-items:center;gap:6px}
.delta.up{color:var(--green);border-color:rgba(16,185,129,.45);background:rgba(16,185,129,.10)}
.delta.down{color:var(--red);border-color:rgba(239,68,68,.45);background:rgba(239,68,68,.10)}
.delta.neutral{color:var(--muted);opacity:.9}
.pref-row .val{font-size:12px;color:var(--muted);text-align:right;white-space:nowrap}

/* Current Stats layout */
.statgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
@media (max-width:980px){.statgrid{grid-template-columns:1fr}}
.statcard{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:10px;border:1px solid var(--border);border-radius:10px;background:#0e1320}
.statcard .label{font-size:12px;color:var(--muted)}
.statcard .value{font-weight:700;font-variant-numeric:tabular-nums}
.statcard .meta{display:flex;align-items:center;gap:8px}
.delta{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320;display:inline-flex;align-items:center;gap:6px}
.delta.up{color:var(--green);border-color:rgba(16,185,129,.45);background:rgba(16,185,129,.10)}
.delta.down{color:var(--red);border-color:rgba(239,68,68,.45);background:rgba(239,68,68,.10)}
.delta.neutral{color:var(--muted);opacity:.9}


/* === Current Stats (list view, fewer boxes) === */
.statlist{display:block}
.statrow{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:10px;padding:6px 0;border-top:1px solid var(--border)}
.statrow:first-child{border-top:0;padding-top:0}
.statrow .k{font-size:12px;color:var(--muted)}
.statrow .v{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.statrow .delta{white-space:nowrap}
/* === Numeric steppers (custom) === */
/* Hide native spinners */
.input[type=number]::-webkit-outer-spin-button,
.input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.input[type=number]{ -moz-appearance: textfield; }
/* Wrapper that provides compact up/down arrows with no background */
.num{ position: relative; }
.num > .input{ padding-right: 28px; text-align:left; } /* room for arrows */
.num .spin{ position:absolute; right:4px; top:50%; transform:translateY(-50%); display:flex; flex-direction:column; gap:0; align-items:center; }
.num .spin button{ width:16px; height:14px; display:flex; align-items:center; justify-content:center; border:0; background:transparent; padding:0; cursor:pointer; color:var(--muted); line-height:1; }
.num .spin button:hover{ filter: brightness(1.08); }
.num .spin button:active{ transform: translateY(1px); }
.num .spin button + button{ margin-top:-10px; }
.num .spin svg{ width:12px; height:12px; display:block; }

`;

// ---------- Types ----------
type Mode = "automatic" | "manual";
type RiskConfig = {
  enabled?: boolean;
  max_usd_per_trade?: number;
  max_open_positions?: number;
  max_daily_loss_usd?: number;
  trading_hours_pt?: { start: string; end: string };
  flatten_before_close_min?: number;
};

type StrategyKind = "ma-crossover" | "ma-grid";

// ---------- Small helpers ----------
function useLocalStorage<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch { return initial; }
  });

  // Broadcast local changes and persist
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch {}
    // Notify other hook instances in this document
    try { window.dispatchEvent(new CustomEvent(`ls:${key}`, { detail: v as any })); } catch {}
  }, [key, v]);

  // Listen for updates from other instances (same tab) and from other tabs
  useEffect(() => {
    const onCustom = (e: Event) => {
      const ce = e as CustomEvent;
      const next = ce?.detail as T;
      // Avoid redundant state updates
      if (JSON.stringify(next) !== JSON.stringify(v)) {
        setV(next);
      }
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== key) return;
      try {
        const next = e.newValue ? (JSON.parse(e.newValue) as T) : initial;
        if (JSON.stringify(next) !== JSON.stringify(v)) setV(next);
      } catch {}
    };
    try { window.addEventListener(`ls:${key}` as any, onCustom as any); } catch {}
    try { window.addEventListener('storage', onStorage); } catch {}
    return () => {
      try { window.removeEventListener(`ls:${key}` as any, onCustom as any); } catch {}
      try { window.removeEventListener('storage', onStorage); } catch {}
    };
  }, [key, v, initial]);

  return [v, setV] as const;
}

async function askConfirm(message: string) {
  const g = (window as any);
  try {
    if (g.__TAURI__?.dialog?.confirm) {
      return await g.__TAURI__.dialog.confirm(message, { title: "Confirm", type: "warning" });
    }
  } catch {}
  return window.confirm(message);
}

async function GET<T>(path: string, params?: Record<string, any>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const r = await fetch(url, { credentials: "omit" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}
async function SEND<T>(path: string, body?: any, method: "POST" | "PUT" | "PATCH" | "DELETE" = "POST"): Promise<T> {
  const r = await fetch(new URL(path, API_BASE), {
    method, headers: { "Content-Type": "application/json" },
    body: method==="DELETE" ? undefined : (body ? JSON.stringify(body) : undefined),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}
const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));
const nowIso = () => new Date().toLocaleTimeString();
const shortId = (s?: string) => {
  const id = String(s || '');
  return id.length > 14 ? `${id.slice(0,8)}…${id.slice(-4)}` : id;
};

// Text-only status label used in tables
function statusTag(status?: string) {
  const s = String(status ?? '').toLowerCase();
  let cls = "status";
  if (["filled","done","completed","executed"].includes(s)) cls += " good";
  else if (["canceled","cancelled","rejected","expired","failed","error"].includes(s)) cls += " bad";
  else if (["open","pending","working","new","partially_filled","partial","accepted"].includes(s)) cls += " warn";
  return <span className={cls}>{status ?? ""}</span>;
}

  // ---------- API bindings ----------
  const api = {
  // connection
  connect: (host: string, port: number, client_id: number) => SEND("/connect", { host, port, client_id }),
  accountsActive: () => GET<{ account_id: string | null; trd_env: string | null }>("/accounts/active"),
  selectAccount: (account_id: string, trd_env: "SIMULATE" | "REAL") =>
    SEND("/accounts/select", { account_id, trd_env }),

  // session helpers
  sessionStatus: () => GET<{ saved: any; connected: boolean; active_account: any }>("/session/status"),
  sessionSave: (host: string, port: number, account_id?: string, trd_env?: string) =>
    SEND("/session/save", { host, port, account_id, trd_env }),
  sessionClear: () => SEND("/session/clear", {}),

  // bot core
  getBotMode: () => GET<{ mode: Mode }>("/bot/mode"),
  setBotMode: (mode: Mode) => SEND<{ mode: Mode }>("/bot/mode", { mode }, "PUT"),
  getRiskConfig: () => GET<RiskConfig>("/risk/config"),
  putRiskConfig: (cfg: RiskConfig) => SEND<RiskConfig>("/risk/config", cfg, "PUT"),
  getRiskStatus: () => GET<{ ok: boolean; config: RiskConfig; open_positions: number | null }>("/risk/status"),
  getPnlToday: () => GET<{ date: string; realized_pnl: number }>("/pnl/today"),
  getAccountAssets: () => GET<{ mode:string; equity?: number|null; bp?: number|null; cash?: number|null }>("/accounts/assets"),

  flattenAll: (symbols?: string[]) => SEND("/positions/flatten", symbols?.length ? { symbols } : {}),
  listStrategies: () => GET<Array<{ id: number; name: string; active: boolean; symbol: string }>>("/automation/strategies"),
  stopStrategy: (id: number) => SEND(`/automation/stop/${id}`),

  getActionLogs: (q: { limit?: number; symbol?: string; since_hours?: number }) => GET<any[]>("/logs/actions", q),
  backtestMA: (payload: any) => SEND("/backtest/ma-crossover", payload),

  // strategy starters (live)
  startMA: (payload: any) => SEND("/automation/start/ma-crossover", payload),
  // startGrid: (payload: any) => SEND("/automation/start/ma-grid", payload),
  // autopilot
  autopilotStatus: () => GET("/autopilot/status"),
  autopilotEnable: (on: boolean) => SEND("/autopilot/enable", { on }),
  autopilotPreview: () => SEND("/autopilot/preview", {}),
  autopilotLogs: (limit: number) => GET<any[]>("/autopilot/logs", { limit }),
  autopilotContext: () => GET("/autopilot/context"),
  autopilotLastOutput: () => GET("/autopilot/last_output"),

  // autopilot prefs/style/watchlist
  getAutoPrefs: () => GET<any>("/autopilot/prefs"),
  putAutoPrefs: (prefs: any) => SEND("/autopilot/prefs", prefs, "PUT"),
  getAutoStyle: () => GET<{ raw: string; summary: string }>("/autopilot/style"),
  postAutoStyle: (text: string) => SEND<{ raw: string; summary: string }>("/autopilot/style", { text }),
  deleteAutoStyle: () => SEND<{ raw: string; summary: string }>("/autopilot/style", undefined, "DELETE"),
  // watchlist endpoints intentionally not used in UI for now
  getDiscovery: () => GET<{ enabled: boolean; only: boolean; seed: string[]; preview: string[] }>("/autopilot/discovery"),
  putDiscovery: (payload: { enabled?: boolean; only?: boolean; seed?: string[] }) => SEND("/autopilot/discovery", payload, "PUT"),
    getNewsSettings: () => GET<{ enabled: boolean; ttl_sec: number; provider?: string }>("/autopilot/news"),
    putNewsSettings: (payload: { enabled?: boolean; ttl_sec?: number; provider?: string }) => SEND("/autopilot/news", payload, "PUT"),
    getDataSettings: () => GET<{ ktype: string; bars_ttl_sec: number; deals_sync_sec: number }>("/autopilot/data"),
    putDataSettings: (payload: { ktype?: string; bars_ttl_sec?: number; deals_sync_sec?: number }) => SEND("/autopilot/data", payload, "PUT"),
    getSignalsSettings: () => GET<{ enabled: boolean; strategies: Record<string, boolean>; weights: Record<string, number> }>("/autopilot/signals"),
    putSignalsSettings: (payload: Partial<{ enabled: boolean; strategies: Record<string, boolean>; weights: Record<string, number> }>) => SEND("/autopilot/signals", payload, "PUT"),
  getExecMode: () => GET<{ mode: "sim"|"moomoo" }>("/execution/mode"),
  putExecMode: (mode: "sim"|"moomoo") => SEND("/execution/mode", { mode }, "PUT"),
  syncDealsNow: () => SEND("/sync/deals", {}),
  syncExecDeals: () => SEND("/exec/sync/deals", {}),
  getPlannerSettings: () => GET<{ min_confidence: number; top_n: number; strict_prefs: boolean }>("/autopilot/planner"),
  putPlannerSettings: (payload: { min_confidence?: number; top_n?: number; strict_prefs?: boolean }) => SEND("/autopilot/planner", payload, "PUT"),

  // execution (SIM)
  listExecOrders: (q: { symbol?: string; status?: string; limit?: number }) => GET<any[]>("/exec/orders", q),
  cancelExecOrder: (id: string) => SEND(`/exec/orders/${id}/cancel`, {}, "POST"),
  listExecFills: (q: { symbol?: string; limit?: number }) => GET<any[]>("/exec/fills", q),
  // execution (SIM) – positions
  listExecPositions: (q?: { symbol?: string; limit?: number }) => GET<any[]>("/exec/positions", q || {}),
  flattenExecPositions: (symbols?: string[]) => SEND("/exec/flatten", symbols?.length ? { symbols } : {}),


};

// ---------- Toast ----------
function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  function show(message: string, timeout = 2800) {
    setMsg(message);
    window.clearTimeout(timer.current!);
    timer.current = window.setTimeout(() => setMsg(null), timeout);
  }
  return { msg, show };
}

// ---------- App ----------
enum Tab { Settings=0, Status=1, Activity=2 }

export default function App() {
  const toast = useToast();
  const [tab, setTab] = useLocalStorage<Tab>("ui.tab", Tab.Settings);

  // Refresh signal state
  const [stratRefreshTick, setStratRefreshTick] = useState(0);

  // connection state (persist inputs)
  const [host, setHost] = useLocalStorage("conn.host", "127.0.0.1");
  const [port, setPort] = useLocalStorage("conn.port", 11111);
  const [clientId, setClientId] = useLocalStorage("conn.clientId", 1);
  const [accountId, setAccountId] = useLocalStorage("conn.accountId", "");
  const [trdEnv, setTrdEnv] = useLocalStorage<"SIMULATE"|"REAL">("conn.env", "SIMULATE");
  const [connected, setConnected] = useState(false);
  const [activeAccount, setActiveAccount] = useState<{ account_id: string | null; trd_env: string | null } | null>(null);

  // bot state
  const [mode, setMode] = useState<Mode>("manual");
  const [cfg, setCfg] = useState<RiskConfig | null>(null);
  const [riskEnabled, setRiskEnabled] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  // status
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState<any|null>(null);

  const [pnl, setPnl] = useState<number | null>(null);
  const [openPositions, setOpenPositions] = useState<number | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [autoStatus, setAutoStatus] = useState<any|null>(null);
  const [autoEvery, setAutoEvery] = useLocalStorage("auto.ms", 4000);
  const [autoAt, setAutoAt] = useState<string>("—");
  const [autoRefresh, setAutoRefresh] = useLocalStorage("status.auto", true);
  const [statusEvery, setStatusEvery] = useLocalStorage("status.ms", 5000);
  const [statusAt, setStatusAt] = useState<string>("—");

  // logs
  const [logs, setLogs] = useState<any[]>([]);
  const [logSymbol, setLogSymbol] = useLocalStorage("logs.symbol", "");
  const [logSince, setLogSince] = useLocalStorage("logs.sinceH", 24);
  const [logLimit, setLogLimit] = useLocalStorage("logs.limit", 200);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsAuto, setLogsAuto] = useLocalStorage("logs.auto", true);
  const [logsEvery, setLogsEvery] = useLocalStorage("logs.ms", 6000);
  const [logsSource, setLogsSource] = useLocalStorage<"system"|"autopilot">("logs.source", "system");
  const [logsAt, setLogsAt] = useState<string>("—");

  // execution (orders/fills)
  const [exSymbol, setExSymbol] = useLocalStorage("exec.symbol", "");
  const [exAuto, setExAuto] = useLocalStorage("exec.auto", true);
  const [exEvery, setExEvery] = useLocalStorage("exec.ms", 5000);
  const [exAt, setExAt] = useState<string>("—");
  const [orders, setOrders] = useState<any[]>([]);
  const [openOrderCount, setOpenOrderCount] = useState<number | null>(null);
  const [exposureMV, setExposureMV] = useState<number | null>(null);

  
  // preference targets (read-only for Current Stats)
  const [prefWinRate] = useLocalStorage<number>("pref.winRate", 55);
  const [prefRR] = useLocalStorage<number>("pref.rr", 1.5);
  const [prefStop] = useLocalStorage<number>("pref.stop", 1.0);
  const [prefTP] = useLocalStorage<number>("pref.tp", 2.0);
  const [prefMM] = useLocalStorage<number>("pref.mm", 1.0);
  const [prefMaxDD] = useLocalStorage<number>("pref.maxdd", 5.0);
// Bot Status live autopilot decisions
  const [statusLogs, setStatusLogs] = useState<any[]>([]);
  const [statusLogsAt, setStatusLogsAt] = useState<string>("—");

  // Explain modal for a decision
  const [explainOpen, setExplainOpen] = useState(false);
  const [explainRow, setExplainRow] = useState<any|null>(null);
  const [explainData, setExplainData] = useState<any|null>(null);

  const [exLoading, setExLoading] = useState(false);
  // positions (SIM)
  const [posSymbol, setPosSymbol] = useLocalStorage("pos.symbol", "");
  const [posAuto, setPosAuto] = useLocalStorage("pos.auto", true);
  const [posEvery, setPosEvery] = useLocalStorage("pos.ms", 5000);
  const [posAt, setPosAt] = useState<string>("—");
  const [positions, setPositions] = useState<any[]>([]);
  const posReqId = useRef(0);

  const [posLoading, setPosLoading] = useState(false);



  // initial: load session + mode + risk
  useEffect(() => {
    (async () => {
      try {
        const st = await api.sessionStatus();
        if (st.connected) {
          setConnected(true);
          setActiveAccount(st.active_account || null);
        } else if (st.saved?.host && st.saved?.port) {
          try {
            await api.connect(String(st.saved.host), Number(st.saved.port), Number(clientId));
            if (st.saved?.account_id && st.saved?.trd_env) {
              try { await api.selectAccount(String(st.saved.account_id), st.saved.trd_env); } catch {}
            }
            const st2 = await api.sessionStatus();
            setConnected(!!st2.connected);
            setActiveAccount(st2.active_account || null);
          } catch {}
        }
        if (st.saved?.host) setHost(String(st.saved.host));
        if (st.saved?.port) setPort(Number(st.saved.port));
        if (st.saved?.account_id) setAccountId(String(st.saved.account_id));
        if (st.saved?.trd_env) setTrdEnv((st.saved.trd_env as "SIMULATE" | "REAL") || "SIMULATE");
      } catch {}
      try { setMode((await api.getBotMode()).mode); } catch {}
      try { setCfg(await api.getRiskConfig()); } catch {}
      await refreshStatus(false);
      await refreshLogs(false);
      await refreshExec(false);
      await refreshPositions(false);
    })();
// eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!autoRefresh || tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshStatus(false), statusEvery);
    const idAuto = window.setInterval(() => refreshAutoStatus(), autoEvery);
    return () => { window.clearInterval(id); window.clearInterval(idAuto); };
  }, [autoRefresh, tab, statusEvery, autoEvery]);

  
  useEffect(() => {
    if (tab !== Tab.Status) return;
    const pull = async () => {
      try {
        const ls = await api.autopilotLogs(100);
        setStatusLogs(ls || []);
        setStatusLogsAt(nowIso());
      } catch {}
    };
    pull();
    const id = window.setInterval(pull, 2500);
    return () => window.clearInterval(id);
  }, [tab]);
useEffect(() => {
    if (tab !== Tab.Activity) return;
    const id = window.setInterval(() => refreshLogs(false), logsEvery);
    return () => window.clearInterval(id);
  }, [tab, logsEvery, logSymbol, logSince, logLimit]);

  useEffect(() => {
    if (tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshExec(false), exEvery);
    return () => window.clearInterval(id);
  }, [tab, exEvery, exSymbol]);
  useEffect(() => {
    if (tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshPositions(false), posEvery);
    return () => window.clearInterval(id);
  }, [tab, posEvery, posSymbol]);



  
  async function refreshStatus(show = true) {
    try {
      setStatusLoading(true);
      // 1) Realized PnL (today)
      try {
        const p = await api.getPnlToday();
        setPnl(p?.realized_pnl ?? null);
      } catch {}
      // 2) Positions -> count + exposure MV
      try {
        const pos = await api.listExecPositions({});
        const count = Array.isArray(pos) ? pos.length : 0;
        const mv = Array.isArray(pos)
          ? pos.reduce((acc:number, r:any) => acc + Math.abs(Number(r?.mv || 0)), 0)
          : null;
        setOpenPositions(count || 0);
        setExposureMV(mv == null ? null : Number(Number(mv).toFixed(2)));
      } catch {}
      // 3) Orders pending
      try {
        const ords = await api.listExecOrders({});
        const pending = Array.isArray(ords)
          ? ords.filter((o:any) => {
              const s = String(o?.status || "").toLowerCase();
              return !["filled", "cancelled", "canceled", "rejected", "done", "completed"].includes(s);
            }).length
          : 0;
        setOpenOrderCount(pending);
      } catch {}
      setStatusAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Status refresh failed: ${brief(e)}`);
    } finally {
      setStatusLoading(false);
    }
  }

  async function refreshLogs(show = true) {
    try {
      setLogsLoading(true);
      if (logsSource === "autopilot") {
        const ls = await api.autopilotLogs(Math.max(10, Number(logLimit) || 100));
        setLogs(ls || []);
      } else {
        const q: any = { limit: Math.max(10, Number(logLimit) || 100) };
        if (logSymbol) q.symbol = logSymbol;
        if (logSince) q.since_hours = Number(logSince) || 24;
        const ls = await api.getActionLogs(q);
        setLogs(ls || []);
      }
      setLogsAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Logs refresh failed: ${brief(e)}`);
    } finally {
      setLogsLoading(false);
    }
  }

  async function flattenSymbol(sym: string) {
    if (!sym) return;
    try {
      await api.flattenExecPositions([sym]);
      toast.show(`Flatten sent: ${sym}`);
      await refreshPositions(false);
      await refreshStatus(false);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten failed: ${brief(e)}`);
    }
  }

  async function flattenVisible() {
    try {
      const list = positions || [];
      const filtered = posSymbol
        ? list.filter((r:any) => String(r?.symbol || "").toLowerCase().includes(String(posSymbol).toLowerCase()))
        : list;
      const symbols = Array.from(new Set(filtered.map((r:any) => r.symbol).filter(Boolean)));
      if (!symbols.length) { toast.show("No visible positions to flatten."); return; }
      await api.flattenExecPositions(symbols);
      toast.show(`Flatten sent: ${symbols.join(", ")}`);
      await refreshPositions(false);
      await refreshStatus(false);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten failed: ${brief(e)}`);
    }
  }

  async function cancelOrder(id: string) {
    if (!id) return;
    try {
      await api.cancelExecOrder(id);
      toast.show(`Cancel sent: ${id}`);
      await refreshExec(false);
    } catch (e:any) {
      toast.show(`Cancel failed: ${brief(e)}`);
    }
  }

  async function refreshExec(show = true) {
    try {
      setExLoading(true);
      try { await api.syncExecDeals(); } catch {}
      const q: any = {};
      if (exSymbol) q.symbol = exSymbol;
      setOrders(await api.listExecOrders(q));
      setExAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Exec refresh failed: ${brief(e)}`);
    } finally {
      setExLoading(false);
    }
  }
  

async function refreshPositions(show = true) {
    const reqId = ++posReqId.current;
    try {
      setPosLoading(true);
      const data = await api.listExecPositions({});
      // Drop stale responses from earlier requests to prevent flicker
      if (reqId !== posReqId.current) return;
      let arr: any[] = data || [];
      if (posSymbol) {
        const q = String(posSymbol).toLowerCase();
        arr = arr.filter((r:any) => String(r?.symbol || "").toLowerCase().includes(q));
      }
      setPositions(arr);
      setPosAt(nowIso());
    } catch (e:any) {
      if (reqId === posReqId.current) {
        show && toast.show(`Positions refresh failed: ${brief(e)}`);
      }
    } finally {
      if (reqId === posReqId.current) setPosLoading(false);
    }
  }



async function refreshAutoStatus() {
  try {
    const st = await api.autopilotStatus();
    setAutoStatus(st || null);
    setAutoAt(nowIso());
  } catch (e:any) {
    // silent
  }
}


// ---------- Helpers (UI) ----------
function timeAgo(iso?: string) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t);
  const s = Math.floor(diff/1000); if (s<60) return `${s}s ago`;
  const m = Math.floor(s/60); if (m<60) return `${m}m ago`;
  const h = Math.floor(m/60); return `${h}h ago`;
}
function shortReason(r:any): string {
  const txt = r?.reason || r?.note || `${r.action||""} ${r.side||""} ${r.symbol||""}`.trim();
  if (!txt) return "";
  return String(txt).length>120 ? String(txt).slice(0,120)+"…" : String(txt);
}
async function openExplain(r:any) {
  setExplainRow(r);
  setExplainOpen(true);
  try {
    const [ctx, last] = await Promise.all([
      api.autopilotContext?.().catch(()=>null),
      api.autopilotLastOutput?.().catch(()=>null),
    ]);
    setExplainData({ ctx, last, row: r });
  } catch {
    setExplainData({ row: r });
  }
}
// ---------- Render ----------
  return (
    <div className="app">
      <div className="bgfx" aria-hidden="true"></div>
      <style>{css}</style>

      <style>{`/* --- overrides: autopilot health metrics position tweak + horizontal spread + control nudge --- */
/* --- overrides: compact vertical rhythm --- */
.panels2.vsplit{gap:8px} /* tighten spacing between left/right panels */
.panel{padding:14px}
.stack{gap: 8px}
.strat-grid{gap: 8px}
.card-lg{padding:16px}

.health{ align-items: center !important; }
.health .health-metrics{ justify-self: center !important; align-self: center !important; margin-top: -16px; gap: 8px 24px; }
.health .stat{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; white-space: nowrap; }
.autopilot-controls{ margin-top: 11px; } /* bumped ~5px more down */`}</style>


      <header className="header">
        <div className="title">
          <div>
            <div style={{fontSize:28,fontWeight:800}}>Moomoo ChatGPT Trading Bot</div>
            <div className="help">API: <small className="code">{API_BASE}</small></div>
          </div>
        </div>

        <div className="header-quick">
          <span className="indicator" title={connected ? "Broker connection OK" : "Not connected"}>
            <span className={`dot ${connected ? "green" : "red"}`} />
            {connected ? "Connected" : "Not connected"}
          </span>
          <span className="indicator" title="Active account">
            <span>{activeAccount?.account_id || "—"}</span>
            {activeAccount?.trd_env ? <span>• {activeAccount.trd_env}</span> : null}
          </span>
          <span className="indicator" title="Risk Guardrail">
            <span className={`dot ${riskEnabled ? "green" : "red"}`} />
            Risk: {riskEnabled==null ? "—" : (riskEnabled ? "On" : "Off")}
          </span>
          <span className="indicator" title="Bot Mode"><span>Bot mode: {mode==="automatic" ? "Automatic" : "Manual"}</span></span>
        </div>
      </header>

      <nav className="tabs">
        {["Settings","Bot Status","Activity Log"].map((t,i)=>(
          <button key={t} className={`tab ${tab===i?'active':''}`} onClick={()=>setTab(i as Tab)}>{t}</button>
        ))}
      </nav>

      {!connected && (
        <div className="panel" role="alert" style={{borderColor:"rgba(239,68,68,.45)", background:"linear-gradient(90deg, rgba(239,68,68,.1), transparent)"}}>
          <strong>Not connected.</strong> Connect to OpenD and select an account in <em>Settings → Connection</em>.
        </div>
      )}

      {/* ===== Settings ===== */}
      {tab===Tab.Settings && (
        <section className="stack">
          {/* Connection */}
          <div className="panel">
            <h2 style={{marginTop:0,marginBottom:8}}>Connection</h2>
            <div className="help" style={{marginBottom:8}}>
              Connect to your local OpenD gateway, then select an account (SIMULATE recommended).
            </div>
            <div className="form-row">
              <div><div className="label">Host</div><input className="input" value={host} onChange={e=>setHost(e.target.value)} /></div>
              <div><div className="label">Port</div><input className="input" type="number" value={port} onChange={e=>setPort(parseInt(e.target.value)||0)} /></div>
              <div><div className="label">Client ID</div><input className="input" type="number" value={clientId} onChange={e=>setClientId(parseInt(e.target.value)||1)} /></div>
            </div>
            <div className="row" style={{marginTop:8}}>
              <button className="btn" onClick={doConnect}>Connect</button>
              <button className="btn" onClick={reconnectFromSaved}>Reconnect (Saved)</button>
              <span className="help" style={{marginLeft:"auto"}}>
                {connected ? "Connected" : "Not connected"} • {activeAccount?.account_id || "—"} {activeAccount?.trd_env ? `• ${activeAccount.trd_env}` : ""}
              </span>
            </div>

            <div className="form-row" style={{marginTop:12}}>
              <div><div className="label">Account ID</div><input className="input" value={accountId} onChange={e=>setAccountId(e.target.value)} placeholder="e.g., 54871" /></div>
              <div>
                <div className="label">Trading Env</div>
                  <NiceSelect
                    value={trdEnv}
                    onChange={(v)=>setTrdEnv((v === "REAL" ? "REAL" : "SIMULATE") as "REAL"|"SIMULATE")}
                    options={[
                      { value: "SIMULATE", label: "SIMULATE" },
                      { value: "REAL", label: "REAL" },
                    ]}
                    width={180}
                  />
              </div>
            </div>
            <div className="row" style={{marginTop:8}}>
              <button className="btn brand" onClick={doSelect}>Select Account</button>
              <button className="btn" onClick={()=>api.sessionSave(host as string, Number(port), String(accountId), String(trdEnv)).then(()=>toast.show("Session saved.")).catch(e=>toast.show(brief(e)))}>Save Session</button>
              <button className="btn" onClick={()=>api.sessionClear().then(()=>toast.show("Saved session cleared.")).catch(e=>toast.show(brief(e)))}>Clear Saved</button>
            </div>
      </div>

          {/* Risk */}
          <div className="panel">
            <h2 style={{marginTop:0,marginBottom:10}}>Risk Configuration</h2>
            {!cfg ? (<div className="help">Loading risk config…</div>) : (
              <>
                <div className="form-row">
                  <div><div className="label">Enabled</div>
                    <NiceSelect
                      value={String(cfgGet("enabled", true))}
                      onChange={(v)=>setCfg({ ...(cfg||{}), enabled: v === "true" })}
                      options={[{ value:"true", label:"True" }, { value:"false", label:"False" }]}
                      width={140}
                    />
                  </div>
                  <div><div className="label">Max $ per trade</div>
                    <input className="input" type="number" value={cfgGet("max_usd_per_trade", 1000)}
                      onChange={e=>setCfg({ ...(cfg||{}), max_usd_per_trade: Number(e.target.value) })}/>
                  </div>
                  <div><div className="label">Max open positions</div>
                    <input className="input" type="number" value={cfgGet("max_open_positions", 5)}
                      onChange={e=>setCfg({ ...(cfg||{}), max_open_positions: Number(e.target.value) })}/>
                  </div>
                </div>
                <div className="form-row">
                  <div><div className="label">Max daily loss ($)</div>
                    <input className="input" type="number" value={cfgGet("max_daily_loss_usd", 200)}
                      onChange={e=>setCfg({ ...(cfg||{}), max_daily_loss_usd: Number(e.target.value) })}/>
                  </div>
                  <div><div className="label">Start (PT)</div>
                    <input className="input" value={cfgGet("trading_hours_pt", {start:"06:30",end:"13:00"}).start}
                      onChange={e=>setCfg({ ...(cfg||{}), trading_hours_pt: { ...(cfg?.trading_hours_pt||{start:"06:30",end:"13:00"}), start: e.target.value }})}/>
                  </div>
                  <div><div className="label">End (PT)</div>
                    <input className="input" value={cfgGet("trading_hours_pt", {start:"06:30",end:"13:00"}).end}
                      onChange={e=>setCfg({ ...(cfg||{}), trading_hours_pt: { ...(cfg?.trading_hours_pt||{start:"06:30",end:"13:00"}), end: e.target.value }})}/>
                  </div>
                </div>
                <div className="form-row">
                  <div><div className="label">Flatten before close (min)</div>
                    <input className="input" type="number" value={cfgGet("flatten_before_close_min", 5)}
                      onChange={e=>setCfg({ ...(cfg||{}), flatten_before_close_min: Number(e.target.value) })}/>
                  </div>
                </div>
                <div className="row" style={{marginTop:10}}>
                  <button className="btn brand" onClick={saveRisk} disabled={saving}>{saving ? "Saving…" : "Save Risk Config"}</button>
                </div>
              </>
            )}
            <div className="help" style={{marginTop:8}}>Risk checks are enforced server-side before any order is sent.</div>
          </div>
          {/* Data & Discovery */}
          <div className="panel compact">
            <h2 style={{marginTop:0}}>Data & Discovery</h2>
            <DiscoverySettings />
            <div style={{margin:"12px 0", borderTop:"1px solid var(--border)"}} />
            <SignalsSettings />
          </div>
          {/* Trading Behavior (Style) */}
          <div className="panel compact">
            <h2 style={{marginTop:0}}>Trading Behavior</h2>
            <StyleAndWatchlist />
          </div>

          {/* Strategies Catalog removed per new design */}
        </section>
      )}

      
      {/* ===== Bot Status ===== */}
      {tab===Tab.Status && (
        <section className="stack">
          {/* KPIs */}
          
          
          
          {/* KPI strip */}
          <div className="grid-3">
            <div className="card card-lg" style={{gridColumn:"span 2"}}>
  <h3>Autopilot Health</h3>
    <div className="health">
    <div className="health-top">
      <span className={`badge ${autoStatus?.on ? "good" : "bad"} health-badge`}>
        {autoStatus?.on ? "ON" : "OFF"}
      </span>
      <span
        className={`badge ${(autoStatus as any)?.planner_info?.enabled ? "good" : "bad"} health-badge`}
        title="Planner provider/model"
      >
        {(() => {
          const pi:any = (autoStatus as any)?.planner_info || {};
          const model = pi.model || (autoStatus as any)?.stats?.model || "stub";
          return pi.enabled ? `GPT: ${model}` : `Planner: Stub`;
        })()}
      </span>
    </div>
    <div className="health-metrics">
      <span className="stat">Last tick: {autoStatus?.last_tick ? timeAgo(autoStatus.last_tick) : "-"}</span>
      <span className="stat">Reject streak: {autoStatus?.reject_streak ?? "-"}</span>
      <span className="stat">Decisions: {autoStatus?.stats?.decisions_today ?? autoStatus?.stats?.decisions ?? "-"}</span>
      <span className="stat">Uptime: {autoStatus?.stats?.uptime ?? "-"}</span>
      <span className="stat">Avg think: {autoStatus?.stats?.avg_think_ms ? `${autoStatus.stats.avg_think_ms} ms` : "-"}</span>
      <span className="stat">Guardrails: {riskEnabled==null ? "-" : (riskEnabled ? "On" : "Off")}</span>
    </div>
  </div>
</div>
            <div className="card split-card" style={{ gridRow: "span 2" }}>
  <div className="section top">
    <h3>Autopilot</h3>
    <div className="row autopilot-controls" style={{alignItems:"center", justifyContent:"space-between"}}>
      <div className="row" style={{gap:12}}>
        <button
          className={`switch-lg ${mode==="automatic" ? "on" : ""}`}
          role="switch"
          aria-checked={mode==="automatic"}
          onClick={async()=> {
            const turnOn = !(mode==="automatic");
            try { await api.autopilotEnable(turnOn); }
            catch(e:any) { toast.show(`Autopilot toggle failed: ${brief(e)}`); }
            setMode(turnOn ? "automatic" : "manual");
          }}
          title="Toggle Autopilot On/Off"
        >
          <span className="thumb" />
        </button>
        <div className="help strong">{mode==="automatic" ? "On" : "Off"}</div>
      </div>
      <button className="btn brand" style={{marginRight:16}} onClick={doPreview}>Preview Plan</button>
    </div>
  </div>
  <div className="section bottom" style={{marginTop:34}}>
    <h3>Positions & Orders</h3>
    <div className="row" style={{alignItems:"baseline",gap:16}}>
      <div><div className="help">Open positions</div><div className="value">{openPositions ?? "—"}</div></div>
      <div><div className="help">Orders pending</div><div className="value">{openOrderCount ?? "—"}</div></div>
    </div>
  </div>
</div>
<div className="card"><h3>Realized PnL (Today)</h3>
              <div className="value" style={{color: pnl==null ? "inherit" : pnl>=0 ? "var(--green)" : "var(--red)"}}>
                {pnl ?? "—"}
              </div>
            </div>
            <div className="card">
              <h3>Exposure (MV)</h3>
              <div className="value">{exposureMV==null ? "—" : (exposureMV?.toFixed ? exposureMV.toFixed(2) : exposureMV)}</div>
            </div>
          </div>
          {/* Controls + Autopilot */}
          
          {/* Autopilot & Active Strategies */}
          
          {/* Strategy & Preferences row */}
          <div className="panels2 vsplit">
            <div className="panel no-bottom-line" style={{ gridRow: "span 2" }}>
              <h2 style={{marginTop:0}}>Active Strategies</h2>
              <StrategyPicker />
            </div>
            <div className="panel compact">
              <h2 style={{marginTop:0}}>Trading Preferences</h2>
              <TradingPreferences />
            </div>
            <div className="panel compact">
              <h2 style={{marginTop:0}}>Current Stats</h2>
            <div className="statlist">
      {/* Win rate vs target */}
      <div className="statrow">
        <div className="k">Win rate</div>
        <div className="v">{autoStatus?.stats?.win_rate ?? autoStatus?.win_rate ?? "—"}{(autoStatus?.stats?.win_rate ?? autoStatus?.win_rate) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.win_rate ?? autoStatus?.win_rate);
          const t = prefWinRate;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.win_rate ?? autoStatus?.win_rate);
          const t = prefWinRate;
          if (v==null || t==null) return `target ${t ?? "—"}%`;
          const d = (v - t).toFixed(0);
          return `${v >= t ? "↑" : "↓"} ${d}% vs ${t}%`;
        })()}</span>
      </div>

      {/* Avg R multiple vs target RR */}
      <div className="statrow">
        <div className="k">Avg R multiple</div>
        <div className="v">{autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr ?? "—"}{(autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr) != null ? "R" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr);
          const t = prefRR;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.avg_rr ?? autoStatus?.avg_rr);
          const t = prefRR;
          if (v==null || t==null) return `target ${t ?? "—"}R`;
          const d = (v - t).toFixed(2);
          return `${v >= t ? "↑" : "↓"} ${d}R vs ${t}R`;
        })()}</span>
      </div>

      {/* Avg realized move vs TP threshold */}
      <div className="statrow">
        <div className="k">Avg realized move</div>
        <div className="v">{autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct ?? "—"}{(autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct);
          const t = prefTP;
          if (v==null || t==null) return "neutral";
          return v >= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.avg_realized_move_pct ?? autoStatus?.avg_realized_move_pct);
          const t = prefTP;
          if (v==null || t==null) return `target ${t ?? "—"}%`;
          const d = (v - t).toFixed(1);
          return `${v >= t ? "↑" : "↓"} ${d}% vs ${t}%`;
        })()}</span>
      </div>

      {/* Drawdown vs Max drawdown (lower is better) */}
      <div className="statrow">
        <div className="k">Drawdown</div>
        <div className="v">{autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct ?? "—"}{(autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct) != null ? "%" : ""}</div>
        <span className={`delta ${(() => {
          const v = (autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct);
          const t = prefMaxDD;
          if (v==null || t==null) return "neutral";
          return v <= t ? "up" : "down";
        })()}`}>{(() => {
          const v = (autoStatus?.stats?.drawdown_pct ?? autoStatus?.drawdown_pct);
          const t = prefMaxDD;
          if (v==null || t==null) return `max ${t ?? "—"}%`;
          const d = (t - v).toFixed(1);
          return `${v <= t ? "↑" : "↓"} ${d}% headroom`;
        })()}</span>
      </div>
    </div>
  </div>


            </div>
{/* Positions (SIM) – its own panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
              <h2 className="title-lg" style={{margin:0}}>Positions (SIM)</h2>
            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:12}}>
              <div style={{minWidth:220}}>
                <input className="input search" value={posSymbol}
                       onChange={e=>setPosSymbol(e.target.value)}
                       placeholder="US.AAPL" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} />
              </div>
              <button className="btn amber" onClick={flattenVisible}>Flatten Visible</button>
              <div className="row" style={{marginLeft:"auto", gap:10}}><span className="help">Last updated: {posAt}</span></div>
            </div>
            <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
              <table className="table-modern">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Qty</th><th>Avg</th><th>Last</th>
                    <th>MV</th><th>UPL</th><th>RPL Today</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(positions||[]).filter(p=>(p?.qty ?? 0)!==0)
                    .filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase()))
                    .length ? (positions||[])
                    .filter(p=>(p?.qty ?? 0)!==0)
                    .filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase()))
                    .map((p:any)=>( 
                      <tr key={p.symbol}>
                        <td>{p.symbol}</td>
                        <td className="num">{p.qty}</td>
                        <td className="num">{p.avg_cost?.toFixed ? p.avg_cost.toFixed(2) : p.avg_cost}</td>
                        <td className="num">{p.last==null ? "" : (p.last?.toFixed ? p.last.toFixed(2) : p.last)}</td>
                        <td className="num">{p.mv==null ? "" : (p.mv?.toFixed ? p.mv.toFixed(2) : p.mv)}</td>
                        <td className="num" style={{color: p.upl==null ? "inherit" : (p.upl>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.upl==null ? "" : (p.upl?.toFixed ? p.upl.toFixed(2) : p.upl)}
                        </td>
                        <td className="num" style={{color: p.rpl_today==null ? "inherit" : (p.rpl_today>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.rpl_today==null ? "" : (p.rpl_today?.toFixed ? p.rpl_today.toFixed(2) : p.rpl_today)}
                        </td>
                        <td><button className="btn red" onClick={()=>flattenSymbol(p.symbol)}>Flatten</button></td>
                      </tr>
                    ))
                  : <tr><td colSpan={8}>No positions.</td></tr>}
                </tbody>
              </table>
            </div>
            
          </div>

          {/* Orders & Fills (SIM) – separate panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
              <h2 className="title-lg" style={{margin:0}}>Orders (SIM)</h2>
              
            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:12}}>
              <div style={{minWidth:220}}>
                <input className="input search" value={exSymbol}
                       onChange={e=>setExSymbol(e.target.value)}
                       placeholder="US.AAPL" />
              </div>
              <div className="row" style={{marginLeft:"auto", gap:10}}>
                <span className="help">Last updated: {exAt}</span>
              </div>
            </div>

            <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
              <table className="table-modern">
                <thead>
                  <tr>
                    <th>Created</th><th>Order ID</th><th>Symbol</th><th>Side</th>
                    <th>Type</th><th>TIF</th><th>Status</th><th className="num">Req Qty</th>
                    <th className="num">Filled</th><th className="num">Avg</th><th className="num">Limit</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {orders?.length ? orders
                    .filter((o:any)=>!exSymbol || String(o.symbol||"").toLowerCase().includes(String(exSymbol).toLowerCase()))
                    .map((o:any)=>(
                    <tr key={o.order_id}>
                      <td className="small mono">{o.created_at}</td>
                      <td className="small mono truncate" title={o.order_id}>{shortId(o.order_id)}</td>
                      <td>{o.symbol}</td>
                      <td>{o.side}</td>
                      <td>{o.order_type}</td>
                      <td>{o.tif}</td>
                      <td>{statusTag(o.status)}</td>
                      <td className="num">{o.requested_qty}</td>
                      <td className="num">{o.filled_qty}</td>
                      <td className="num">{o.avg_fill_price==null ? "" : o.avg_fill_price}</td>
                      <td className="num">{o.limit_price==null ? "" : o.limit_price}</td>
                      <td>
                        <button className="btn red" disabled={o.status!=="open" && o.status!=="pending"} onClick={()=>cancelOrder(o.order_id)}>Cancel</button>
                      </td>
                    </tr>
                  )) : <tr><td colSpan={12}>No orders yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* ===== Activity Log ===== */}
      {tab===Tab.Activity && (
        <ActivityLog
          logs={logs} logsAt={logsAt}
          logsEvery={logsEvery} setLogsEvery={setLogsEvery}
          logsAuto={logsAuto} setLogsAuto={setLogsAuto}
          logSymbol={logSymbol} setLogSymbol={setLogSymbol}
          logSince={logSince} setLogSince={setLogSince}
          logLimit={logLimit} setLogLimit={setLogLimit}
          logsSource={logsSource} setLogsSource={setLogsSource}
          onExplain={openExplain}
          refreshLogs={()=>refreshLogs(true)} logsLoading={logsLoading}
        />
      )}

      {/* Backtest tab removed */}

      {previewOpen && createPortal(
        <div id="preview-modal" style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }} onClick={()=>setPreviewOpen(false)}>
          <div className="panel" style={{width: "min(860px, 94vw)", maxHeight: "80vh", overflow: "auto"}} onClick={e=>e.stopPropagation()}>
            <h2 style={{marginTop:0}}>Autopilot Preview</h2>
            <div className="help" style={{marginBottom:8}}>Raw planner input/output and validation (read-only)</div>
            <pre style={{whiteSpace:"pre-wrap", background:"#0b1220", padding:"12px", borderRadius:"8px", border:"1px solid var(--border)"}}>
{JSON.stringify(previewResult, null, 2)}
            </pre>
            <div className="row" style={{marginTop:12, justifyContent:"flex-end"}}>
              <button className="btn" onClick={()=>setPreviewOpen(false)}>Close</button>
            </div>
          </div>
        </div>, document.body
      )}

      {explainOpen && createPortal(
        <div id="explain-modal" style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000
        }} onClick={()=>setExplainOpen(false)}>
          <div className="panel" style={{width: "min(860px, 94vw)", maxHeight: "80vh", overflow: "auto"}} onClick={e=>e.stopPropagation()}>
            <h2 style={{marginTop:0}}>Decision Details</h2>
            <div className="help" style={{marginBottom:8}}>What the bot was thinking and why it acted</div>
            {(() => {
              try {
                const row:any = explainRow || {};
                const extra:any = row.extra_json ? JSON.parse(row.extra_json) : (row.extra || {});
                const sigs:any[] = Array.isArray(extra?.signals_used) ? extra.signals_used : [];
                const tone = extra?.news_tone;
                const conf = extra?.conf; const minc = extra?.min_conf;
                if (!sigs.length && !tone && conf==null) return null;
                return (
                  <div className="panel compact" style={{background:"#0e1320", marginBottom:8}}>
                    <div className="row" style={{gap:8, flexWrap:"wrap"}}>
                      {typeof conf === 'number' && typeof minc === 'number' && (
                        <span className="badge" title="Confidence gate">conf {conf.toFixed(2)} ≥ {minc.toFixed(2)}</span>
                      )}
                      {tone && <span className="badge" title="News tone">news {String(tone)}</span>}
                      {sigs.slice(0,6).map((s:any, i:number)=> (
                        <span key={i} className="badge" title={`${s.strategy} ${s.signal}`}>{s.strategy}:{s.signal} {Number(s.strength||0).toFixed(2)}</span>
                      ))}
                    </div>
                  </div>
                );
              } catch { return null; }
            })()}
            <pre style={{whiteSpace:"pre-wrap", background:"#0b1320", padding:"12px", borderRadius:"8px", border:"1px solid var(--border)"}}>
{JSON.stringify(explainData || explainRow, null, 2)}
            </pre>
            <div className="row" style={{marginTop:12, justifyContent:"flex-end"}}>
              <button className="btn" onClick={()=>setExplainOpen(false)}>Close</button>
            </div>
          </div>
        </div>, document.body
      )}

      {toast.msg && <div className="toast" role="status" aria-live="polite">{toast.msg}</div>}
    </div>
  );

// ===== Handlers & helpers (scoped to App) =====
async function doConnect() {
  try {
    await api.connect(String(host), Number(port), Number(clientId));
    setConnected(true);
    try { setActiveAccount(await api.accountsActive()); } catch {}
    toast.show("Connected.");
  } catch (e:any) {
    toast.show(`Connect failed: ${brief(e)}`);
  }
}

async function reconnectFromSaved() {
  try {
    const st = await api.sessionStatus();
    const saved = st?.saved || {};
    const h = String(saved.host || host);
    const p = Number(saved.port || port);
    const cid = Number(saved.client_id || clientId);
    await api.connect(h, p, cid);
    setHost(h); setPort(p); setClientId(cid);
    setConnected(true);
    try { setActiveAccount(await api.accountsActive()); } catch {}
    toast.show("Reconnected from saved.");
  } catch (e:any) {
    toast.show(`Reconnect failed: ${brief(e)}`);
  }
}

async function doSelect() {
  try {
    const resp = await api.selectAccount(String(accountId), trdEnv);
    setActiveAccount(resp as any);
    toast.show("Account selected.");
  } catch (e:any) {
    toast.show(`Select failed: ${brief(e)}`);
  }
}

function cfgGet<K extends keyof RiskConfig, T = any>(key: K, def: T): any {
  const c: any = cfg || {};
  const v = c[key];
  if (v === undefined || v === null) return def;
  return v;
}


async function saveRisk() {
  if (!cfg) return;
  try {
    setSaving(true);
    const r = await api.putRiskConfig(cfg);
    setCfg(r);
    // Instantly reflect header pill without waiting for poll / reload
    const en = (typeof (r as any)?.enabled === "boolean")
      ? !!(r as any).enabled
      : (typeof cfg?.enabled === "boolean" ? !!cfg.enabled : null);
    setRiskEnabled(en);
    // Pull fresh status and autopilot snapshot
    await refreshStatus(false);
    await refreshAutoStatus();
    toast.show("Risk config saved.");
  } catch (e:any) {
    toast.show(`Save failed: ${brief(e)}`);
  } finally {
    setSaving(false);
  }
}


async function killSwitch() {
  const ok = await askConfirm("Stop all running automations NOW?");
  if (!ok) return;
  try {
    await SEND("/automation/stop_all", {});
    toast.show("Kill switch sent.");
    setStratRefreshTick((t: number)=>t+1);
  } catch (e:any) {
    toast.show(`Kill switch failed: ${brief(e)}`);
  }
}

async function doFlattenAll() {
  const ok = await askConfirm("Flatten ALL positions now? (SIMULATE is allowed; REAL is blocked by server)");
  if (!ok) return;
  try {
    await api.flattenAll();
    toast.show("Flatten sent.");
  } catch (e:any) {
    toast.show(`Flatten failed: ${brief(e)}`);
  }
}

async function applyMode(next: Mode) {
  try {
    const r = await api.setBotMode(next);
    setMode(r.mode as Mode);
  } catch (e:any) {
    toast.show(`Set mode failed: ${brief(e)}`);
  }
}

async function doPreview() {
  try {
    setPreviewLoading(true);
    const r = await api.autopilotPreview();
    setPreviewResult(r);
    setPreviewOpen(true);
  } catch (e:any) {
    toast.show(`Preview failed: ${brief(e)}`);
  } finally {
    setPreviewLoading(false);
  }
}


  function brief(err: any) {
    try { const j = JSON.parse(String(err?.message || err)); return j?.detail || err?.message || String(err); }
    catch { return err?.message || String(err); }
  }
}

// ---------- Subcomponents ----------

// ---------- Fancy dropdowns (portal-based, non-clipping) ----------
type Opt = { value: string; label: string };

function useOutsideClose<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", h, true);
    document.addEventListener("keydown", k, true);
    return () => { document.removeEventListener("mousedown", h, true); document.removeEventListener("keydown", k, true); };
  }, [open, onClose]);
  return ref;
}

function useAnchorPosition(trigger: HTMLElement | null, open: boolean, menuMaxH = 260) {
  const [pos, setPos] = useState<{ left: number; top: number; width: number; openUp: boolean }>(
    { left: 0, top: 0, width: 0, openUp: false }
  );

  useEffect(() => {
    if (!open || !trigger) return;

    // capture a non-null handle for the closure
    const el: HTMLElement = trigger;

    function place() {
      const r = el.getBoundingClientRect(); // <- no null warning now
      const width = Math.max(r.width, 160);
      let left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
      let top = r.bottom + 6;
      let openUp = false;

      // open upward if not enough room below
      if (top + menuMaxH > window.innerHeight - 8) {
        openUp = true;
        top = Math.max(8, r.top - 6 - menuMaxH);
      }
      setPos({ left, top, width, openUp });
    }

    place();
    const opts: AddEventListenerOptions = { passive: true };
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place, opts);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, trigger, menuMaxH]);

  return pos;
}

export function NiceSelect({
  value, onChange, options, width = 160, placeholder = "Select…"
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const outsideRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const pos = useAnchorPosition(btnRef.current ?? null, open);
  const current = options.find(o => o.value === value);

  return (
    <div className="custom-select" ref={wrapRef} style={{ width }}>
      <button className="custom-trigger" ref={btnRef} type="button" onClick={() => setOpen(o => !o)}>
        {current?.label ?? <span style={{ color: "var(--muted)" }}>{placeholder}</span>}
      </button>

      {open && createPortal(
        <div
          ref={outsideRef}
          className="menu"
          style={{
            position: "fixed",
            left: pos.left,
            top: pos.top,
            width: pos.width,
            maxHeight: 260,
            zIndex: 10000,
          }}
        >
          {options.map(o => (
            <div
              key={o.value}
              className={`item ${o.value === value ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); }}
            >
              {o.label}
            </div>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}

export function NiceCombobox({
  value, onChange, options, width = 200, placeholder = "Search…"
}: { value: string; onChange: (v: string) => void; options: Opt[]; width?: number; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const outsideRef = useOutsideClose<HTMLDivElement>(open, () => setOpen(false));
  const pos = useAnchorPosition(btnRef.current, open);
  const current = options.find(o => o.value === value);
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q.toLowerCase()) || o.value.toLowerCase().includes(q.toLowerCase()))
    : options;

  return (
    <div className="custom-select" style={{ width }}>
      <button className="custom-trigger" ref={btnRef} type="button" onClick={() => setOpen(o => !o)}>
        {current?.label ?? <span style={{ color: "var(--muted)" }}>Select…</span>}
      </button>

      {open && createPortal(
        <div
          ref={outsideRef}
          className="menu"
          style={{
            position: "fixed",
            left: pos.left,
            top: pos.top,
            width: pos.width,
            maxHeight: 260,
            zIndex: 10000,
          }}
        >
          <input className="search" autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} />
          {filtered.length ? filtered.map(o => (
            <div
              key={o.value}
              className={`item ${o.value === value ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); setQ(""); }}
            >
              {o.label}
            </div>
          )) : <div className="item" style={{ color: "var(--muted)" }}>No matches</div>}
        </div>,
        document.body
      )}
    </div>
  );
}


function ActivityLog(props: {
  logs: any[]; logsAt: string; logsEvery: number; setLogsEvery: (n:number)=>void;
  logsAuto: boolean; setLogsAuto: (b:boolean)=>void;
  logSymbol: string; setLogSymbol: (s:string)=>void;
  logSince: number; setLogSince: (n:number)=>void;
  logLimit: number; setLogLimit: (n:number)=>void;
  logsSource: "system" | "autopilot"; setLogsSource: (v: "system" | "autopilot") => void;
  onExplain: (row:any)=>void;
  refreshLogs: () => void; logsLoading: boolean;
}) {
  const { logs, logsAt, logsEvery, setLogsEvery, logsAuto, setLogsAuto,
          logSymbol, setLogSymbol, logSince, setLogSince, logLimit, setLogLimit,
          logsSource, setLogsSource, onExplain,
          refreshLogs, logsLoading } = props;

  const [coverage, setCoverage] = useState<{ exits?: number; stops?: number; tp?: number } | null>(null);
  const [covAt, setCovAt] = useState<string>("—");
  const [assets, setAssets] = useState<{ mode:string; equity?: number|null; bp?: number|null }|null>(null);
  const [assetsAt, setAssetsAt] = useState<string>("—");

  useEffect(() => { (async ()=>{
    try {
      const st:any = await api.autopilotStatus();
      const s = st?.stats || {};
      setCoverage({ exits: Number(s?.exits_coverage_pct ?? NaN), stops: Number(s?.stops_coverage_pct ?? NaN), tp: Number(s?.tp_coverage_pct ?? NaN) });
      setCovAt(new Date().toLocaleTimeString());
    } catch {}
    try {
      const a:any = await api.getAccountAssets();
      setAssets(a || null);
      setAssetsAt(new Date().toLocaleTimeString());
    } catch {}
  })(); }, [logsAt, logsSource, logSince]);

  return (
    <section className="stack activity">
      <div className="panel">
        <h2 className="title-lg" style={{marginTop:0}}>Activity Log</h2>
        <div className="row sticky-controls" style={{alignItems:"end", gap:12, marginTop:12}}>
          <div>
            <div className="label">Source</div>
            <NiceSelect
              value={logsSource}
              onChange={(v)=>{ setLogsSource((v as any) as ("system"|"autopilot")); setTimeout(()=>refreshLogs(), 0); }}
              options={[{value:"system",label:"System"},{value:"autopilot",label:"Autopilot"}]}
              width={160}
            />
          </div>
          <div style={{minWidth:220}}><div className="label">Symbol (optional)</div>
            <input className="input search" value={logSymbol}
                   onChange={e=>setLogSymbol(e.target.value)}
                   placeholder="US.AAPL" />
          </div>
          <div style={{width:140}}><div className="label">Since (hours)</div>
            <input className="input" type="number" value={logSince}
                   onChange={e=>setLogSince(parseInt(e.target.value)||0)} />
          </div>
          <div>
            <div className="label">Limit</div>
            <div className="row" style={{gap:6, alignItems:"center"}}>
              <input className="input" type="number" value={logLimit}
                     onChange={e=>setLogLimit(parseInt(e.target.value)||0)}
                     style={{width:110}} />
              <button className="btn" onClick={()=>exportCsv(logs)} style={{padding:"6px 10px"}}>Export CSV</button>
            </div>
          </div>
          <div className="row" style={{marginLeft:"auto", gap:10}}>
            <span className="help">Last updated: {logsAt}</span>
          </div>
        </div>

        {assets && (
          <div className="row" style={{gap:12, margin:"8px 0"}}>
            <span className="badge" title={`Updated ${assetsAt}`}>{assets.mode === 'moomoo' ? 'Broker' : 'SIM'} Net Assets: {assets?.equity!=null ? `$${Number(assets.equity).toFixed(2)}` : '—'}</span>
            {assets?.bp!=null && <span className="badge" title="Buying Power">BP: {`$${Number(assets.bp).toFixed(2)}`}</span>}
          </div>
        )}

        {coverage && isFinite(coverage.exits||NaN) && (
          <div className="row" style={{gap:12, margin:"8px 0"}}>
            <span className="delta" title={`Updated ${covAt}`}>Exits coverage: {coverage.exits?.toFixed(1)}%</span>
            <span className="delta" title={`Updated ${covAt}`}>Stops: {coverage.stops?.toFixed(1)}%</span>
            <span className="delta" title={`Updated ${covAt}`}>Take‑profit: {coverage.tp?.toFixed(1)}%</span>
          </div>
        )}

        <div className="table-wrap" style={{maxHeight: 460}}>
          <table className="table-modern">
            <thead>
              <tr>
                <th>Time</th><th>Mode</th><th>Action</th><th>Symbol</th>
                <th>Side</th><th>Qty</th><th>Price</th><th>Reason</th><th>Status</th><th>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.length ? logs.map((r:any)=>(
                <tr key={r.id ?? `${r.ts}-${Math.random()}`}>
                  <td className="small mono">{r.ts ?? ""}</td><td>{r.mode ?? ""}</td><td>{r.action ?? ""}</td>
                  <td>{r.symbol ?? ""}</td><td>{r.side ?? ""}</td><td className="num">{r.qty ?? ""}</td>
                  <td className="num">{r.price ?? ""}</td><td>{r.reason ?? ""}</td><td>{statusTag(r.status)}</td>
                  <td><button className="btn" onClick={()=>onExplain(r)}>Explain</button></td>
                </tr>
              )) : <tr><td colSpan={9}>No log entries yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="help" style={{marginTop:8}}>All actions are logged server-side for traceability.</div>
      </div>
    </section>
  );

  function exportCsv(rows: any[]) {
    if (!rows?.length) { alert("No rows to export"); return; }
    const cols = ["ts","mode","action","symbol","side","qty","price","reason","status"];
    const escape = (s:any) => String(s ?? "").replace(/"/g,'""');
    const csv = [cols.join(",")].concat(rows.map(r=>cols.map(c=>`"${escape(r[c])}"`).join(","))).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `activity_${new Date().toISOString().replace(/[:.]/g,"-")}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  }
}

function ActiveStrategies({ onStopped, refreshKey }: { onStopped?: () => void; refreshKey?: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(()=>{ refresh(); }, []);           // initial load
  useEffect(()=>{ refresh(); }, [refreshKey]); // reload after Kill Switch

  async function refresh() {
    try {
      setLoading(true);
      const ls = await GET<any[]>("/automation/strategies");
      setItems((ls || []).filter((s:any)=>s.active));
    } finally {
      setLoading(false);
    }
  }

  async function stop(id: number) {
    try {
      await SEND(`/automation/stop/${id}`, {}, "POST");
      onStopped?.();  // this will bump stratRefreshTick in App
      refresh();
    } catch {}
  }

  return (
    <div className="stack">
      <div className="row">
        <button className="btn" onClick={refresh}>{loading?"Refreshing…":"Refresh"}</button>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{["id","name","symbol","active","actions"].map(h=><th key={h}>{h}</th>)}</tr></thead>
          <tbody>
            {(items?.length?items:[]).map((s:any)=>(
              <tr key={s.id}>
                <td>{s.id}</td><td>{s.name}</td><td>{s.symbol}</td>
                <td>{String(s.active)}</td>
                <td>{s.active && <button className="btn red" onClick={()=>stop(Number(s.id))}>Stop</button>}</td>
              </tr>
            ))}
            {!items?.length && <tr><td>No strategies</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---- Strategies Catalog (select / configure / presets / start) ----
function StrategyCatalog({ connected }: { connected: boolean }) {
  const [kind, setKind] = useLocalStorage<StrategyKind>("strat.kind", "ma-crossover");

  // shared
  const [symbol, setSymbol] = useLocalStorage("strat.symbol", "US.AAPL");

  // ma-crossover params
  const [fast, setFast] = useLocalStorage("strat.ma.fast", 20);
  const [slow, setSlow] = useLocalStorage("strat.ma.slow", 50);
  const [ktype, setKType] = useLocalStorage("strat.ma.ktype", "K_1M");
  const [interval, setIntervalSec] = useLocalStorage("strat.ma.interval", 15);
  const [qty, setQty] = useLocalStorage("strat.ma.qty", 1.0);
  const [sizeMode, setSizeMode] = useLocalStorage<"shares"|"usd">("strat.ma.sizeMode", "shares");
  const [dollarSize, setDollarSize] = useLocalStorage("strat.ma.dollar", 0.0);
  const [allowReal, setAllowReal] = useLocalStorage("strat.ma.allowReal", false);

  // grid (placeholder fields)
  const [gridFast, setGridFast] = useLocalStorage("strat.grid.fast", 20);
  const [gridSlow, setGridSlow] = useLocalStorage("strat.grid.slow", 50);

  // presets (localStorage-based)
  const PRESETS_KEY = "strat.presets.v1";
  const [presets, setPresets] = useState<Record<string, any>>(() => {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || "{}"); } catch { return {}; }
  });
  function savePresets(next: Record<string, any>) {
    setPresets(next);
    try { localStorage.setItem(PRESETS_KEY, JSON.stringify(next)); } catch {}
  }
  function makePresetPayload() {
    if (kind === "ma-crossover") {
      return { kind, symbol, fast, slow, ktype, interval_sec: interval, qty, size_mode: sizeMode, dollar_size: dollarSize, allow_real: allowReal };
    } else {
      return { kind, symbol, fast: gridFast, slow: gridSlow };
    }
  }
  function onSavePreset() {
    const name = prompt("Preset name?");
    if (!name) return;
    const next = { ...presets, [name]: makePresetPayload() };
    savePresets(next);
  }
  function onLoadPreset(name: string) {
    const p = presets[name];
    if (!p) return;
    setKind(p.kind as StrategyKind);
    setSymbol(p.symbol || symbol);
    if (p.kind === "ma-crossover") {
      setFast(p.fast ?? fast); setSlow(p.slow ?? slow); setKType(p.ktype ?? ktype);
      setIntervalSec(p.interval_sec ?? interval); setQty(p.qty ?? qty);
      setSizeMode((p.size_mode as any) ?? sizeMode); setDollarSize(p.dollar_size ?? dollarSize);
      setAllowReal(!!p.allow_real);
    } else {
      setGridFast(p.fast ?? gridFast); setGridSlow(p.slow ?? gridSlow);
    }
  }
  function onDeletePreset(name: string) {
    const next = { ...presets }; delete next[name]; savePresets(next);
  }

  async function startStrategy() {
    if (!connected) { alert("Not connected"); return; }
    if (kind === "ma-crossover") {
      const payload = {
        symbol, fast, slow, ktype,
        qty, size_mode: sizeMode, dollar_size: dollarSize,
        interval_sec: interval, allow_real: allowReal,
      };
      try { await api.startMA(payload); alert("MA strategy started."); }
      catch (e:any) { alert(`Start failed: ${brief(e)}`); }
    } else {
      alert("Grid live start requires a /automation/start/ma-grid endpoint. (Backtest supports grid.)");
    }
  }

  function brief(err: any) {
    try { const j = JSON.parse(String(err?.message || err)); return j?.detail || err?.message || String(err); }
    catch { return err?.message || String(err); }
  }

  return (
    <div className="panel">
      <h2 style={{marginTop:0,marginBottom:10}}>Strategies</h2>
      <div className="form-row">
        <div>
          <div className="label">Strategy</div>
          <NiceSelect
            value={kind}
            onChange={(v)=>setKind(v as StrategyKind)}
            options={[
              { value: "ma-crossover", label: "MA Crossover" },
              { value: "ma-grid", label: "MA Grid (beta)"},
            ]}
            width={200}
          />
        </div>
        <div>
          <div className="label">Symbol</div>
          <input className="input" value={symbol} onChange={e=>setSymbol(e.target.value)} />
        </div>
        <div style={{display:"flex", alignItems:"flex-end", gap:12}}>
          <button className="btn brand" onClick={startStrategy} disabled={!connected}>Start</button>
          <button className="btn" onClick={onSavePreset}>Save Preset</button>
          <PresetPicker presets={presets} onLoad={onLoadPreset} onDelete={onDeletePreset}/>
        </div>
      </div>

      {kind === "ma-crossover" ? (
        <>
          <div className="form-row" style={{marginTop:12}}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={fast} onChange={e=>setFast(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={slow} onChange={e=>setSlow(parseInt(e.target.value)||2)} /></div>
            <div><div className="label">KType</div>
              <NiceCombobox
                value={ktype}
                onChange={setKType}
                options={["K_1M","K_5M","K_15M","K_30M","K_60M","K_1D"].map(k=>({value:k,label:k}))}
                width={180}
                placeholder="Search ktype…"
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Interval (sec)</div><input className="input" type="number" value={interval} onChange={e=>setIntervalSec(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Qty (shares)</div><input className="input" type="number" value={qty} onChange={e=>setQty(parseFloat(e.target.value)||0)} /></div>
            <div>
              <div className="label">Size Mode</div>
              <NiceSelect
                value={sizeMode}
                onChange={(v)=>setSizeMode(v as any)}
                options={[{value:"shares",label:"shares"},{value:"usd",label:"usd"}]}
                width={140}
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Dollar Size</div><input className="input" type="number" value={dollarSize} onChange={e=>setDollarSize(parseFloat(e.target.value)||0)} /></div>
            <div>
              <div className="label">Allow Real Trading</div>
              <NiceSelect
                value={String(allowReal)}
                onChange={(v)=>setAllowReal(v==="true")}
                options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
                width={140}
              />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="form-row" style={{marginTop:12}}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={gridFast} onChange={e=>setGridFast(parseInt(e.target.value)||1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={gridSlow} onChange={e=>setGridSlow(parseInt(e.target.value)||2)} /></div>
          </div>
          <div className="help" style={{marginTop:4}}>
            Live Grid start requires a server endpoint <code>/automation/start/ma-grid</code>. Backtest is available in the Backtest tab.
          </div>
        </>
      )}
    </div>
  );
}

function PresetPicker({ presets, onLoad, onDelete }:{ presets: Record<string, any>, onLoad:(n:string)=>void, onDelete:(n:string)=>void }) {
  const names = Object.keys(presets);
  const [sel, setSel] = useState(names[0] || "");
  useEffect(()=>{ if (!names.includes(sel)) setSel(names[0] || ""); }, [JSON.stringify(names)]);
  if (!names.length) return <span className="help">No presets yet.</span>;
  return (
    <div className="row" style={{alignItems:"flex-end"}}>
      <div>
        <div className="label">Presets</div>
        <NiceCombobox
          value={sel}
          onChange={setSel}
          options={names.map(n=>({value:n,label:n}))}
          width={180}
          placeholder="Search presets…"
        />
      </div>
      <button className="btn" onClick={()=>onLoad(sel)} disabled={!sel}>Load</button>
      <button className="btn red" onClick={()=>onDelete(sel)} disabled={!sel}>Delete</button>
</div>
  );
}

// Backtest panel removed per new design


function StrategyPicker() {
  const CATALOG: { key: string; name: string; desc?: string }[] = [
    { key: "ma-crossover", name: "MA Crossover", desc: "Fast/slow cross with RSI gate" },
    { key: "rsi-gate", name: "RSI Gate", desc: "Enter on RSI cross; avoid extremes" },
    { key: "breakout-retest", name: "Breakout Retest", desc: "Range breakout then retest confirm" },
    { key: "mean-reversion", name: "Mean Reversion", desc: "Fade stretches (z-score/RSI)" },
    { key: "atr-trailer", name: "ATR Trailing Stop", desc: "Trend-follow exits with ATR" },
    { key: "news-momo", name: "News Momentum", desc: "Spike-follow with risk caps" },
  ];
  const [selected, setSelected] = useLocalStorage<string[]>("pref.strategies", ["ma-crossover"]);

  // Map UI keys to backend signal strategy keys
  function mapToBackend(key: string): { signals?: Record<string, boolean>; newsEnabled?: boolean } {
    switch (key) {
      case "ma-crossover":
        return { signals: { macd_cross: true } };
      case "rsi-gate":
        return { signals: { stoch_rsi_extreme: true } };
      case "breakout-retest":
        return { signals: { bb_breakout: true } };
      case "news-momo":
        return { newsEnabled: true };
      default:
        return {};
    }
  }

  // Initialize from backend so toggles reflect real state
  useEffect(() => { (async () => {
    try {
      const sig = await api.getSignalsSettings();
      const news = await api.getNewsSettings();
      const enabled: string[] = [];
      if (sig?.strategies?.macd_cross) enabled.push("ma-crossover");
      if (sig?.strategies?.stoch_rsi_extreme) enabled.push("rsi-gate");
      if (sig?.strategies?.bb_breakout) enabled.push("breakout-retest");
      if (news?.enabled) enabled.push("news-momo");
      // keep any previously selected unknowns
      const known = new Set(CATALOG.map(s=>s.key));
      const prev = (selected || []).filter(k => !known.has(k));
      const merged = Array.from(new Set([...prev, ...enabled]));
      setSelected(merged);
    } catch {}
  })(); }, []);

  async function persistToggle(key: string, on: boolean) {
    // Persist to backend based on mapping
    const mapped = mapToBackend(key);
    try {
      if (mapped.signals) {
        // read existing to merge
        const cur = await api.getSignalsSettings();
        const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
        for (const k of Object.keys(mapped.signals)) next[k] = on;
        await api.putSignalsSettings({ strategies: next });
      } else if (mapped.newsEnabled !== undefined) {
        await api.putNewsSettings({ enabled: on });
      } else {
        // Unsupported today: no-op (kept locally)
      }
    } catch {}
  }
  function toggle(k: string) {
    setSelected(sel => {
      const on = !sel.includes(k);
      persistToggle(k, on);
      return on ? sel.concat(k) : sel.filter(x=>x!==k);
    });
  }
  return (
    <div className="stack">
      <div className="row" style={{justifyContent:"space-between", alignItems:"center", marginTop:2}}>
        <div className="help" style={{fontWeight:700}}>Selected: <b>{selected.length}</b> / {CATALOG.length}</div>
        <div className="row" style={{gap:8}}>
          <button className="btn" onClick={async()=>{
            const keys = CATALOG.map(s=>s.key);
            setSelected(keys);
            try {
              const cur = await api.getSignalsSettings();
              const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
              next.macd_cross = true; next.stoch_rsi_extreme = true; next.bb_breakout = true;
              await api.putSignalsSettings({ strategies: next });
              await api.putNewsSettings({ enabled: true });
            } catch {}
          }}>All</button>
          <button className="btn red" onClick={async()=>{
            setSelected([]);
            try {
              const cur = await api.getSignalsSettings();
              const next = { ...(cur?.strategies || {}) } as Record<string, boolean>;
              next.macd_cross = false; next.stoch_rsi_extreme = false; next.bb_breakout = false;
              await api.putSignalsSettings({ strategies: next });
              await api.putNewsSettings({ enabled: false });
            } catch {}
          }}>Clear</button>
        </div>
      </div>
      <div className="strat-grid">
        {CATALOG.map(s => {
          const on = selected.includes(s.key);
          return (
            <div key={s.key} className={`strat ${on ? "on" : ""}`} onClick={()=>toggle(s.key)} role="button" aria-pressed={on}>
              <span className={`dot ${on ? "green" : "red"}`} />
              <div className="info">
                <div className="name">{s.name}</div>
                <div className="desc">{s.desc || ""}</div>
              </div>
              <span className={`badge-mini ${on ? "good" : ""}`}>{on ? "On" : "Off"}</span>
            </div>
          );
        })}
      </div>
      <div className="help" style={{marginTop:6}}></div>
    </div>
  );
}

/** Compact number input with custom, backgroundless arrows.
 *  Arrows use the same color as labels (var(--muted)).
 */
/** Compact number input with custom, backgroundless arrows.
 *  Arrows use the same color as labels (var(--muted)).
 *  Allows clearing the field while editing; value is validated on blur/Enter.
 */

function Num({
  value,
  setValue,
  step = 1,
  min,
  max,
  inputProps = {},
}: {
  value: number;
  setValue: (n: number) => void;
  step?: number;
  min?: number;
  max?: number;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState<string>(
    Number.isFinite(value) ? String(value) : ""
  );

  useEffect(() => {
    // Sync from external value when not actively editing
    if (document.activeElement !== ref.current) {
      setText(Number.isFinite(value) ? String(value) : "");
    }
  }, [value]);

  const valid = (s: string) => /^-?\d*\.?\d*$/.test(s);

  function clamp(n: number) {
    if (min != null && n < min) n = min as number;
    if (max != null && n > max) n = max as number;
    return n;
  }

  function commit() {
    // If empty or partial number, settle to a safe value
    if (text === "" || text === "-" || text === "." || text === "-.") {
      const fallback = min != null ? Math.max(0, min) : 0;
      setValue(fallback);
      setText(String(fallback));
      return;
    }
    const n = clamp(Number(text));
    setValue(n);
    setText(String(n));
  }

  function bump(dir: 1 | -1) {
    const cur =
      text === "" || text === "-" || text === "." || text === "-."
        ? (Number.isFinite(value) ? value : 0)
        : Number(text);
    const s = Number(step) || 1;
    const next = clamp(Number((cur + dir * s).toFixed(6)));
    setValue(next);
    setText(String(next));
  }

  return (
    <div className="num">
      <input
        ref={ref}
        className="input"
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          const s = e.target.value;
          if (valid(s)) setText(s);
        }}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === "NumpadEnter") { e.preventDefault(); commit(); (e.currentTarget as HTMLInputElement).blur(); } }}
        {...inputProps}
      />
      <span className="spin" aria-hidden="true">
        <button type="button" onClick={() => bump(1)} title="Increase">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 6l6 6H6z" />
          </svg>
        </button>
        <button type="button" onClick={() => bump(-1)} title="Decrease">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 18l-6-6h12z" />
          </svg>
        </button>
      </span>
    </div>
  );
}

function TradingPreferences() {
  const [winRate, setWinRate] = useLocalStorage<number>("pref.winRate", 55);
  const [rr, setRR] = useLocalStorage<number>("pref.rr", 1.5);
  const [stopLoss, setStopLoss] = useLocalStorage<number>("pref.stop", 1.0);
  const [takeProfit, setTakeProfit] = useLocalStorage<number>("pref.tp", 2.0);
  const [measuredMove, setMeasuredMove] = useLocalStorage<number>("pref.mm", 1.0);
  const [maxDD, setMaxDD] = useLocalStorage<number>("pref.maxdd", 5.0);
  const [loaded, setLoaded] = useState(false);
  const [saveTick, setSaveTick] = useState(0);

  // Load from server once
  useEffect(() => {
    (async () => {
      try {
        const p = await api.getAutoPrefs();
        if (p && typeof p === 'object') {
          if (p.target_winrate_pct != null) setWinRate(Number(p.target_winrate_pct));
          if (p.target_rr != null) setRR(Number(p.target_rr));
          if (p.stop_loss_pct != null) setStopLoss(Number(p.stop_loss_pct));
          if (p.take_profit_pct != null) setTakeProfit(Number(p.take_profit_pct));
          if (p.measured_move_atr_mult != null) setMeasuredMove(Number(p.measured_move_atr_mult));
          if (p.max_dd_pct != null) setMaxDD(Number(p.max_dd_pct));
        }
      } catch {}
      setLoaded(true);
    })();
  }, []);

  // Auto-save when values change (debounced)
  useEffect(() => {
    if (!loaded) return;
    const id = window.setTimeout(async () => {
      try {
        await api.putAutoPrefs({
          target_winrate_pct: winRate,
          target_rr: rr,
          stop_loss_pct: stopLoss,
          take_profit_pct: takeProfit,
          measured_move_atr_mult: measuredMove,
          max_dd_pct: maxDD,
        });
        setSaveTick((t: number) => t + 1);
      } catch {
        // silent in UI; backend logs
      }
    }, 500);
    return () => window.clearTimeout(id);
  }, [loaded, winRate, rr, stopLoss, takeProfit, measuredMove, maxDD]);
  return (
    <div className="stack">
      <div className="form-row prefs-grid">
        <div>
          <div className="label">Target win rate (%)</div>
          <Num value={winRate} setValue={setWinRate} step={1} min={0} max={100} />
        </div>
        <div>
          <div className="label">Reward ratio (R)</div>
          <Num value={rr} setValue={setRR} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Stop loss (% move)</div>
          <Num value={stopLoss} setValue={setStopLoss} step={0.1} min={0} />
        </div>
      </div>
      <div className="form-row">
        <div>
          <div className="label">Take profit (% move)</div>
          <Num value={takeProfit} setValue={setTakeProfit} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Measured move (ATR x)</div>
          <Num value={measuredMove} setValue={setMeasuredMove} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Max drawdown (%)</div>
          <Num value={maxDD} setValue={setMaxDD} step={0.1} min={0} max={100} />
        </div>
      </div>
    </div>
  );
}








function PreferenceIndicators({ autoStatus }: { autoStatus: any }) {
  // pull targets saved by Trading Preferences
  const getNum = (k: string, def: number) => {
    try { const raw = localStorage.getItem(k); if (!raw) return def; const v = JSON.parse(raw); return (typeof v === "number" ? v : Number(v) || def); }
    catch { const raw = localStorage.getItem(k); const n = Number(raw); return isFinite(n) ? n : def; }
  };
  const T = {
    win: getNum("pref.winRate", 55),
    r:   getNum("pref.rr", 1.5),
    dd:  getNum("pref.maxdd", 5),
  };

  const S = (autoStatus?.stats || {}) as any;
  const V = {
    win: Number.isFinite(S.win_rate_pct) ? Number(S.win_rate_pct) : NaN,
    r:   Number.isFinite(S.avg_r)        ? Number(S.avg_r)        : NaN,
    dd:  Number.isFinite(S.max_dd)       ? Number(S.max_dd)       : NaN,
  };

  type Row = { k: string; unit: string; target: number; value: number; higher: boolean };
  const rows: Row[] = [
    { k: "Win rate",     unit: "%", target: T.win, value: V.win, higher: true  },
    { k: "Reward ratio", unit: "R", target: T.r,   value: V.r,   higher: true  },
    { k: "Drawdown",     unit: "%", target: T.dd,  value: V.dd,  higher: false },
  ];

  const fmt = (v:number, unit:string, decimals=unit==="R"?2:0) =>
    (isFinite(v) ? `${Number(v.toFixed(decimals))}${unit}` : `—${unit}`);

  const Chip = ({ row }: { row: Row }) => {
    const hasLive = isFinite(row.value);
    if (!isFinite(row.target) || row.target === 0) {
      return <span className="delta neutral">target —</span>;
    }
    if (!hasLive) {
      return <span className="delta neutral">target {fmt(row.target, row.unit)}</span>;
    }
    const better = row.higher ? (row.value >= row.target) : (row.value <= row.target);
    const cls = better ? "delta up" : "delta down";
    const arrow = better ? "↑" : "↓";
    return <span className={cls}>{arrow} {fmt(row.value, row.unit)} <span style={{opacity:.8}}>vs {fmt(row.target, row.unit)}</span></span>;
  };

  return (
    <div className="pref-list">
      {rows.map((r,i)=> (
        <div className="pref-row" key={i}>
          <div className="k">{r.k}</div>
          <Chip row={r} />
        </div>
      ))}
    </div>
  );
}

function StyleAndWatchlist() {
  const [styleRaw, setStyleRaw] = useState("");
  const [styleSummary, setStyleSummary] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const s = await api.getAutoStyle();
        setStyleRaw(s?.raw || "");
        setStyleSummary(s?.summary || "");
      } catch {}
    })();
  }, []);

  async function saveStyle() {
    if (!styleRaw.trim()) return;
    try {
      setBusy(true);
      const r = await api.postAutoStyle(styleRaw);
      setStyleSummary(r?.summary || "");
    } finally {
      setBusy(false);
    }
  }

  async function deleteStyle() {
    try {
      setBusy(true);
      await api.deleteAutoStyle();
      setStyleRaw("");
      setStyleSummary("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div style={{flex:1}}>
          <div className="label">Style (natural language)</div>
          <textarea className="input" rows={4} value={styleRaw} onChange={e=>setStyleRaw(e.target.value)} placeholder="Describe your trading preferences, constraints, and style…" />
          <div className="row" style={{justifyContent:"space-between", marginTop:6}}>
            <div className="help">Write preferences like: "Focus on short-term trades, prefer small-caps, avoid biotech."</div>
            <div className="row" style={{gap:8}}>
              <button className="btn" onClick={deleteStyle} disabled={busy || (!styleRaw && !styleSummary)}>Delete Style</button>
              <button className="btn brand" onClick={saveStyle} disabled={busy || !styleRaw.trim()}>Summarize & Save</button>
            </div>
          </div>
        </div>
      </div>
      {styleSummary ? (
        <div className="panel compact" style={{background:"#0e1320"}}>
          <div className="label">Saved Style Summary</div>
          <div className="help" style={{whiteSpace:"pre-wrap"}}>{styleSummary}</div>
        </div>
      ) : null}
    </div>
  );
}

function DiscoverySettings() {
  const [discEnabled, setDiscEnabled] = useState<boolean>(true);
  const [discOnly, setDiscOnly] = useState<boolean>(false);
  const [seed, setSeed] = useState<string>("");
  const [preview, setPreview] = useState<string[]>([]);
  const [newsEnabled, setNewsEnabled] = useState<boolean>(true);
  const [newsTtl, setNewsTtl] = useState<number>(1800);
  const [newsProvider, setNewsProvider] = useState<string>("heuristic");
  const [ktype, setKtype] = useState<string>("K_DAY");
  const [barsTtl, setBarsTtl] = useState<number>(60);
  const [execMode, setExecMode] = useState<"sim"|"moomoo">("sim");
  const [dealsSync, setDealsSync] = useState<number>(180);
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const d = await api.getDiscovery();
      setDiscEnabled(!!d?.enabled);
      setDiscOnly(!!d?.only);
      setSeed(Array.isArray(d?.seed) ? (d?.seed as string[]).join("\n") : "");
      setPreview(Array.isArray(d?.preview) ? d.preview : []);
    } catch {}
    try {
      const n = await api.getNewsSettings();
      setNewsEnabled(!!n?.enabled);
      setNewsTtl(Number(n?.ttl_sec || 1800));
      if (n?.provider) setNewsProvider(String(n.provider));
    } catch {}
    try {
      const dset = await api.getDataSettings();
      setKtype(String(dset?.ktype || "K_DAY"));
      setBarsTtl(Number(dset?.bars_ttl_sec || 60));
      if (dset?.deals_sync_sec != null) setDealsSync(Number(dset.deals_sync_sec));
    } catch {}
    try {
      const em = await api.getExecMode(); setExecMode((em?.mode as any) || "sim");
    } catch {}
  })(); }, []);

  async function saveDiscovery() {
    setSaving(true);
    try {
      const parsed = seed.split(/\n+/).map(s=>s.trim()).filter(Boolean);
      await api.putDiscovery({ enabled: discEnabled, only: discOnly, seed: parsed });
      const d = await api.getDiscovery();
      setPreview(Array.isArray(d?.preview) ? d.preview : []);
    } finally { setSaving(false); }
  }
  async function saveNews() {
    setSaving(true);
    try {
      await api.putNewsSettings({ enabled: newsEnabled, ttl_sec: Number(newsTtl)||1800, provider: newsProvider });
      await api.putDataSettings({ ktype, bars_ttl_sec: Number(barsTtl)||60, deals_sync_sec: Number(dealsSync)||180 });
      await api.putExecMode(execMode);
    } finally { setSaving(false); }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div>
          <div className="label">Discovery Enabled</div>
          <NiceSelect
            value={String(discEnabled)}
            onChange={(v)=>setDiscEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width={140}
          />
        </div>
        <div>
          <div className="label">Dynamic Only (no watchlist)</div>
          <NiceSelect
            value={String(discOnly)}
            onChange={(v)=>setDiscOnly(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width={160}
          />
        </div>
        <div>
          <div className="label">Use News</div>
          <NiceSelect
            value={String(newsEnabled)}
            onChange={(v)=>setNewsEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width={140}
          />
        </div>
        <div>
          <div className="label">News Provider</div>
          <NiceSelect
            value={newsProvider}
            onChange={(v)=>setNewsProvider(v)}
            options={[{value:"heuristic",label:"Heuristic"},{value:"gpt",label:"GPT"}]}
            width={160}
          />
        </div>
        <div>
          <div className="label">News TTL (sec)</div>
          <input className="input" type="number" value={newsTtl} onChange={(e)=>setNewsTtl(parseInt(e.target.value)||1800)} />
        </div>
        <div>
          <div className="label">Timeframe (KType)</div>
          <NiceSelect
            value={ktype}
            onChange={(v)=>setKtype(v as string)}
            options={["K_1M","K_5M","K_15M","K_30M","K_60M","K_DAY"].map(k=>({value:k,label:k}))}
            width={140}
          />
        </div>
        <div>
          <div className="label">Bars cache TTL (sec)</div>
          <input className="input" type="number" value={barsTtl} onChange={(e)=>setBarsTtl(parseInt(e.target.value)||60)} />
        </div>
        <div>
          <div className="label">Execution Backend</div>
          <NiceSelect
            value={execMode}
            onChange={(v)=>setExecMode((v as any) as ("sim"|"moomoo"))}
            options={[{value:"sim",label:"SIM"},{value:"moomoo",label:"Moomoo"}]}
            width={140}
          />
        </div>
        <div>
          <div className="label">Deals sync (sec)</div>
          <input className="input" type="number" value={dealsSync} onChange={(e)=>setDealsSync(parseInt(e.target.value)||180)} />
        </div>
      </div>
      <div className="form-row">
        <div style={{flex:1}}>
          <div className="label">Discovery Seed (US.TICKER per line)</div>
          <textarea className="input" rows={4} value={seed} onChange={(e)=>setSeed(e.target.value)} placeholder={"US.AAPL\nUS.MSFT\nUS.TSLA"} />
        </div>
      </div>
      <div className="row" style={{gap:8, justifyContent:"flex-end"}}>
        <button className="btn" onClick={saveNews} disabled={saving}>Save News</button>
        <button className="btn brand" onClick={saveDiscovery} disabled={saving}>{saving?"Saving…":"Save Discovery"}</button>
      </div>
  <div className="panel compact" style={{background:"#0e1320"}}>
    <div className="label">Preview (Top Candidates)</div>
    <div className="help" style={{whiteSpace:"pre-wrap"}}>{preview?.length ? preview.join(", ") : "—"}</div>
  </div>
  <PlannerSettings />
    </div>
  );
}

function SignalsSettings() {
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => { (async () => {
    try {
      const s = await api.getSignalsSettings();
      setWeights(s?.weights || {});
    } catch {}
    setLoading(false);
  })(); }, []);

  function setWeight(name: string, v: number) {
    setWeights(prev => ({ ...prev, [name]: v }));
  }
  async function save() {
    setSaving(true);
    try {
      await api.putSignalsSettings({ weights });
    } finally { setSaving(false); }
  }

  const stratNames = Object.keys(weights).length ? Object.keys(weights) : ["macd_cross","bb_breakout","stoch_rsi_extreme"];

  return (
    <div className="stack">
      <h3 style={{margin:"4px 0 8px", fontSize:14, color:"var(--muted)", textTransform:"uppercase", letterSpacing:".06em"}}>Signal Weights</h3>
      <div className="table-wrap" style={{marginTop:8}}>
        <table className="table-modern">
          <thead>
            <tr>
              <th>Strategy</th>
              <th className="num" style={{width:160}}>Weight</th>
            </tr>
          </thead>
          <tbody>
            {stratNames.map(name => (
              <tr key={name}>
                <td>{name}</td>
                <td className="num">
                  <input
                    className="input"
                    type="number"
                    step={0.1}
                    min={0}
                    max={2}
                    value={(weights[name] ?? 1.0)}
                    onChange={e=>setWeight(name, Math.max(0, Math.min(2, parseFloat(e.target.value)||0)))}
                    style={{maxWidth:120}}
                  />
                </td>
              </tr>
            ))}
            {!stratNames.length && (
              <tr><td colSpan={2}>No strategies found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="row" style={{marginTop:10, justifyContent:"flex-end"}}>
        <button className="btn brand" onClick={save} disabled={saving || loading}>{saving?"Saving…":"Save Weights"}</button>
      </div>
    </div>
  );
}

function PlannerSettings() {
  const [minConf, setMinConf] = useState<number>(0.6);
  const [topN, setTopN] = useState<number>(8);
  const [strict, setStrict] = useState<boolean>(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const p = await api.getPlannerSettings();
      setMinConf(Number(p?.min_confidence ?? 0.6));
      setTopN(Number(p?.top_n ?? 8));
      setStrict(!!p?.strict_prefs);
    } catch {}
  })(); }, []);

  async function save() {
    setSaving(true);
    try { await api.putPlannerSettings({ min_confidence: minConf, top_n: topN, strict_prefs: strict }); }
    finally { setSaving(false); }
  }

  return (
    <div className="panel compact" style={{marginTop:12}}>
      <h2 style={{marginTop:0}}>Planner</h2>
      <div className="form-row">
        <div>
          <div className="label">Min confidence (0–1)</div>
          <input className="input" type="number" step={0.01} min={0} max={1} value={minConf} onChange={(e)=>setMinConf(parseFloat(e.target.value)||0)} />
        </div>
        <div>
          <div className="label">Top‑N Universe</div>
          <input className="input" type="number" min={1} value={topN} onChange={(e)=>setTopN(parseInt(e.target.value)||8)} />
        </div>
        <div>
          <div className="label">Strict Prefs (require stop/TP)</div>
          <NiceSelect
            value={String(strict)}
            onChange={(v)=>setStrict(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width={140}
          />
        </div>
        <div className="row" style={{alignItems:"flex-end", marginLeft:"auto"}}>
          <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save Planner"}</button>
        </div>
      </div>
    </div>
  );
}
