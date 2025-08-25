// desktop/app/src/App.tsx
// Desktop UI (Tauri + React) with Connection panel, Strategies Catalog (presets + start), richer Status/Logs,
// and Backtest with friendly 400 errors (missing bars file hint).
// API base comes from VITE_API_BASE (defaults to http://127.0.0.1:8000)

import { useEffect, useRef, useState } from "react";
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
.app{max-width:1180px;margin:0 auto;padding:18px 20px 28px}
.header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
.title{display:flex;align-items:center;gap:12px}
.badge{font-size:12px;color:var(--text-dim);background:linear-gradient(135deg, rgba(124,58,237,.25), rgba(6,182,212,.25));
  border:1px solid rgba(124,58,237,.35);padding:4px 8px;border-radius:999px}
.tabs{display:flex;gap:8px;margin:8px 0 18px}
.tab{padding:8px 12px;border-radius:8px;background:var(--panel);color:var(--text-dim);
  border:1px solid var(--border);cursor:pointer;transition:.18s ease}
.tab:hover{background:var(--hover)}
.tab.active{color:var(--text);background:linear-gradient(180deg, rgba(124,58,237,.25), rgba(6,182,212,.25));border-color:rgba(124,58,237,.45)}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media (max-width:900px){.grid-3{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}
.card h3{margin:0 0 6px;font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.card .value{font-size:20px;font-weight:600}
.row{display:flex;gap:12px;flex-wrap:wrap}
.stack{display:grid;gap:10px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:8px 12px;border-radius:10px;border:1px solid var(--border);
  background:#0e1320;color:var(--text);cursor:pointer;transition:transform .04s ease, background .18s ease;user-select:none}
.btn[disabled]{opacity:.55;cursor:not-allowed}
.btn:hover{background:var(--hover)} .btn:active{transform:translateY(1px)}
.btn.brand{background:linear-gradient(180deg, rgba(124,58,237,.5), rgba(6,182,212,.4));border-color:rgba(124,58,237,.5)}
.btn.red{background:linear-gradient(180deg, rgba(239,68,68,.25), rgba(239,68,68,.15));border-color:rgba(239,68,68,.4)}
.btn.amber{background:linear-gradient(180deg, rgba(245,158,11,.25), rgba(245,158,11,.15));border-color:rgba(245,158,11,.4)}
.input,.select{width:100%;padding:8px 10px;border-radius:8px;background:#0c111b;color:var(--text);border:1px solid var(--border);outline:none;transition:border-color .18s}
.input:focus,.select:focus{border-color:rgba(124,58,237,.6)}

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
.table-wrap{overflow:auto;border-radius:10px;border:1px solid var(--border); position: relative;}
table{width:100%;border-collapse:collapse;background:var(--panel)}
th,td{padding:8px 10px;border-top:1px solid var(--border)} th{text-align:left;font-size:12px;color:var(--muted);background:#0f1420;position:sticky;top:0;z-index:1}
tr:hover td{background:rgba(124,58,237,.08)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px} @media (max-width:900px){.kpis{grid-template-columns:1fr}}
.help{color:var(--muted);font-size:12px}
.toast{position:fixed;right:16px;bottom:16px;padding:10px 12px;border-radius:10px;background:#0e1320;border:1px solid var(--border);color:var(--text);box-shadow:0 10px 30px rgba(0,0,0,.35);max-width:360px}
small.code{font-family:ui-monospace, SFMono-Regular, Menlo, monospace;background:rgba(124,58,237,.18);padding:2px 6px;border-radius:6px}

.indicator{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;border:1px solid var(--border);background:#0e1320}
.dot{width:8px;height:8px;border-radius:50%}
.dot.green{background:var(--green)} .dot.red{background:var(--red)}
.header-quick{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;min-width:320px}

.sticky-controls{position: sticky; top: 0; background: #0f1420; padding: 6px 0; z-index: 2; border-bottom: 1px solid var(--border);}
.note{font-size:12px;color:var(--muted)}

/* indicator font tweak */
.indicator{font-size:12px;font-weight:600}

.header, .title, .header-quick{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial }

.grid-2{display:grid;grid-template-columns:2fr 1fr;gap:12px}
@media (max-width:980px){.grid-2{grid-template-columns:1fr}}
.panel.thick{padding:22px}
/* Autopilot switch (solid color) */
.switch-lg{position:relative;width:60px;height:30px;border-radius:999px;background:#334155;border:1px solid #475569;display:inline-flex;align-items:center;transition:background .18s ease,border-color .18s ease}
.switch-lg .thumb{position:absolute;left:3px;width:24px;height:24px;border-radius:999px;background:#0b1220;box-shadow:0 6px 16px rgba(0,0,0,.35);transition:transform .2s ease, background .2s ease}
.switch-lg.on{background:#22a6f2;border-color:#22a6f2}
.switch-lg.on .thumb{transform:translateX(30px);background:#ffffff}
.help.strong{font-weight:600;color:var(--text)}

/* Align with KPI 3-column track; panels span to align edges */
.panels3{display:grid;grid-template-columns:repeat(3, minmax(0,1fr));gap:12px}
.panels3 .span-2{grid-column:span 2 / span 2}
@media (max-width:980px){.panels3{grid-template-columns:1fr}.panels3 .span-2{grid-column:auto}}

/* Fixed gradient overlay to avoid scroll seams */
.bgfx{position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(1200px 600px at 20% -10%, rgba(139,92,246,.12), transparent 60%),
    radial-gradient(1000px 500px at 100% 0%, rgba(34,211,238,.10), transparent 60%);
}`;

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
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch {}
  }, [key, v]);
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
async function SEND<T>(path: string, body?: any, method: "POST" | "PUT" | "PATCH" = "POST"): Promise<T> {
  const r = await fetch(new URL(path, API_BASE), {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}
const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));
const nowIso = () => new Date().toLocaleTimeString();

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
  autopilotLogs: (limit: number) => GET("/autopilot/logs", { limit }),
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
enum Tab { Settings=0, Status=1, Activity=2, Backtest=3 }

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
  const [exTab, setExTab] = useLocalStorage<"orders"|"fills">("exec.tab", "orders");
  const [exSymbol, setExSymbol] = useLocalStorage("exec.symbol", "");
  const [exAuto, setExAuto] = useLocalStorage("exec.auto", true);
  const [exEvery, setExEvery] = useLocalStorage("exec.ms", 5000);
  const [exAt, setExAt] = useState<string>("—");
  const [orders, setOrders] = useState<any[]>([]);
  const [fills, setFills] = useState<any[]>([]);
  const [exLoading, setExLoading] = useState(false);
  // positions (SIM)
  const [posSymbol, setPosSymbol] = useLocalStorage("pos.symbol", "");
  const [posAuto, setPosAuto] = useLocalStorage("pos.auto", true);
  const [posEvery, setPosEvery] = useLocalStorage("pos.ms", 5000);
  const [posAt, setPosAt] = useState<string>("—");
  const [positions, setPositions] = useState<any[]>([]);
  const [posLoading, setPosLoading] = useState(false);



  // initial: load session + mode + risk
  useEffect(() => {
    (async () => {
      try {
        const st = await api.sessionStatus();
        setConnected(!!st.connected);
        setActiveAccount(st.active_account || null);
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
    if (!logsAuto || tab !== Tab.Activity) return;
    const id = window.setInterval(() => refreshLogs(false), logsEvery);
    return () => window.clearInterval(id);
  }, [logsAuto, tab, logsEvery, logSymbol, logSince, logLimit]);

  useEffect(() => {
    if (!exAuto || tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshExec(false), exEvery);
    return () => window.clearInterval(id);
  }, [exAuto, tab, exEvery, exSymbol, exTab]);
  useEffect(() => {
    if (!posAuto || tab !== Tab.Status) return;
    const id = window.setInterval(() => refreshPositions(false), posEvery);
    return () => window.clearInterval(id);
  }, [posAuto, tab, posEvery, posSymbol]);



  
  async function refreshExec(show = true) {
    try {
      setExLoading(true);
      if (exTab === "orders") {
        const q: any = {};
        if (exSymbol) q.symbol = exSymbol;
        setOrders(await api.listExecOrders(q));
      } else {
        const q: any = {};
        if (exSymbol) q.symbol = exSymbol;
        setFills(await api.listExecFills(q));
      }
      setExAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Exec refresh failed: ${brief(e)}`);
    } finally {
      setExLoading(false);
    }
  }
  
async function refreshPositions(show = true) {
    try {
      setPosLoading(true);
      const data = await api.listExecPositions({});
      let arr: any[] = data || [];
      if (posSymbol) {
        const q = String(posSymbol).toLowerCase();
        arr = arr.filter((r:any) => String(r?.symbol || "").toLowerCase().includes(q));
      }
      setPositions(arr);
      setPosAt(nowIso());
    } catch (e:any) {
      show && toast.show(`Positions refresh failed: ${brief(e)}`);
    } finally {
      setPosLoading(false);
    }
  }
  async function flattenSymbol(sym: string) {
    try {
      await api.flattenExecPositions([sym]);
      toast.show(`Flattened ${sym}`);
      refreshPositions(false);
      refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten failed: ${brief(e)}`);
    }
  }
  async function flattenVisible() {
    try {
      const syms = (positions || []).map((p:any) => p.symbol);
      if (!syms.length) { toast.show("No positions."); return; }
      await api.flattenExecPositions(syms);
      toast.show(`Flattened ${syms.length} symbol(s)`);
      refreshPositions(false);
      refreshExec(false);
    } catch (e:any) {
      toast.show(`Flatten-all failed: ${brief(e)}`);
    }
  }
async function cancelOrder(id: string) {
    try {
      await api.cancelExecOrder(id);
      toast.show("Cancel sent.");
      refreshExec(false);
    } catch (e:any) {
      toast.show(`Cancel failed: ${brief(e)}`);
    }
  }
async function refreshStatus(show = true) {
    try {
      setStatusLoading(true);
      const [rs, pt] = await Promise.all([api.getRiskStatus(), api.getPnlToday()]);
      setOpenPositions(rs.open_positions ?? null);
      setPnl(pt.realized_pnl ?? null);
      setStatusAt(nowIso());
    } catch (e: any) {
      show && toast.show(`Status refresh failed: ${brief(e)}`);
    } finally {
      setStatusLoading(false);
    }
  }

  async function refreshLogs(show = true) {
  try {
    setLogsLoading(true);
    let ls: any[] = [];
    if (logsSource === "autopilot") {
      ls = await api.autopilotLogs(logLimit) as any[];
    } else {
      ls = await api.getActionLogs({ limit: logLimit, symbol: logSymbol || undefined, since_hours: logSince });
    }
    setLogs(ls || []);
    setLogsAt(nowIso());
  } catch (e: any) {
    show && toast.show(`Logs refresh failed: ${brief(e)}`);
  } finally {
    setLogsLoading(false);
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

// ---------- Render ----------
  return (
    <div className="app">
      <div className="bgfx" aria-hidden="true"></div>
      <style>{css}</style>

      <header className="header">
        <div className="title">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M3 12c0-4.97 4.03-9 9-9 1.88 0 3.63.57 5.08 1.55L12 12l-7.55 5.08A8.96 8.96 0 0 1 3 12Z" fill="url(#g1)"/>
            <path d="M21 12a9 9 0 0 1-14.63 7.08L12 12l7.08-5.63C20.42 7.37 21 9.12 21 12Z" fill="url(#g2)"/>
            <defs>
              <linearGradient id="g1" x1="3" y1="3" x2="21" y2="21"><stop stopColor="#7c3aed"/><stop offset="1" stopColor="#06b6d4"/></linearGradient>
              <linearGradient id="g2" x1="3" y1="3" x2="21" y2="21"><stop stopColor="#06b6d4"/><stop offset="1" stopColor="#7c3aed"/></linearGradient>
            </defs>
          </svg>
          <div>
            <div style={{fontSize:24,fontWeight:800}}>Moomoo ChatGPT Trading Bot</div>
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
          <span className="indicator" title="Bot Mode"><span>Bot mode: {mode==="automatic" ? "Automatic" : "Manual"}</span></span>
        </div>
      </header>

      <nav className="tabs">
        {["Settings","Bot Status","Activity Log","Backtest"].map((t,i)=>(
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

          {/* Strategies Catalog */}
          <StrategyCatalog connected={connected} />
        </section>
      )}

      
      {/* ===== Bot Status ===== */}
      {tab===Tab.Status && (
        <section className="stack">
          {/* KPIs */}
          <div className="grid-3">
            <div className="card"><h3>Connection</h3><div className="value">{connected ? "CONNECTED" : "NOT CONNECTED"}</div></div>
            <div className="card"><h3>Open Positions</h3><div className="value">{openPositions ?? "—"}</div></div>
            <div className="card"><h3>Realized PnL (Today)</h3>
              <div className="value" style={{color: pnl==null ? "inherit" : pnl>=0 ? "var(--green)" : "var(--red)"}}>
                {pnl ?? "—"}
              </div>
            </div>
          </div>

          {/* Controls + Autopilot */}
          <div className="grid-3 panels3">
            <div className="panel thick span-2">
              <div className="row" style={{justifyContent:"space-between", alignItems:"center"}}>
                <h2 style={{margin:0}}>Controls</h2>
                <div className="note">Last updated: {statusAt}</div>
              </div>
              <div className="row" style={{marginTop:14}}>
                <button className="btn red" onClick={killSwitch}>Kill Switch (Stop Strategies)</button>
                <button className="btn amber" onClick={doFlattenAll} disabled={!connected}>Flatten All Now</button>
                <button className="btn" onClick={()=>refreshStatus(true)}>{statusLoading?"Refreshing…":"Refresh"}</button>
                <label style={{display:"flex",alignItems:"center",gap:8,marginLeft:"auto"}}>
                  <input type="checkbox" checked={autoRefresh} onChange={e=>setAutoRefresh(e.target.checked)} /> Auto-refresh
                </label>
                <NiceSelect
                  value={String(statusEvery)}
                  onChange={(v)=>setStatusEvery(Number(v))}
                  options={[
                    { value: "3000", label: "3s" },
                    { value: "5000", label: "5s" },
                    { value: "10000", label: "10s" },
                    { value: "30000", label: "30s" },
                  ]}
                  width={120}
                />
              </div>
            </div>

            <div className="panel">
              <h2 style={{marginTop:0,marginBottom:10}}>Autopilot</h2>
              <div className="row" style={{alignItems:"center", gap:12, marginTop:14}}>
                <button
                  className={`switch-lg ${mode==="automatic" ? "on" : ""}`}
                  role="switch"
                  aria-checked={mode==="automatic"}
                  onClick={async()=> {
                    const turnOn = !(mode==="automatic");
                    try { await api.autopilotEnable(turnOn); }
                    catch(e:any) { toast.show(`Autopilot toggle failed: ${brief(e)}`); }
                    setBotMode(turnOn ? "automatic" : "manual");
                  }}
                  title="Toggle Autopilot On/Off"
                >
                  <span className="thumb" />
                </button>
                <div className="help strong">{mode==="automatic" ? "On" : "Off"}</div>
                <button
                  className="btn brand"
                  style={{marginLeft:"auto"}}
                  onClick={doPreview}
                  disabled={previewLoading}
                  title="Run a dry-run tick (no orders)"
                >
                  {previewLoading ? "Running Preview…" : "Preview Decisions"}
                </button>
              </div>
              <div className="help" aria-live="polite" style={{marginTop:6}}>
                {mode==="automatic" ? "Autopilot is running" : "Autopilot is off"}
                {autoStatus ? ` • Last tick: ${autoStatus.last_tick || "—"} • Reject streak: ${autoStatus.reject_streak || 0}` : ""}
              </div>
            </div>
          </div>

          {/* Active strategies */}
          <div className="panel">
            <h2 style={{marginTop:0,marginBottom:10}}>Active Strategies</h2>
            <ActiveStrategies
              refreshKey={stratRefreshTick}
              onStopped={() => setStratRefreshTick(t => t + 1)}
            />
          </div>

          {/* Positions (SIM) – its own panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center"}}>
              <h2 style={{margin:0}}>Positions (SIM)</h2>
              <div className="note">Last updated: {posAt}</div>
            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:8}}>
              <div style={{minWidth:180}}>
                <div className="label">Filter symbol</div>
                <input className="input" value={posSymbol} onChange={e=>setPosSymbol(e.target.value)} placeholder="US.AAPL (optional)" />
              </div>
              <button className="btn" onClick={()=>refreshPositions(true)}>{posLoading ? "Refreshing…" : "Refresh"}</button>
              <label style={{display:"flex",alignItems:"center",gap:8, marginLeft:"auto"}}>
                <input type="checkbox" checked={posAuto} onChange={e=>setPosAuto(e.target.checked)} /> Auto
              </label>
              <NiceSelect
                value={String(posEvery)}
                onChange={(v)=>setPosEvery(Number(v))}
                options={[
                  { value: "3000", label: "3s" },
                  { value: "5000", label: "5s" },
                  { value: "10000", label: "10s" },
                  { value: "30000", label: "30s" },
                ]}
                width={120}
              />
              <button className="btn amber" onClick={()=>flattenVisible()} title="Flatten all visible positions">Flatten Visible</button>
            </div>
            <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
              <table>
                <thead>
                  <tr>{"symbol qty avg last mv upl rpl_today actions".split(" ").map(h=>(<th key={h}>{h}</th>))}</tr>
                </thead>
                <tbody>
                  {(positions||[]).filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase())).length ?
                    (positions||[]).filter(p=>!posSymbol || String(p.symbol||"").toLowerCase().includes(String(posSymbol).toLowerCase())).map((p:any)=>(
                      <tr key={p.symbol}>
                        <td>{p.symbol}</td>
                        <td>{p.qty}</td>
                        <td>{p.avg_cost?.toFixed ? p.avg_cost.toFixed(2) : p.avg_cost}</td>
                        <td>{p.last==null ? "" : (p.last?.toFixed ? p.last.toFixed(2) : p.last)}</td>
                        <td>{p.mv==null ? "" : (p.mv?.toFixed ? p.mv.toFixed(2) : p.mv)}</td>
                        <td style={{color: p.upl==null ? "inherit" : (p.upl>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.upl==null ? "" : (p.upl?.toFixed ? p.upl.toFixed(2) : p.upl)}
                        </td>
                        <td style={{color: p.rpl_today==null ? "inherit" : (p.rpl_today>=0 ? "var(--green)" : "var(--red)")}}>
                          {p.rpl_today==null ? "" : (p.rpl_today?.toFixed ? p.rpl_today.toFixed(2) : p.rpl_today)}
                        </td>
                        <td><button className="btn red" onClick={()=>flattenSymbol(p.symbol)}>Flatten</button></td>
                      </tr>
                    ))
                  : <tr><td>No positions.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="help" style={{marginTop:8}}>SIM pricing uses most recent fill as last; flatten sends MARKET orders opposite to current qty.</div>
          </div>

          {/* Orders & Fills (SIM) – separate panel */}
          <div className="panel">
            <div className="row" style={{justifyContent:"space-between", alignItems:"center"}}>
              <h2 style={{margin:0}}>Orders & Fills (SIM)</h2>
              <div className="note">Last updated: {exAt}</div>
            </div>
            <div className="row" style={{alignItems:"end", gap:12, marginTop:8}}>
              <div className="row" style={{gap:8}}>
                <button className="btn" onClick={()=>setExTab("orders")} disabled={exTab==="orders"}>Orders</button>
                <button className="btn" onClick={()=>setExTab("fills")} disabled={exTab==="fills"}>Fills</button>
              </div>
              <div style={{minWidth:180}}>
                <div className="label">Symbol (optional)</div>
                <input className="input" value={exSymbol} onChange={e=>setExSymbol(e.target.value)} placeholder="US.AAPL" />
              </div>
              <button className="btn" onClick={()=>refreshExec(true)}>{exLoading?"Refreshing…":"Refresh"}</button>
              <label style={{display:"flex",alignItems:"center",gap:8, marginLeft:"auto"}}>
                <input type="checkbox" checked={exAuto} onChange={e=>setExAuto(e.target.checked)} /> Auto
              </label>
              <NiceSelect
                value={String(exEvery)}
                onChange={(v)=>setExEvery(Number(v))}
                options={[
                  { value: "3000", label: "3s" },
                  { value: "5000", label: "5s" },
                  { value: "10000", label: "10s" },
                  { value: "30000", label: "30s" },
                ]}
                width={120}
              />
            </div>

            {exTab === "orders" ? (
              <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
                <table>
                  <thead>
                    <tr>
                      {["created_at","order_id","symbol","side","type","tif","status","req_qty","filled","avg","limit","actions"].map(h=>(
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {orders?.length ? orders
                      .filter((o:any)=>!exSymbol || String(o.symbol||"").toLowerCase().includes(String(exSymbol).toLowerCase()))
                      .map((o:any)=>(
                      <tr key={o.order_id}>
                        <td className="small">{o.created_at}</td>
                        <td className="small">{o.order_id}</td>
                        <td>{o.symbol}</td>
                        <td>{o.side}</td>
                        <td>{o.order_type}</td>
                        <td>{o.tif}</td>
                        <td>{o.status}</td>
                        <td>{o.requested_qty}</td>
                        <td>{o.filled_qty}</td>
                        <td>{o.avg_fill_price==null ? "" : o.avg_fill_price}</td>
                        <td>{o.limit_price==null ? "" : o.limit_price}</td>
                        <td>
                          <button className="btn red" disabled={o.status!=="open" && o.status!=="pending"} onClick={()=>cancelOrder(o.order_id)}>Cancel</button>
                        </td>
                      </tr>
                    )) : <tr><td>No orders yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="table-wrap" style={{maxHeight: 360, marginTop: 10}}>
                <table>
                  <thead>
                    <tr>
                      {["ts","fill_id","order_id","symbol","qty","price"].map(h=>(
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fills?.length ? fills
                      .filter((f:any)=>!exSymbol || String(f.symbol||"").toLowerCase().includes(String(exSymbol).toLowerCase()))
                      .map((f:any)=>(
                      <tr key={f.fill_id}>
                        <td className="small">{f.ts}</td>
                        <td className="small">{f.fill_id}</td>
                        <td className="small">{f.order_id}</td>
                        <td>{f.symbol}</td>
                        <td>{f.qty}</td>
                        <td>{f.price}</td>
                      </tr>
                    )) : <tr><td>No fills yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ===== Activity Log ===== */}
      {tab===Tab.Activity && (<>
  <div className="row" style={{marginBottom:8, gap:8}}>
    <span className="label">Source</span>
    <button className="btn" onClick={()=>setLogsSource("system")} disabled={logsSource==="system"}>System</button>
    <button className="btn" onClick={()=>setLogsSource("autopilot")} disabled={logsSource==="autopilot"}>Autopilot</button>
  </div>
  <ActivityLog logs={logs} logsAt={logsAt} logsEvery={logsEvery} setLogsEvery={setLogsEvery}
               logsAuto={logsAuto} setLogsAuto={setLogsAuto}
               logSymbol={logSymbol} setLogSymbol={setLogSymbol}
               logSince={logSince} setLogSince={setLogSince}
               logLimit={logLimit} setLogLimit={setLogLimit}
               refreshLogs={()=>refreshLogs(true)} logsLoading={logsLoading} />
</>)}

      {/* ===== Backtest ===== */}
      {tab===Tab.Backtest && <BacktestPanel />}

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
    setStratRefreshTick(t=>t+1);
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

async function setBotMode(next: Mode) {
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
  refreshLogs: () => void; logsLoading: boolean;
}) {
  const { logs, logsAt, logsEvery, setLogsEvery, logsAuto, setLogsAuto,
          logSymbol, setLogSymbol, logSince, setLogSince, logLimit, setLogLimit,
          refreshLogs, logsLoading } = props;

  return (
    <section className="stack">
      <div className="panel">
        <div className="sticky-controls">
          <div className="row" style={{alignItems:"end",marginBottom:4}}>
            <div><div className="label">Symbol (optional)</div><input className="input" value={logSymbol} onChange={e=>setLogSymbol(e.target.value)} placeholder="US.AAPL" /></div>
            <div><div className="label">Since (hours)</div><input className="input" type="number" value={logSince} onChange={e=>setLogSince(Number(e.target.value)||24)} /></div>
            <div><div className="label">Limit</div><input className="input" type="number" value={logLimit} onChange={e=>setLogLimit(Number(e.target.value)||200)} /></div>
            <div className="row">
              <button className="btn" onClick={refreshLogs}>{logsLoading?"Refreshing…":"Refresh Logs"}</button>
              <label style={{display:"flex",alignItems:"center",gap:8}}>
                <input type="checkbox" checked={logsAuto} onChange={e=>setLogsAuto(e.target.checked)} /> Auto
              </label>
              <NiceSelect
                value={String(logsEvery)}
                onChange={(v)=>setLogsEvery(Number(v))}
                options={[
                  { value: "4000", label: "4s" },
                  { value: "6000", label: "6s" },
                  { value: "10000", label: "10s" },
                  { value: "30000", label: "30s" },
                ]}
                width={120}
              />
              <button className="btn" onClick={()=>exportCsv(logs)}>Export CSV</button>
            </div>
            <div className="note" style={{marginLeft:"auto"}}>Last updated: {logsAt}</div>
          </div>
        </div>

        <div className="table-wrap" style={{maxHeight: 460}}>
          <table>
            <thead><tr>{["ts","mode","action","symbol","side","qty","price","reason","status"].map(h=><th key={h}>{h}</th>)}</tr></thead>
            <tbody>
              {logs.length ? logs.map((r:any)=>(
                <tr key={r.id ?? `${r.ts}-${Math.random()}`}>
                  <td>{r.ts ?? ""}</td><td>{r.mode ?? ""}</td><td>{r.action ?? ""}</td>
                  <td>{r.symbol ?? ""}</td><td>{r.side ?? ""}</td><td>{r.qty ?? ""}</td>
                  <td>{r.price ?? ""}</td><td>{r.reason ?? ""}</td><td>{r.status ?? ""}</td>
                </tr>
              )) : <tr><td>No log entries yet.</td></tr>}
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
      setItems(ls || []);
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

function BacktestPanel() {
  const [symbol, setSymbol] = useState("US.AAPL");
  const [fast, setFast] = useState(20);
  const [slow, setSlow] = useState(50);
  const [ktype, setKType] = useState("K_1M");
  const [qty, setQty] = useState(1);
  const [sizeMode, setSizeMode] = useState<"shares"|"usd">("shares");
  const [dollarSize, setDollarSize] = useState(0);
  const [sl, setSL] = useState(0);
  const [tp, setTP] = useState(0);
  const [comm, setComm] = useState(0);
  const [slip, setSlip] = useState(0);
  const [res, setRes] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // derive the expected bars filename the server uses (ticker sans prefix + ktype)
  const ticker = symbol.includes(".") ? symbol.split(".").pop()!.toUpperCase() : symbol.toUpperCase();
  const expectedFile = `data/bars/${ticker}_${ktype}.csv`;

  async function run() {
    setErr(null);
    setRes(null);
    try {
      setRunning(true);
      const payload = {
        symbol, fast, slow, ktype, qty, size_mode: sizeMode, dollar_size: dollarSize,
        stop_loss_pct: sl, take_profit_pct: tp, commission_per_share: comm, slippage_bps: slip
      };
      const r = await SEND("/backtest/ma-crossover", payload);
      setRes(r);
    } catch (e:any) {
      const msg = tryParseError(e);
      setErr(msg);
    } finally { setRunning(false); }
  }

  return (
    <section className="stack">
      <div className="panel">
        <div className="row" style={{justifyContent:"space-between", alignItems:"center"}}>
          <h2 style={{margin:0}}>MA Crossover Backtest</h2>
          <div className="note">{res ? "Results below" : "Configure and run"}</div>
        </div>

        <div className="form-row">
          <div><div className="label">Symbol</div><input className="input" value={symbol} onChange={e=>setSymbol(e.target.value)} /></div>
          <div><div className="label">Fast MA</div><input className="input" type="number" value={fast} onChange={e=>setFast(parseInt(e.target.value)||1)} /></div>
          <div><div className="label">Slow MA</div><input className="input" type="number" value={slow} onChange={e=>setSlow(parseInt(e.target.value)||2)} /></div>
        </div>
        <div className="form-row">
          <div><div className="label">KType</div>
            <NiceCombobox
              value={ktype}
              onChange={setKType}
              options={["K_1M","K_5M","K_15M","K_30M","K_60M","K_1D"].map(k=>({value:k,label:k}))}
              width={180}
              placeholder="Search ktype…"
            />
          </div>
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
          <div><div className="label">Stop Loss %</div><input className="input" type="number" step="0.0001" value={sl} onChange={e=>setSL(parseFloat(e.target.value)||0)} /></div>
          <div><div className="label">Take Profit %</div><input className="input" type="number" step="0.0001" value={tp} onChange={e=>setTP(parseFloat(e.target.value)||0)} /></div>
        </div>
        <div className="form-row">
          <div><div className="label">Commission / share</div><input className="input" type="number" step="0.0001" value={comm} onChange={e=>setComm(parseFloat(e.target.value)||0)} /></div>
          <div><div className="label">Slippage (bps)</div><input className="input" type="number" value={slip} onChange={e=>setSlip(parseFloat(e.target.value)||0)} /></div>
        </div>
        <div className="row" style={{marginTop:10}}>
          <button className="btn brand" onClick={run} disabled={running}>{running?"Running…":"Run Backtest"}</button>
        </div>

        {err && (
          <div className="panel" style={{marginTop:12, borderColor:"rgba(239,68,68,.45)", background:"linear-gradient(90deg, rgba(239,68,68,.08), transparent)"}}>
            <div style={{fontWeight:600, marginBottom:6}}>Backtest failed</div>
            <div style={{whiteSpace:"pre-wrap"}}>{err}</div>
            <div className="help" style={{marginTop:6}}>
              If this mentions a missing bars file, create it at <code>{expectedFile}</code>.
              (Ticker uses the part after the dot, e.g., <code>US.AAPL → AAPL</code>.)
            </div>
          </div>
        )}

        {!!res && (
          <div className="stack" style={{marginTop:12}}>
            <div className="card"><h3>Metrics</h3><pre style={{margin:0,whiteSpace:"pre-wrap"}}>{JSON.stringify(res.metrics ?? res, null, 2)}</pre></div>
            {res.trades_sample && (
              <div className="table-wrap">
                <table>
                  <thead><tr>{["entry_ts","exit_ts","side","entry_px","exit_px","qty","pnl"].map(h=><th key={h}>{h}</th>)}</tr></thead>
                  <tbody>
                    {res.trades_sample.map((t:any,i:number)=>(
                      <tr key={i}><td>{t.entry_ts}</td><td>{t.exit_ts}</td><td>{t.side}</td>
                      <td>{t.entry_px}</td><td>{t.exit_px}</td><td>{t.qty}</td><td>{t.pnl}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );

  function tryParseError(e:any) {
    try {
      const j = JSON.parse(String(e?.message || e));
      return j?.detail || j?.message || String(e);
    } catch {
      return e?.message || String(e);
    }
  }
}