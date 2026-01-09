
/* desktop/app/src/hooks/useAutopilot.ts */
export type AutoStatus = { on: boolean; last_tick?: string|null; stats?: any; last_decision?: any; reject_streak?: number };
const BASE = (import.meta as any)?.env?.VITE_API_BASE?.toString() || "http://127.0.0.1:8000";

async function GET<T>(path: string): Promise<T> {
  const r = await fetch(new URL(path, BASE));
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}
async function SEND<T>(path: string, body: any): Promise<T> {
  const r = await fetch(new URL(path, BASE), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

export const useAutopilot = {
  status: () => GET<AutoStatus>("/autopilot/status"),
  enable: (on: boolean) => SEND<AutoStatus>("/autopilot/enable", { on }),
  preview: () => SEND<any>("/autopilot/preview", {}),
};
