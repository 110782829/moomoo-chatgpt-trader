import { useEffect, useState } from "react";
import api from "../../api";
import { NiceSelect } from "../../App";

export default function SettingsWatchlist({ toast }: any) {
  const [discEnabled, setDiscEnabled] = useState(true);
  const [discOnly, setDiscOnly] = useState(false);
  const [seed, setSeed] = useState("");
  const [preview, setPreview] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const d = await api.getDiscovery();
      setDiscEnabled(!!d.enabled);
      setDiscOnly(!!d.only);
      setSeed(Array.isArray(d.seed) ? d.seed.join("\n") : "");
      setPreview(Array.isArray(d.preview) ? d.preview : []);
    } catch {}
  })(); }, []);

  async function save() {
    setSaving(true);
    try {
      const parsed = seed.split(/\n+/).map(s=>s.trim()).filter(Boolean);
      await api.putDiscovery({ enabled: discEnabled, only: discOnly, seed: parsed });
      const d = await api.getDiscovery();
      setPreview(Array.isArray(d.preview) ? d.preview : []);
      toast.show("Watchlist saved.");
    } catch(e:any){ toast.show(String(e)); }
    finally { setSaving(false); }
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
          {/* you toggle discovery */}
        </div>
        <div>
          <div className="label">Discovery Only</div>
          <NiceSelect
            value={String(discOnly)}
            onChange={(v)=>setDiscOnly(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width={140}
          />
          {/* we allow dynamic only mode */}
        </div>
      </div>
      <div>
        <div className="label">Seed Symbols (one per line)</div>
        <textarea className="input" rows={4} value={seed} onChange={e=>setSeed(e.target.value)} />
      </div>
      {preview.length ? <div className="help">Preview: {preview.join(", ")}</div> : null}
      <div className="row" style={{marginTop:8}}>
        <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save Watchlist"}</button>
      </div>
    </div>
  );
}
