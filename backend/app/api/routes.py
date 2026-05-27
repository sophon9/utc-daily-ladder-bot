"""FastAPI routes for trading bot."""
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

from app.config import BotConfig, get_config_loader
from app.bot import TradingBot

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
LOG_FILE = PROJECT_ROOT / "logs" / "daily_ladder_bot.log"

router = APIRouter(prefix="/api", tags=["bot"])

# Global bot instance (set in main.py)
_bot_instance: Optional[TradingBot] = None


def set_bot_instance(bot: TradingBot):
    """Set global bot instance."""
    global _bot_instance
    _bot_instance = bot


def get_bot() -> TradingBot:
    """Dependency to get bot instance."""
    if _bot_instance is None:
        raise HTTPException(status_code=500, detail="Bot not initialized")
    return _bot_instance


# ==================== STATUS ENDPOINTS ====================

@router.get("/status")
async def get_status(bot: TradingBot = Depends(get_bot)):
    """Get bot status."""
    status = bot.get_status()
    status["account_connection"] = await bot.get_account_connection_status()

    # Add equity if not in dry run mode
    equity = await bot.get_equity()
    if equity is not None:
        status["equity"] = equity

    return status


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": "2026-01-01T00:00:00"}


# ==================== CONTROL ENDPOINTS ====================

@router.post("/start")
async def start_bot(bot: TradingBot = Depends(get_bot)):
    """Start the trading bot."""
    try:
        await bot.start()
        return {"status": "started", "message": "Bot started successfully"}
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_bot(bot: TradingBot = Depends(get_bot)):
    """Stop the trading bot."""
    try:
        await bot.stop()
        return {"status": "stopped", "message": "Bot stopped successfully"}
    except Exception as e:
        logger.error(f"Failed to stop bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop")
async def emergency_stop(
    reason: str = Body("User initiated emergency stop"),
    bot: TradingBot = Depends(get_bot)
):
    """Emergency stop and close all positions."""
    try:
        await bot.emergency_stop_all(reason=reason)
        return {"status": "emergency_stopped", "message": "Emergency stop executed"}
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CONFIG ENDPOINTS ====================

@router.get("/config")
async def get_config():
    """Get current configuration."""
    config_loader = get_config_loader()
    config = config_loader.get_config()
    return config.model_dump()


class ConfigUpdate(BaseModel):
    """Config update request."""
    config: dict


@router.post("/config")
async def update_config(update: ConfigUpdate):
    """Update configuration."""
    try:
        config_loader = get_config_loader()

        # Validate new config
        new_config = BotConfig(**update.config)

        # Save
        config_loader.save(new_config)

        if _bot_instance is not None:
            await _bot_instance._reload_config()

        return {
            "status": "success",
            "message": "Configuration updated",
            "config": new_config.model_dump()
        }
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ==================== POSITION ENDPOINTS ====================

@router.get("/positions")
async def get_positions(bot: TradingBot = Depends(get_bot)):
    """Get all position sets."""
    position_sets = bot.position_manager.get_all_sets()
    return {
        "positions": [ps.to_dict() for ps in position_sets],
        "total_count": len(position_sets),
        "active_count": bot.position_manager.count_active_sets(),
    }


@router.get("/positions/{set_id}")
async def get_position(set_id: str, bot: TradingBot = Depends(get_bot)):
    """Get specific position set."""
    position_set = bot.position_manager.get_position_set(set_id)
    if not position_set:
        raise HTTPException(status_code=404, detail="Position set not found")
    return position_set.to_dict()


@router.post("/positions/{set_id}/close")
async def close_position(
    set_id: str,
    reason: str = Body("Manual close"),
    bot: TradingBot = Depends(get_bot)
):
    """Close specific position set."""
    try:
        success = await bot.close_position_set(set_id, reason=reason)
        if success:
            return {"status": "success", "message": f"Position {set_id} closed"}
        else:
            raise HTTPException(status_code=400, detail="Failed to close position")
    except Exception as e:
        logger.error(f"Failed to close position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/positions/{set_id}")
async def remove_position(
    set_id: str,
    force: bool = False,
    bot: TradingBot = Depends(get_bot)
):
    """Remove a position set from local persistence."""
    from app.api.websocket import broadcast_event

    position_set = bot.position_manager.get_position_set(set_id)
    if not position_set:
        raise HTTPException(status_code=404, detail="Position set not found")

    if position_set.is_active() and not force:
        raise HTTPException(status_code=400, detail="Cannot remove an active position. Close it first.")

    if position_set.is_active() and force:
        logger.warning(f"Force-removing active position set {set_id} from local state")

    bot.position_manager.remove_set(set_id)
    bot.position_manager.save_positions()

    # Broadcast updated positions list
    positions = bot.position_manager.get_all_sets()
    await broadcast_event("positions_update", [ps.to_dict() for ps in positions])

    return {"status": "success", "message": f"Position {set_id} removed"}


