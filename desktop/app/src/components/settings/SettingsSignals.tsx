import { useEffect, useState } from "react";
import api from "../../api";

export default function SettingsSignals({ toast }: any) {
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Strategy name map
  const pretty: Record<string, string> = {
    macd_cross: "MACD Cross",
    bb_breakout: "Bollinger Breakout",
    stoch_rsi_extreme: "Stochastic RSI Extreme",
    ma_trend: "MA Trend",
    rsi_extreme: "RSI Extreme",
    news: "News",
  };

  useEffect(() => { (async () => { try { const s = await api.getSignalsSettings(); setWeights(s.weights||{}); } catch {} finally { setLoading(false); } })(); }, []);

  function setWeight(name: string, v: number) { setWeights(prev => ({ ...prev, [name]: v })); }
  function normalize() {
    const sum = Object.values(weights).reduce((a,b)=>a+(b||0),0);
    if (!sum) return;
    const next: Record<string, number> = {};
    Object.keys(weights).forEach(k=>{ next[k] = Number(((weights[k]||0)/sum).toFixed(2)); });
    setWeights(next);
  }
  function assignAuto() {
    const n = Object.keys(weights).length;
    if (!n) return;
    const w = Number((1/n).toFixed(2));
    const next: Record<string, number> = {};
    Object.keys(weights).forEach(k=>{ next[k] = w; });
    setWeights(next);
  }
  async function save() {
    setSaving(true);
    try { await api.putSignalsSettings({ weights }); toast.show("Signals saved."); } catch(e:any){ toast.show(String(e)); } finally { setSaving(false); }
  }

  const names = Object.keys(weights).length
    ? Object.keys(weights)
    : [
        "macd_cross",
        "bb_breakout",
        "stoch_rsi_extreme",
        "ma_trend",
        "rsi_extreme",
        "news",
      ];

  return (
    <div className="stack" style={{ marginTop: 32 }}>
      <div className="row" style={{marginBottom:8, gap:8}}>
        <button className="btn" onClick={normalize}>Normalize Weights</button>
        <button className="btn" onClick={assignAuto}>Assign Automatically</button>
      </div>
      <div className="table-wrap" style={{ overflowY: "visible" }}>
        <table className="table-modern">
          <thead><tr><th>Strategy</th><th className="num" style={{width:160}}>Weight</th></tr></thead>
          <tbody>
            {names.map(n => (
              <tr key={n}>
                <td>{pretty[n] || n.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</td>
                <td className="num"><input className="input" type="number" step={0.1} min={0} max={2} value={weights[n] ?? 1} onChange={e=>setWeight(n, parseFloat(e.target.value)||0)} style={{maxWidth:120}} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row" style={{marginTop:8, justifyContent:"flex-end"}}>
        <button className="btn brand" onClick={save} disabled={saving || loading}>{saving?"Saving…":"Save Signals"}</button>
      </div>
    </div>
  );
}
