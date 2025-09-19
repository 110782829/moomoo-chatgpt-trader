import { useEffect, useMemo, useState } from "react";
import api from "../../api";

type TrendBar = {
  ts: string;
  close: number;
  high?: number;
  low?: number;
  sma_fast?: number | null;
  sma_slow?: number | null;
};

type TrendEvent = {
  ts?: string | null;
  side?: string | null;
  status?: string | null;
  qty?: number | null;
  price?: number | null;
  order_id?: string | null;
  action?: string | null;
  type?: string | null;
};

type TrendSymbol = {
  symbol: string;
  source?: string;
  change_pct?: number | null;
  error?: string;
  bars: TrendBar[];
  events: TrendEvent[];
};

type Snapshot = {
  generated_at?: string;
  symbols: TrendSymbol[];
};

function formatPct(v?: number | null, digits = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  const places = Math.abs(v) >= 50 ? 0 : digits;
  return `${sign}${Number(v).toFixed(places)}%`;
}

function timeAgo(ts?: string | null): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    const diff = Date.now() - d.getTime();
    const mins = Math.round(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 48) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    return `${days}d ago`;
  } catch {
    return ts;
  }
}

function closestPrice(bars: TrendBar[], ts?: string | null, hinted?: number | null): number | null {
  if (hinted != null && !Number.isNaN(hinted)) return hinted;
  if (!ts) return null;
  const target = new Date(ts).getTime();
  if (Number.isNaN(target)) return null;
  let bestValue: number | null = null;
  let bestDiff = Number.POSITIVE_INFINITY;
  bars.forEach(bar => {
    const t = new Date(bar.ts).getTime();
    if (Number.isNaN(t)) return;
    const diff = Math.abs(t - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestValue = bar.close;
    }
  });
  return bestValue;
}