@router.post("/positions/close-all")
async def close_all_positions(bot: TradingBot = Depends(get_bot)):
    """Close all active positions."""
    active_sets = bot.position_manager.get_active_sets()
    closed_count = 0

    for ps in active_sets:
        try:
            success = await bot.close_position_set(ps.set_id, reason="Close all")
            if success:
                closed_count += 1
        except Exception as e:
            logger.error(f"Failed to close {ps.set_id}: {e}")

    return {
        "status": "success",
        "closed_count": closed_count,
        "total_count": len(active_sets)
    }


# ==================== MARKET DATA ENDPOINTS ====================

@router.get("/market-data")
async def get_market_data(bot: TradingBot = Depends(get_bot)):
    """Get current market data."""
    status = bot.get_status()
    symbol = status.get("symbol")
    feed = bot.market_data.get(symbol) if bot.market_data and symbol else None
    if not feed or not feed.candle_manager:
        raise HTTPException(status_code=503, detail="Market data not available")

    latest_candle = feed.candle_manager.get_latest_candle()

    return {
        "symbol": symbol,
        "interval": "5m",
        "latest_candle": {
            "timestamp": latest_candle.timestamp,
            "datetime": latest_candle.datetime.isoformat(),
            "open": latest_candle.open,
            "high": latest_candle.high,
            "low": latest_candle.low,
            "close": latest_candle.close,
            "volume": latest_candle.volume,
        } if latest_candle else None,
        "daily_open_price": status.get("daily_open_price"),
        "current_drawdown_pct": status.get("current_drawdown_pct"),
        "candle_count": len(feed.candle_manager),
    }


@router.get("/chart-data")
async def get_chart_data(
    limit: int = 50,
    bot: TradingBot = Depends(get_bot)
):
    """Get recent candles with the current UTC daily-open reference line."""
    status = bot.get_status()
    symbol = status.get("symbol")
    feed = bot.market_data.get(symbol) if bot.market_data and symbol else None
    if not feed or not feed.candle_manager:
        raise HTTPException(status_code=503, detail="Market data not available")

    candle_mgr = feed.candle_manager

    # Get recent candles (last N)
    all_candles = candle_mgr.candles
    recent_candles = all_candles[-limit:] if len(all_candles) > limit else all_candles

    daily_open_price = status.get("daily_open_price")
    reference_values = [daily_open_price for _ in recent_candles] if daily_open_price else []

    return {
        "symbol": symbol,
        "interval": "5m",
        "candles": [
            {
                "timestamp": c.timestamp,
                "datetime": c.datetime.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in recent_candles
        ],
        "reference_values": reference_values,
        "reference_label": "UTC Daily Open",
        "move_label": (
            "Rally From Open"
            if bot.config.bias == "short"
            else "Move From Open"
            if bot.config.bias == "both"
            else "Drawdown From Open"
        ),
    }


@router.get("/equity")
async def get_equity(bot: TradingBot = Depends(get_bot)):
    """Get current account equity."""
    equity = await bot.get_equity()
    return {
        "equity": equity,
        "available": equity is not None,
        "dry_run": bot.dry_run,
    }


@router.get("/equity/history")
async def get_equity_history(limit: int = 240, bot: TradingBot = Depends(get_bot)):
    """Get recent equity history points for performance tracking."""
    limit = max(20, min(limit, 2000))
    points = bot.equity_history.get_points(limit=limit)
    return {
        "points": [
            {
                "timestamp": point.timestamp,
                "equity": point.equity,
            }
            for point in points
        ],
        "count": len(points),
        "available": len(points) > 0,
        "dry_run": bot.dry_run,
    }


@router.get("/logs")
async def get_logs(lines: int = 50):
    """Get recent bot logs."""
    lines = max(10, min(lines, 1000))

    if not LOG_FILE.exists():
        return {
            "lines": [],
            "content": "",
            "path": str(LOG_FILE),
            "available": False,
        }

    try:
        content = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        log_lines = content.splitlines()
        recent_lines = log_lines[-lines:]
        return {
            "lines": recent_lines,
            "content": "\n".join(recent_lines),
            "path": str(LOG_FILE),
            "available": True,
            "line_count": len(recent_lines),
            "updated_at": LOG_FILE.stat().st_mtime,
        }
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to read log file")
