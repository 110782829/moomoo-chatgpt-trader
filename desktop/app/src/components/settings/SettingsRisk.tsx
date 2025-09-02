import { NiceSelect } from "../../App";

export default function SettingsRisk({ cfg, setCfg, cfgGet, saveRisk, saving }: any) {
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
      </div>
      <div className="row" style={{marginTop:10}}>
        <button className="btn brand" onClick={saveRisk} disabled={saving}>{saving ? "Saving…" : "Save Guardrails"}</button>
      </div>
      <div className="help" style={{marginTop:8}}>Risk checks are enforced server-side before any order is sent.</div>
    </>
  );
}
