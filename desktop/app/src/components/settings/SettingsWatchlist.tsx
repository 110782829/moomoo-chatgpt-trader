import { useEffect, useState } from "react";
import api from "../../api";
import { NiceSelect } from "../../App";

export default function SettingsWatchlist({ toast }: any) {
  const [discEnabled, setDiscEnabled] = useState(true);
  const [discOnly, setDiscOnly] = useState(false);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [newSymbol, setNewSymbol] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { (async () => {
    try {
      const d = await api.getDiscovery();
      setDiscEnabled(!!d.enabled);
      setDiscOnly(!!d.only);
      setSymbols(Array.isArray(d.preview) ? d.preview : Array.isArray(d.seed) ? d.seed : []);
    } catch {}
  })(); }, []);

  function addSymbol() {
    const sym = newSymbol.trim().toUpperCase();
    if (sym && !symbols.includes(sym)) setSymbols([...symbols, sym]);
    setNewSymbol("");
  }

  function removeSymbol(sym: string) {
    setSymbols(symbols.filter(s => s !== sym));
  }

  async function save() {
    setSaving(true);
    try {
      await api.putDiscovery({ enabled: discEnabled, only: discOnly, seed: symbols });
      const d = await api.getDiscovery();
      setSymbols(Array.isArray(d.preview) ? d.preview : symbols);
      toast.show("Watchlist saved.");
    } catch(e:any){ toast.show(String(e)); }
    finally { setSaving(false); }
  }

  return (
    <div className="stack">
      <div className="form-row" style={{ alignItems: "flex-end" }}>
        <div>
          <div className="label">Discovery Enabled</div>
          <NiceSelect
            value={String(discEnabled)}
            onChange={(v)=>setDiscEnabled(v==="true")}
            options={[{value:"true",label:"True"},{value:"false",label:"False"}]}
            width="100%"
          />
          {/* toggle discovery */}
        </div>
        <div>
          <div className="label">Discovery Only</div>
          <NiceSelect
            value={String(discOnly)}
            onChange={(v)=>setDiscOnly(v==="true")}
            options={[{value:"false",label:"False"},{value:"true",label:"True"}]}
            width="100%"
          />
          {/* allow dynamic-only mode */}
        </div>
        <div>
          <div className="label">Add Symbol</div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              placeholder="Add symbol"
              value={newSymbol}
              onChange={e=>setNewSymbol(e.target.value)}
              onKeyDown={e=>{ if(e.key==="Enter") addSymbol(); }}
            />
            <button className="btn" onClick={addSymbol}>Add</button>
          </div>
        </div>
      </div>
      <div className="table-wrap" style={{ marginTop: 8, maxHeight: 280 }}>
        <table className="table-modern">
          <thead>
            <tr><th>Symbol</th><th className="num" style={{ width: 80 }}>Action</th></tr>
          </thead>
          <tbody>
            {symbols.map(sym => (
              <tr key={sym}>
                <td>{sym}</td>
                <td className="num">
                  <button className="btn" onClick={() => removeSymbol(sym)}>Remove</button>
                </td>
              </tr>
            ))}
            {!symbols.length && (
              <tr>
                <td colSpan={2} style={{ textAlign: "center", opacity: 0.6 }}>
                  No symbols
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="row" style={{ marginTop: 8, justifyContent: "flex-end" }}>
        <button className="btn brand" onClick={save} disabled={saving}>{saving?"Saving…":"Save Watchlist"}</button>
      </div>
    </div>
  );
}
