const DEFAULT_API_BASE = "http://127.0.0.1:8000";
export const API_BASE = (import.meta as any)?.env?.VITE_API_BASE?.toString() || DEFAULT_API_BASE;

type Mode = "automatic" | "manual";

export async function GET<T>(path: string, params?: Record<string, any>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const r = await fetch(url, { credentials: "omit" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

export async function SEND<T>(path: string, body?: any, method: "POST" | "PUT" | "PATCH" | "DELETE" = "POST"): Promise<T> {
  const r = await fetch(new URL(path, API_BASE), {
    method,
    headers: { "Content-Type": "application/json" },
    body: method === "DELETE" ? undefined : (body ? JSON.stringify(body) : undefined),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

const api = {
  connect: (host: string, port: number, client_id: number) => SEND("/connect", { host, port, client_id }),
  accountsActive: () => GET<{ account_id: string | null; trd_env: string | null; account_type?: string | null }>("/accounts/active"),
  selectAccount: (account_id: string) => SEND("/accounts/select", { account_id }),
  unlockTrade: (passcode: string) => SEND("/trade/unlock", { passcode }),
  sessionStatus: () => GET<{ saved: any; connected: boolean; active_account: any }>("/session/status"),
  sessionSave: (host: string, port: number, client_id?: number, account_id?: string, trd_env?: string) => SEND("/session/save", { host, port, client_id, account_id, trd_env }),
  sessionClear: () => SEND("/session/clear", {}),
  getRiskConfig: () => GET<any>("/risk/config"),
  putRiskConfig: (cfg: any) => SEND<any>("/risk/config", cfg, "PUT"),
  getRiskStatus: () => GET<{ ok: boolean; config: any; open_positions: number | null }>("/risk/status"),
  getPnlToday: () => GET<{ date: string; realized_pnl: number }>("/pnl/today"),
  getAccountAssets: () => GET<{ mode:string; equity?: number|null; bp?: number|null; cash?: number|null }>("/accounts/assets"),
  flattenAll: (symbols?: string[]) => SEND("/positions/flatten", symbols?.length ? { symbols } : {}),
  listExecOrders: (q?: { symbol?: string; status?: string; limit?: number; fresh?: boolean }) => GET<any[]>("/exec/orders", q),
  cancelExecOrder: (order_id: string) => SEND(`/exec/orders/${order_id}/cancel`, {}, "POST"),
  listExecTrades: (q?: { symbol?: string; limit?: number }) => GET<any[]>("/exec/fills", q),
  listExecPositions: (q?: { fresh?: boolean }) => GET<any[]>("/exec/positions", q),
  flattenExecPositions: (symbols?: string[]) => SEND("/exec/flatten", symbols?.length ? { symbols } : {}),
  listStrategies: () => GET<Array<{ id: number; name: string; active: boolean; symbol: string }>>("/automation/strategies"),
  stopStrategy: (id: number) => SEND(`/automation/stop/${id}`),
  getActionLogs: (q: { limit?: number; symbol?: string; since_hours?: number }) => GET<any[]>("/logs/actions", q),
  backtestMA: (payload: any) => SEND("/backtest/ma-crossover", payload),
  startMA: (payload: any) => SEND("/automation/start/ma-crossover", payload),
  autopilotStatus: () => GET("/autopilot/status"),
  autopilotEnable: (on: boolean) => SEND("/autopilot/enable", { on }),
  autopilotPreview: () => SEND("/autopilot/preview", {}),
  autopilotLogs: (limit: number) => GET<any[]>("/autopilot/logs", { limit }),
  autopilotContext: () => GET("/autopilot/context"),
  autopilotLastOutput: () => GET("/autopilot/last_output"),
  autopilotLastDiff: () => GET<{ proposed: any[]; kept: any[]; executed: any[]; notes?: string | null }>("/autopilot/last_diff"),
  autopilotWeekly: () => GET("/autopilot/weekly"),
  getAutoPrefs: () => GET<any>("/autopilot/prefs"),
  putAutoPrefs: (prefs: any) => SEND("/autopilot/prefs", prefs, "PUT"),
  getAutoStyle: () => GET<{ raw: string; summary: string }>("/autopilot/style"),
  postAutoStyle: (text: string) => SEND<{ raw: string; summary: string }>("/autopilot/style", { text }),
  deleteAutoStyle: () => SEND<{ raw: string; summary: string }>("/autopilot/style", undefined, "DELETE"),
  getDiscovery: () => GET<{ enabled: boolean; only: boolean; seed: string[]; preview: string[] }>("/autopilot/discovery"),
  putDiscovery: (payload: { enabled?: boolean; only?: boolean; seed?: string[] }) => SEND("/autopilot/discovery", payload, "PUT"),
  getNewsSettings: () => GET<{ enabled: boolean; ttl_sec: number; provider?: string }>("/autopilot/news"),
  putNewsSettings: (payload: { enabled?: boolean; ttl_sec?: number; provider?: string }) => SEND("/autopilot/news", payload, "PUT"),
  getDataSettings: () => GET<{ ktype: string; bars_ttl_sec: number; deals_sync_sec: number; data_source: string }>("/autopilot/data"),
  putDataSettings: (payload: { ktype?: string; bars_ttl_sec?: number; deals_sync_sec?: number; data_source?: string }) => SEND("/autopilot/data", payload, "PUT"),
  getSignalsSettings: () => GET<{ enabled: boolean; strategies: Record<string, boolean>; weights: Record<string, number>; auto_weight?: boolean }>("/autopilot/signals"),
  putSignalsSettings: (payload: Partial<{ enabled: boolean; strategies: Record<string, boolean>; weights: Record<string, number>; auto_weight?: boolean }>) => SEND("/autopilot/signals", payload, "PUT"),
  getExecMode: () => GET<{ mode: "sim"|"moomoo" }>("/execution/mode"),
  putExecMode: (mode: "sim"|"moomoo") => SEND("/execution/mode", { mode }, "PUT"),
  getBotMode: () => GET<{ mode: Mode }>("/bot/mode"),
  setBotMode: (mode: Mode) => SEND<{ mode: Mode }>("/bot/mode", { mode }, "PUT"),
  syncDealsNow: () => SEND("/sync/deals", {}),
  getPlannerSettings: () => GET<{ min_confidence: number; top_n: number; strict_prefs: boolean }>("/autopilot/planner"),
  putPlannerSettings: (payload: { min_confidence?: number; top_n?: number; strict_prefs?: boolean }) => SEND("/autopilot/planner", payload, "PUT"),
  assistantChat: (messages: { role: string; content: string }[], include_context = true) => SEND<{ reply: string }>("/assistant/chat", { messages, include_context }),
  assistantChatLog: (limit = 200) => GET<{ messages: { role: string; content: string }[] }>("/assistant/chat_log", { limit }),
  getStyleLines: () => GET<{ lines: string[] }>("/assistant/style_lines"),
  addStyleLines: (add: string[]) => SEND<{ lines: string[] }>("/assistant/style_lines", { add }),
  deleteStyleLines: (payload: { indexes?: number[]; texts?: string[] }) => SEND<{ lines: string[] }>("/assistant/style_lines", payload, "DELETE"),
  setStyleSummary: (text: string) => SEND<{ style_summary: string }>("/assistant/style_summary", { text }, "PUT"),
  getPnlSeries: (days=30) => GET<{ series: { date: string; realized_pnl: number }[] }>("/autopilot/pnl_series", { days }),
};

export default api;
