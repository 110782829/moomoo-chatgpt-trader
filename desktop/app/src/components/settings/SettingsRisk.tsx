import { useState } from "react";
import { NiceSelect } from "../../App";
import api from "../../api";

// Lock icon
function LockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--muted)" }}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

// Open lock icon
function UnlockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--muted)" }}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 9-3" />
    </svg>
  );
}

export default function SettingsRisk({ cfg, setCfg, cfgGet, saveRisk, saving, toast }: any) {
  const [code, setCode] = useState("");
  const [unlocked, setUnlocked] = useState(false); // lock state
  async function unlock() {
    try {
      await api.unlockTrade(code);
      toast?.show?.("Trade unlocked.");
      setCode("");
      setUnlocked(true);
    } catch (e: any) {
      toast?.show?.(String(e));
    }
  }
  if (!cfg) return <div className="help">Loading risk config…</div>;
  return (
    <>
      <div className="form-row">
        <div><div className="label">Enabled</div>
          <NiceSelect
            value={String(cfgGet("enabled", true))}
            onChange={(v: string)=>setCfg({ ...(cfg||{}), enabled: v === "true" })}
            options={[{ value:"true", label:"True" }, { value:"false", label:"False" }]}
            width="100%"
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
        <div><div className="label">Passcode</div>
          <input className="input" type="password" value={code} onChange={e=>setCode(e.target.value)} />
        </div>
        <div style={{ alignSelf: "end", display: "flex", alignItems: "center", gap: 8 }}>
          <span title={unlocked ? "Unlocked" : "Locked"}>{unlocked ? <UnlockIcon /> : <LockIcon />}</span>
          <button className="btn brand" onClick={unlock}>Unlock</button>
          <button className="btn brand" onClick={saveRisk} disabled={saving}>{saving ? "Saving…" : "Save Guardrails"}</button>
        </div>
      </div>
      
      <div className="help" style={{marginTop:8}}>Risk checks are enforced server-side before any order is sent.</div>
    </>
  );
}
