import { useEffect, useRef, useState } from "react";
import api from "../../api";
import { useLocalStorage } from "../../App";

function Num({
  value,
  setValue,
  step = 1,
  min,
  max,
  inputProps = {},
}: {
  value: number;
  setValue: (n: number) => void;
  step?: number;
  min?: number;
  max?: number;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState<string>(
    Number.isFinite(value) ? String(value) : ""
  );

  useEffect(() => {
    if (document.activeElement !== ref.current) {
      setText(Number.isFinite(value) ? String(value) : "");
    }
  }, [value]);

  const valid = (s: string) => /^-?\d*\.?\d*$/.test(s);

  function clamp(n: number) {
    if (min != null && n < min) n = min;
    if (max != null && n > max) n = max;
    return n;
  }

  function commit() {
    if (text === "" || text === "-" || text === "." || text === "-.") {
      const fallback = min != null ? Math.max(0, min) : 0;
      setValue(fallback);
      setText(String(fallback));
      return;
    }
    const n = clamp(Number(text));
    setValue(n);
    setText(String(n));
  }

  function bump(dir: 1 | -1) {
    const cur =
      text === "" || text === "-" || text === "." || text === "-."
        ? (Number.isFinite(value) ? value : 0)
        : Number(text);
    const s = Number(step) || 1;
    const next = clamp(Number((cur + dir * s).toFixed(6)));
    setValue(next);
    setText(String(next));
  }

  return (
    <div className="num">
      <input
        ref={ref}
        className="input"
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => {
          const s = e.target.value;
          if (valid(s)) setText(s);
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "NumpadEnter") {
            e.preventDefault();
            commit();
            (e.currentTarget as HTMLInputElement).blur();
          }
        }}
        {...inputProps}
      />
      <span className="spin" aria-hidden="true">
        <button type="button" onClick={() => bump(1)} title="Increase">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 6l6 6H6z" />
          </svg>
        </button>
        <button type="button" onClick={() => bump(-1)} title="Decrease">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 18l-6-6h12z" />
          </svg>
        </button>
      </span>
    </div>
  );
}

export default function SettingsTrading() {
  const [winRate, setWinRate] = useLocalStorage<number>("pref.winRate", 55);
  const [rr, setRR] = useLocalStorage<number>("pref.rr", 1.5);
  const [stopLoss, setStopLoss] = useLocalStorage<number>("pref.stop", 1.0);
  const [takeProfit, setTakeProfit] = useLocalStorage<number>("pref.tp", 2.0);
  const [measuredMove, setMeasuredMove] = useLocalStorage<number>("pref.mm", 1.0);
  const [maxDD, setMaxDD] = useLocalStorage<number>("pref.maxdd", 5.0);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const p = await api.getAutoPrefs();
        if (p && typeof p === "object") {
          if (p.target_winrate_pct != null) setWinRate(Number(p.target_winrate_pct));
          if (p.target_rr != null) setRR(Number(p.target_rr));
          if (p.stop_loss_pct != null) setStopLoss(Number(p.stop_loss_pct));
          if (p.take_profit_pct != null) setTakeProfit(Number(p.take_profit_pct));
          if (p.measured_move_atr_mult != null) setMeasuredMove(Number(p.measured_move_atr_mult));
          if (p.max_dd_pct != null) setMaxDD(Number(p.max_dd_pct));
        }
      } catch {}
      setLoaded(true);
    })();
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const id = window.setTimeout(async () => {
      try {
        await api.putAutoPrefs({
          target_winrate_pct: winRate,
          target_rr: rr,
          stop_loss_pct: stopLoss,
          take_profit_pct: takeProfit,
          measured_move_atr_mult: measuredMove,
          max_dd_pct: maxDD,
        });
      } catch {}
    }, 500);
    return () => window.clearTimeout(id);
  }, [loaded, winRate, rr, stopLoss, takeProfit, measuredMove, maxDD]);

  return (
    <div className="stack">
      <div className="form-row prefs-grid">
        <div>
          <div className="label">Target win rate (%)</div>
          <Num value={winRate} setValue={setWinRate} step={1} min={0} max={100} />
        </div>
        <div>
          <div className="label">Reward ratio (R)</div>
          <Num value={rr} setValue={setRR} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Stop loss (% move)</div>
          <Num value={stopLoss} setValue={setStopLoss} step={0.1} min={0} />
        </div>
      </div>
      <div className="form-row">
        <div>
          <div className="label">Take profit (% move)</div>
          <Num value={takeProfit} setValue={setTakeProfit} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Measured move (ATR x)</div>
          <Num value={measuredMove} setValue={setMeasuredMove} step={0.1} min={0} />
        </div>
        <div>
          <div className="label">Max drawdown (%)</div>
          <Num value={maxDD} setValue={setMaxDD} step={0.1} min={0} max={100} />
        </div>
      </div>
    </div>
  );
}

