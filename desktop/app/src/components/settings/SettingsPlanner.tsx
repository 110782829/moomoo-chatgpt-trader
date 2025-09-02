import { useEffect, useState } from "react";
import { NiceSelect } from "../../App";
import api from "../../api";

export default function SettingsPlanner({ toast }: any) {
  const [minConf, setMinConf] = useState(0.6);
  const [topN, setTopN] = useState(8);
  const [strict, setStrict] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => { try { const p = await api.getPlannerSettings(); setMinConf(Number(p.min_confidence||0.6)); setTopN(Number(p.top_n||8)); setStrict(!!p.strict_prefs); } catch {} })(); }, []);

  async function save() {
    setSaving(true);
    try { await api.putPlannerSettings({ min_confidence: minConf, top_n: topN, strict_prefs: strict }); toast.show("Planner saved."); }
    catch(e:any){ toast.show(String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div>
          <div className="label">Min confidence (0–1)</div>
          <input className="input" type="number" step={0.01} min={0} max={1} value={minConf} onChange={e=>setMinConf(parseFloat(e.target.value)||0)} />
        </div>
        <div>
          <div className="label">Top‑N Universe</div>
          <input className="input" type="number" min={1} value={topN} onChange={e=>setTopN(parseInt(e.target.value)||8)} />
        </div>
        <div>
          <div className="label">Strict Prefs</div>
          <NiceSelect value={String(strict)} onChange={(v)=>setStrict(v==="true")} options={[{value:"false",label:"False"},{value:"true",label:"True"}]} width={140} />
        </div>
      </div>
      <div className="row" style={{ justifyContent: "flex-start" }}>
        {/* Save button anchored to bottom-left */}
        <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save Planner"}</button>
      </div>
    </div>
  );
}
