export type Mode = "automatic" | "manual";

export type RiskConfig = {
  enabled?: boolean;
  max_usd_per_trade?: number;
  max_open_positions?: number;
  max_daily_loss_usd?: number;
  trading_hours_pt?: { start: string; end: string };
  flatten_before_close_min?: number;
};

export type StrategyKind = "ma-crossover" | "ma-grid";