export default function WatchlistTrends() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const load = async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const data = await api.getWatchlistSnapshot({ limit: 0, interval: "K_1M", bars: 160, since_hours: 36 });
      setSnapshot({ symbols: Array.isArray(data?.symbols) ? data.symbols : [], generated_at: data?.generated_at });
    } catch (e: any) {
      setError(String(e?.message || e || "Failed to load watchlist snapshot"));
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      if (cancelled) return;
      await load();
    };
    init();
    const id = window.setInterval(() => load({ silent: true }), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const symbols = snapshot?.symbols || [];
  const sources = useMemo(() => {
    const set = new Set<string>();
    symbols.forEach(sym => { if (sym.source) set.add(String(sym.source)); });
    return Array.from(set);
  }, [symbols]);

  const cards = useMemo(() => symbols.map(sym => {
    const bars = sym.bars || [];
    if (!bars.length) {
      return { ...sym, chart: null };
    }
    const width = 360;
    const height = 172;
    const padX = 28;
    const padY = 22;
    const times = bars.map(b => new Date(b.ts).getTime());
    const closes = bars.map(b => Number(b.close || 0));
    const minClose = Math.min(...closes);
    const maxClose = Math.max(...closes);
    const range = (maxClose - minClose) || 1;
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);
    const span = (maxTime - minTime) || 1;

    const getX = (idx: number) => padX + ((times[idx] - minTime) / span) * (width - padX * 2);
    const getXByTime = (time: number) => padX + ((time - minTime) / span) * (width - padX * 2);
    const getY = (value: number) => height - padY - ((value - minClose) / range) * (height - padY * 2);

    let linePath = "";
    bars.forEach((bar, idx) => {
      const x = getX(idx);
      const y = getY(Number(bar.close || 0));
      linePath += idx === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
    });

    let areaPath = "";
    if (bars.length) {
      areaPath = `M ${getX(0)} ${getY(minClose)}`;
      bars.forEach((bar, idx) => {
        const x = getX(idx);
        const y = getY(Number(bar.close || 0));
        areaPath += ` L ${x} ${y}`;
      });
      areaPath += ` L ${getX(bars.length - 1)} ${getY(minClose)} Z`;
    }

    const makeSmoothPath = (key: "sma_fast" | "sma_slow") => {
      let path = "";
      let active = false;
      bars.forEach((bar, idx) => {
        const value = bar[key];
        if (value == null || Number.isNaN(value)) {
          active = false;
          return;
        }
        const x = getX(idx);
        const y = getY(Number(value));
        if (!active) {
          path += `M ${x} ${y}`;
          active = true;
        } else {
          path += ` L ${x} ${y}`;
        }
      });
      return path.trim();
    };

    const fastPath = makeSmoothPath("sma_fast");
    const slowPath = makeSmoothPath("sma_slow");

    const minT = Math.min(...times);
    const maxT = Math.max(...times);

    const eventNodes = (sym.events || []).map((event, idx) => {
      const rawTime = event.ts ? new Date(event.ts).getTime() : NaN;
      if (Number.isNaN(rawTime) || rawTime < minT || rawTime > maxT) return null;
      const price = closestPrice(bars, event.ts, event.price ?? null);
      if (price == null) return null;
      const x = getXByTime(rawTime);
      const y = getY(price);
      const kind = (event.type || "entry").toLowerCase() === "exit" ? "exit" : "entry";
      const badge = event.side ? event.side.toUpperCase() : kind === "exit" ? "SELL" : "BUY";
      const titleLines = [
        `${badge} @ ${price.toFixed(2)}`,
        event.qty != null ? `qty ${event.qty}` : null,
        event.status ? `status ${event.status}` : null,
      ].filter(Boolean).join(" | ");
      return (
        <g key={`${event.ts || idx}-${idx}`} className={`trend-event ${kind}`}>
          <line x1={x} x2={x} y1={padY - 6} y2={height - padY + 8} />
          <circle cx={x} cy={y} r={4} />
          <title>{titleLines || "autopilot event"}</title>
        </g>
      );
    });

    const chart = (
      <svg viewBox={`0 0 ${width} ${height}`} className="trend-svg" role="img" aria-label={`${sym.symbol} intraday trend`}>
        <defs>
          <linearGradient id={`area-${sym.symbol}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(124,58,237,0.35)" />
            <stop offset="100%" stopColor="rgba(15,23,42,0.05)" />
          </linearGradient>
          <linearGradient id={`line-${sym.symbol}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(124,58,237,0.95)" />
            <stop offset="100%" stopColor="rgba(6,182,212,0.95)" />
          </linearGradient>
        </defs>
        <rect x={0} y={0} width={width} height={height} rx={10} ry={10} className="trend-bg" />
        <path d={areaPath} className="trend-area" fill={`url(#area-${sym.symbol})`} />
        <path d={linePath} className="trend-line" stroke={`url(#line-${sym.symbol})`} strokeWidth={2.2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        {slowPath && <path d={slowPath} className="trend-slow" stroke="rgba(96,165,250,.65)" />}
        {fastPath && <path d={fastPath} className="trend-fast" stroke="rgba(34,197,94,.65)" />}
        <g className="trend-events">{eventNodes}</g>
      </svg>
    );

    return { ...sym, chart };
  }), [symbols]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <div className="watchlist-trends">
      <div className="watchlist-trends__header">
        <div>
          <h2 className="watchlist-trends__title title-lg">Watchlist Pulse</h2>
        </div>
        <div className="watchlist-trends__controls">
          <span className="badge neutral">{loading ? "Syncing…" : `Updated ${timeAgo(snapshot?.generated_at)}`}</span>
          <button className="refresh-btn" onClick={handleRefresh} disabled={loading || refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
      {symbols.length ? (
        <div className="watchlist-trends__legend">
          <span><span className="legend-dot entry" /> Entry</span>
          <span><span className="legend-dot exit" /> Exit</span>
          {sources.length ? <span>Data feed: {sources.join(", ")}</span> : null}
        </div>
      ) : null}
      {error && <div className="watchlist-error" role="alert">{error}</div>}
      <div className="watchlist-grid">
        {cards.length ? cards.map(card => (
          <article key={card.symbol} className="trend-card">
            <div className="trend-card__head">
              <div>
                <div className="trend-symbol">{card.symbol}</div>
              </div>
              <div className={`trend-change ${Number(card.change_pct || 0) >= 0 ? "up" : "down"}`}>
                {formatPct(card.change_pct, 2)}
              </div>
            </div>
            <div className="trend-chart">
              {card.chart || <div className="help">No intraday data</div>}
            </div>
            <div className="trend-footer">
              {card.error ? <span className="help" style={{ color: "var(--amber)" }}>{card.error}</span> : null}
            </div>
          </article>
        )) : (!loading && !error ? <div className="help">No watchlist symbols available. Configure one in Settings → Watchlist.</div> : null)}
      </div>
    </div>
  );
}
