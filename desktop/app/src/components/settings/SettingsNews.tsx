import { useEffect, useState } from "react";
import api from "../../api";
import { NiceSelect } from "../../App";

export default function SettingsNews({ toast }: any) {
  const [newsEnabled, setNewsEnabled] = useState(true);
  const [newsTtl, setNewsTtl] = useState(1800);
  const [newsProvider, setNewsProvider] = useState("heuristic");
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => { try { const n = await api.getNewsSettings(); setNewsEnabled(!!n.enabled); setNewsTtl(Number(n.ttl_sec||1800)); if (n.provider) setNewsProvider(String(n.provider)); } catch {} })(); }, []);

  async function save() {
    setSaving(true);
    try { await api.putNewsSettings({ enabled: newsEnabled, ttl_sec: Number(newsTtl)||1800, provider: newsProvider }); toast.show("News settings saved."); }
    catch(e:any){ toast.show(String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="stack">
      <div className="form-row">
        <div>
          <div className="label">News Enabled</div>
          <NiceSelect
            value={String(newsEnabled)}
            onChange={(v)=>setNewsEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width={140}
          />
          {/* Toggle news usage */}
        </div>
        <div>
          <div className="label">TTL (sec)</div>
          <input className="input" type="number" value={newsTtl} onChange={e=>setNewsTtl(parseInt(e.target.value)||0)} />
        </div>
        <div>
          <div className="label">Provider</div>
          <NiceSelect
            value={newsProvider}
            onChange={setNewsProvider}
            options={[{value:"heuristic",label:"Heuristic"},{value:"gpt",label:"GPT"}]}
            width={160}
          />
          {/* Supported providers */}
        </div>
      </div>
      <div className="row" style={{ justifyContent: "flex-start" }}>
        {/* Save button anchored to bottom-left */}
        <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save News"}</button>
      </div>
    </div>
  );
}
