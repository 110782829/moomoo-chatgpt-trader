import { useEffect, useState } from "react";
import api from "../../api";
import { useLocalStorage } from "../../App";

export default function SettingsPreferences({ toast }: any) {
  const [raw, setRaw] = useLocalStorage<string>("pref.nl.raw", "");
  const [summary, setSummary] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => { api.getAutoStyle().then(r => { setRaw(r.raw||""); setSummary(r.summary||""); setDirty(false); }).catch(()=>{}); }, []);

  async function save() {
    const r = await api.postAutoStyle(raw);
    setSummary(r.summary||"");
    setDirty(false);
    toast.show("Style saved.");
  }

  async function reset() {
    const r = await api.deleteAutoStyle();
    setRaw(r.raw||"");
    setSummary(r.summary||"");
    setDirty(false);
  }

  return (
    <div className="nl-card">
      <div className="toolbar">
        <button className="btn brand" onClick={save} disabled={!dirty}>Save</button>
        <button className="btn" onClick={reset}>Reset</button>
        <span className="counter">{raw.length} chars</span>
      </div>
      <textarea
        className="input nl-fixed"
        value={raw}
        onChange={e => { setRaw(e.target.value); setDirty(true); }}
        placeholder="Describe your tone, formatting, and constraints (e.g., 'Use concise bullet points, risk-first tone…')"
      />
      {summary ? <div className="help" style={{marginTop:8}}>Summary: {summary}</div> : null}
    </div>
  );
}
