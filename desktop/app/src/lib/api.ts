import type { Mode, RiskConfig } from "../types";

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
export const API_BASE = (import.meta as any)?.env?.VITE_API_BASE?.toString() || DEFAULT_API_BASE;

/** GET wrapper */
export async function GET<T>(path: string, params?: Record<string, any>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const r = await fetch(url, { credentials: "omit" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

/** POST/PUT/PATCH wrapper */
export async function SEND<T>(path: string, body?: any, method: "POST" | "PUT" | "PATCH" = "POST"): Promise<T> {
  const r = await fetch(new URL(path, API_BASE), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

/** API bindings */
export const api = {
  // connection
  connect: (host: string, port: number, client_id: number) => SEND("/connect", { host, port, client_id }),
  accountsActive: () => GET<{ account_id: string | null; trd_env: string | null }>("/accounts/active"),
  selectAccount: (account_id: string, trd_env: "SIMULATE" | "REAL") => SEND("/accounts/select", { account_id, trd_env }),

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

  startMA: (payload: any) => SEND("/automation/start/ma-crossover", payload),
  autopilotStatus: () => GET("/autopilot/status"),
  autopilotEnable: (on: boolean) => SEND("/autopilot/enable", { on }),
  autopilotPreview: () => SEND("/autopilot/preview", {}),
  autopilotLogs: (limit: number) => GET("/autopilot/logs", { limit }),
  listExecOrders: (q: { symbol?: string; status?: string; limit?: number }) => GET<any[]>("/exec/orders", q),
  cancelExecOrder: (id: string) => SEND(`/exec/orders/${id}/cancel`, {}, "POST"),
  listExecFills: (q: { symbol?: string; limit?: number }) => GET<any[]>("/exec/fills", q),
  listExecPositions: (q?: { symbol?: string; limit?: number }) => GET<any[]>("/exec/positions", q || {}),
  flattenExecPositions: (symbols?: string[]) => SEND("/exec/flatten", symbols?.length ? { symbols } : {}),
};

