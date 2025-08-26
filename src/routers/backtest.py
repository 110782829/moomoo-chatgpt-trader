from fastapi import APIRouter, HTTPException
from ..schemas import BacktestMARequest, BacktestMAGridRequest

try:
    from backtest.engine import load_bars_csv, run_ma_crossover
    _BACKTEST_AVAILABLE = True
    _BACKTEST_IMPORT_ERR = None
except Exception as _be:
    _BACKTEST_AVAILABLE = False
    _BACKTEST_IMPORT_ERR = _be

try:
    from backtest.grid import run_ma_grid
    _GRID_AVAILABLE = True
    _GRID_IMPORT_ERR = None
except Exception as _ge:
    _GRID_AVAILABLE = False
    _GRID_IMPORT_ERR = _ge

router = APIRouter(prefix="/backtest", tags=["backtest"])

@router.post("/ma-crossover")
def backtest_ma(req: BacktestMARequest):
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        res = run_ma_crossover(
            bars=bars,
            fast=int(req.fast),
            slow=int(req.slow),
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
        )
        trades = [{
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
            "entry_px": t.entry_px, "exit_px": t.exit_px, "qty": t.qty, "pnl": t.pnl
        } for t in res.trades[:20]]
        return {"metrics": res.metrics, "trades_sample": trades}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv with columns time,open,high,low,close,volume",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")

@router.post("/ma-grid")
def backtest_ma_grid(req: BacktestMAGridRequest):
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if not _GRID_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest grid not available: {_GRID_IMPORT_ERR}")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        results = run_ma_grid(
            bars=bars,
            fast_min=req.fast_min, fast_max=req.fast_max, fast_step=req.fast_step,
            slow_min=req.slow_min, slow_max=req.slow_max, slow_step=req.slow_step,
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
            top_n=int(req.top_n),
        )
        return {"count": len(results), "results": results}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest grid failed: {e}")

