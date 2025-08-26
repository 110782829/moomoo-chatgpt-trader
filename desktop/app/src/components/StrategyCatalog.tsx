import { useEffect, useState } from "react";
import { NiceCombobox, NiceSelect } from "./NiceSelect";
import { api } from "../lib/api";
import { brief } from "../lib/utils";
import { useLocalStorage } from "../hooks/useLocalStorage";
import type { StrategyKind } from "../types";

/** Strategy presets and starter */
export function StrategyCatalog({ connected }: { connected: boolean }) {
  const [kind, setKind] = useLocalStorage<StrategyKind>("strat.kind", "ma-crossover");
  const [symbol, setSymbol] = useLocalStorage("strat.symbol", "US.AAPL");
  const [fast, setFast] = useLocalStorage("strat.ma.fast", 20);
  const [slow, setSlow] = useLocalStorage("strat.ma.slow", 50);
  const [ktype, setKType] = useLocalStorage("strat.ma.ktype", "K_1M");
  const [interval, setIntervalSec] = useLocalStorage("strat.ma.interval", 15);
  const [qty, setQty] = useLocalStorage("strat.ma.qty", 1.0);
  const [sizeMode, setSizeMode] = useLocalStorage<"shares" | "usd">("strat.ma.sizeMode", "shares");
  const [dollarSize, setDollarSize] = useLocalStorage("strat.ma.dollar", 0.0);
  const [allowReal, setAllowReal] = useLocalStorage("strat.ma.allowReal", false);
  const [gridFast, setGridFast] = useLocalStorage("strat.grid.fast", 20);
  const [gridSlow, setGridSlow] = useLocalStorage("strat.grid.slow", 50);

  const PRESETS_KEY = "strat.presets.v1";
  const [presets, setPresets] = useState<Record<string, any>>(() => {
    try { return JSON.parse(localStorage.getItem(PRESETS_KEY) || "{}"); } catch { return {}; }
  });
  function savePresets(next: Record<string, any>) {
    setPresets(next);
    try { localStorage.setItem(PRESETS_KEY, JSON.stringify(next)); } catch {}
  }
  function makePresetPayload() {
    return kind === "ma-crossover"
      ? { kind, symbol, fast, slow, ktype, interval_sec: interval, qty, size_mode: sizeMode, dollar_size: dollarSize, allow_real: allowReal }
      : { kind, symbol, fast: gridFast, slow: gridSlow };
  }
  function onSavePreset() {
    const name = prompt("Preset name?");
    if (!name) return;
    const next = { ...presets, [name]: makePresetPayload() };
    savePresets(next);
  }
  function onLoadPreset(name: string) {
    const p = presets[name];
    if (!p) return;
    setKind(p.kind as StrategyKind);
    setSymbol(p.symbol || symbol);
    if (p.kind === "ma-crossover") {
      setFast(p.fast ?? fast);
      setSlow(p.slow ?? slow);
      setKType(p.ktype ?? ktype);
      setIntervalSec(p.interval_sec ?? interval);
      setQty(p.qty ?? qty);
      setSizeMode((p.size_mode as any) ?? sizeMode);
      setDollarSize(p.dollar_size ?? dollarSize);
      setAllowReal(!!p.allow_real);
    } else {
      setGridFast(p.fast ?? gridFast);
      setGridSlow(p.slow ?? gridSlow);
    }
  }
  function onDeletePreset(name: string) {
    const next = { ...presets };
    delete next[name];
    savePresets(next);
  }

  async function startStrategy() {
    if (!connected) { alert("Not connected"); return; }
    if (kind === "ma-crossover") {
      const payload = { symbol, fast, slow, ktype, qty, size_mode: sizeMode, dollar_size: dollarSize, interval_sec: interval, allow_real: allowReal };
      try { await api.startMA(payload); alert("MA strategy started."); }
      catch (e: any) { alert(`Start failed: ${brief(e)}`); }
    } else {
      alert("Grid live start requires a /automation/start/ma-grid endpoint. Backtest supports grid.");
    }
  }

  return (
    <div className="panel">
      <h2 style={{ marginTop: 0, marginBottom: 10 }}>Strategies</h2>
      <div className="form-row">
        <div>
          <div className="label">Strategy</div>
          <NiceSelect
            value={kind}
            onChange={v => setKind(v as StrategyKind)}
            options={[
              { value: "ma-crossover", label: "MA Crossover" },
              { value: "ma-grid", label: "MA Grid (beta)" },
            ]}
            width={200}
          />
        </div>
        <div>
          <div className="label">Symbol</div>
          <input className="input" value={symbol} onChange={e => setSymbol(e.target.value)} />
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
          <button className="btn brand" onClick={startStrategy} disabled={!connected}>Start</button>
          <button className="btn" onClick={onSavePreset}>Save Preset</button>
          <PresetPicker presets={presets} onLoad={onLoadPreset} onDelete={onDeletePreset} />
        </div>
      </div>

      {kind === "ma-crossover" ? (
        <>
          <div className="form-row" style={{ marginTop: 12 }}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={fast} onChange={e => setFast(parseInt(e.target.value) || 1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={slow} onChange={e => setSlow(parseInt(e.target.value) || 2)} /></div>
            <div><div className="label">KType</div>
              <NiceCombobox
                value={ktype}
                onChange={setKType}
                options={["K_1M", "K_5M", "K_15M", "K_30M", "K_60M", "K_1D"].map(k => ({ value: k, label: k }))}
                width={180}
                placeholder="Search ktype…"
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Interval (sec)</div><input className="input" type="number" value={interval} onChange={e => setIntervalSec(parseInt(e.target.value) || 1)} /></div>
            <div><div className="label">Qty (shares)</div><input className="input" type="number" value={qty} onChange={e => setQty(parseFloat(e.target.value) || 0)} /></div>
            <div>
              <div className="label">Size Mode</div>
              <NiceSelect
                value={sizeMode}
                onChange={v => setSizeMode(v as any)}
                options={[{ value: "shares", label: "shares" }, { value: "usd", label: "usd" }]}
                width={140}
              />
            </div>
          </div>
          <div className="form-row">
            <div><div className="label">Dollar Size</div><input className="input" type="number" value={dollarSize} onChange={e => setDollarSize(parseFloat(e.target.value) || 0)} /></div>
            <div>
              <div className="label">Allow Real Trading</div>
              <NiceSelect
                value={String(allowReal)}
                onChange={v => setAllowReal(v === "true")}
                options={[{ value: "false", label: "False" }, { value: "true", label: "True" }]}
                width={140}
              />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="form-row" style={{ marginTop: 12 }}>
            <div><div className="label">Fast MA</div><input className="input" type="number" value={gridFast} onChange={e => setGridFast(parseInt(e.target.value) || 1)} /></div>
            <div><div className="label">Slow MA</div><input className="input" type="number" value={gridSlow} onChange={e => setGridSlow(parseInt(e.target.value) || 2)} /></div>
          </div>
          <div className="help" style={{ marginTop: 4 }}>
            Live Grid start requires a server endpoint <code>/automation/start/ma-grid</code>. Backtest is available in the Backtest tab.
          </div>
        </>
      )}
    </div>
  );
}

function PresetPicker({ presets, onLoad, onDelete }: { presets: Record<string, any>; onLoad: (n: string) => void; onDelete: (n: string) => void }) {
  const names = Object.keys(presets);
  const [sel, setSel] = useState(names[0] || "");
  useEffect(() => { if (!names.includes(sel)) setSel(names[0] || ""); }, [JSON.stringify(names)]);
  if (!names.length) return <span className="help">No presets yet.</span>;
  return (
    <div className="row" style={{ alignItems: "flex-end" }}>
      <div>
        <div className="label">Presets</div>
        <NiceCombobox
          value={sel}
          onChange={setSel}
          options={names.map(n => ({ value: n, label: n }))}
          width={180}
          placeholder="Search presets…"
        />
      </div>
      <button className="btn" onClick={() => onLoad(sel)} disabled={!sel}>Load</button>
      <button className="btn red" onClick={() => onDelete(sel)} disabled={!sel}>Delete</button>
    </div>
  );
}

