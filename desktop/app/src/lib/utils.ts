/** Ask for confirmation */
export async function askConfirm(message: string) {
  const g = window as any;
  try {
    if (g.__TAURI__?.dialog?.confirm) {
      return await g.__TAURI__.dialog.confirm(message, { title: "Confirm", type: "warning" });
    }
  } catch {}
  return window.confirm(message);
}

/** Pause for a number of milliseconds */
export const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));

/** Time string helper */
export const nowIso = () => new Date().toLocaleTimeString();

/** Short error text */
export function brief(err: any) {
  return String(err?.message || err);
}
