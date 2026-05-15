"""Main trading bot orchestrator for the daily drawdown ladder strategy."""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import BotConfig, ConfigLoader
from app.exchange import BybitClient
from app.execution import OrderManager
from app.marketdata import MarketDataFeed
from app.portfolio import PositionManager, PositionSet, PositionState
from app.risk import EmergencyStop, RiskLimits
from app.strategy import Signal, SignalDetector

logger = logging.getLogger(__name__)


class TradingBot:
    """Coordinates market data, entry detection, execution, and position management."""

    def __init__(
        self,
        config: BotConfig,
        exchange_client: BybitClient,
        dry_run: bool = True,
        config_path: Optional[Path] = None,
    ):
        self.config = config
        self.client = exchange_client
        self.dry_run = dry_run
        self.config_path = config_path

        self.market_data: Optional[MarketDataFeed] = None
        self.signal_detector = SignalDetector(config.entry_levels_pct)
        self.position_manager = PositionManager(config.max_position_sets)
        self.order_manager = OrderManager(exchange_client, dry_run)
        self.risk_limits = RiskLimits(config.cooldown_minutes, config.max_position_sets)
        self.emergency_stop = EmergencyStop()

        self.running = False
        self._main_task: Optional[asyncio.Task] = None
        self._pnl_task: Optional[asyncio.Task] = None
        self._config_watcher_task: Optional[asyncio.Task] = None
        self._config_last_mtime: Optional[float] = None

        self._equity_cache: Optional[float] = None
        self._equity_cache_ts: float = 0.0
        self._equity_cache_ttl_seconds: int = 30
        self._equity_lock = asyncio.Lock()

        self._state_file = Path("data/bot_state.json")
        self._daily_open_price: Optional[float] = None
        self._daily_open_day: Optional[str] = None

        logger.info(
            "TradingBot initialized (DRY_RUN=%s, symbol=%s, entry_levels=%s, hedge_enabled=%s)",
            dry_run,
            config.symbol,
            config.entry_levels_pct,
            config.hedge_config.enabled,
        )

    async def initialize(self):
        """Initialize bot components."""
        logger.info("Initializing trading bot...")
        self.market_data = MarketDataFeed(self.client, symbol=self.config.symbol, interval="5")
        await self.market_data.initialize(ema_period=200, historical_limit=300)
        await self._refresh_daily_open_price(force=True)
        self.position_manager.load_positions()

        if self.config_path and self.config_path.exists():
            self._config_last_mtime = self.config_path.stat().st_mtime

        logger.info("Trading bot initialized successfully")

    async def start(self):
        """Start the trading bot."""
        if self.running:
            logger.warning("Bot already running")
            return

        if not self.market_data:
            await self.initialize()

        self.running = True
        self.emergency_stop.reset()
        self._main_task = asyncio.create_task(self._main_loop())
        self._pnl_task = asyncio.create_task(self._pnl_update_loop())
        if self.config_path:
            self._config_watcher_task = asyncio.create_task(self._config_watcher_loop())

        self._save_bot_state(running=True)
        logger.info("Trading bot started")

    async def stop(self, save_state: bool = True):
        """Stop the trading bot."""
        if not self.running:
            logger.warning("Bot not running")
            return

        self.running = False
        for task in [self._main_task, self._pnl_task, self._config_watcher_task]:
            if task and not task.done():
                task.cancel()

        if save_state:
            self._save_bot_state(running=False)
        logger.info("Trading bot stopped")

    async def emergency_stop_all(self, reason: str = "Emergency stop"):
        """Emergency stop and close all positions."""
        self.emergency_stop.trigger(reason)
        await self.stop(save_state=True)

        for position_set in self.position_manager.get_active_sets():
            await self.close_position_set(
                position_set.set_id,
                reason="Emergency stop",
                close_option_override=True,
            )

        logger.critical("Emergency stop completed")

    def _save_bot_state(self, running: bool):
        """Persist bot running state to disk."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w") as handle:
                json.dump(
                    {"running": running, "last_updated": datetime.now().isoformat()},
                    handle,
                    indent=2,
                )
        except Exception as exc:
            logger.error("Failed to save bot state: %s", exc)

    def _load_bot_state(self) -> bool:
        """Load persisted bot running state."""
        try:
            if not self._state_file.exists():
                return False
            with open(self._state_file) as handle:
                return bool(json.load(handle).get("running", False))
        except Exception as exc:
            logger.error("Failed to load bot state: %s", exc)
            return False

    async def restore_running_state(self):
        """Restore the previously persisted running state."""
        if self._load_bot_state():
            logger.info("Restoring previous bot state: auto-starting bot...")
            try:
                await self.start()
            except Exception as exc:
                logger.error("Failed to restore bot running state: %s", exc)
        else:
            logger.info("Previous bot state: stopped")

    @staticmethod
    def _get_trading_day(now: Optional[datetime] = None) -> str:
        """Return the current UTC trading day key."""
        current = now or datetime.now(timezone.utc)
        return current.astimezone(timezone.utc).strftime("%Y-%m-%d")

    async def _refresh_daily_open_price(self, force: bool = False):
        """Refresh the UTC daily open price from the current 1D candle."""
        trading_day = self._get_trading_day()
        if not force and self._daily_open_day == trading_day and self._daily_open_price is not None:
            return

        klines = await self.client.get_klines(
            symbol=self.config.symbol,
            interval="D",
            category="linear",
            limit=1,
        )
        if not klines:
            raise RuntimeError("Could not fetch daily open price")

        latest_daily = klines[0]
        self._daily_open_price = float(latest_daily[1])
        self._daily_open_day = trading_day
        logger.info(
            "Daily open refreshed for %s: %.2f",
            trading_day,
            self._daily_open_price,
        )

    def _get_used_ladder_levels_for_day(self, trading_day: str) -> set[int]:
        """Return every ladder level already entered for the specified UTC day."""
        used_levels: set[int] = set()
        for position_set in self.position_manager.get_all_sets():
            if position_set.trading_day != trading_day:
                continue
            if position_set.ladder_level is None:
                continue
            if position_set.state == PositionState.ERROR and not position_set.is_active():
                continue
            used_levels.add(position_set.ladder_level)
        return used_levels

    async def _main_loop(self):
        """Main trading loop."""
        logger.info("Main trading loop started")
        while self.running and not self.emergency_stop.is_stopped():
            try:
                await self.market_data.update()
                await self._refresh_daily_open_price()

                if self.config.bias != "off":
                    await self._check_and_handle_entry_signals()

                await self._check_exit_conditions()
                await asyncio.sleep(self.config.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in main loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.config.poll_interval_seconds)

        logger.info("Main trading loop stopped")

    async def _pnl_update_loop(self):
        """PnL update loop."""
        logger.info("PnL update loop started")
        while self.running:
            try:
                await self._update_all_pnl()
                self.position_manager.save_positions()
                await asyncio.sleep(self.config.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in PnL update loop: %s", exc)
                await asyncio.sleep(self.config.poll_interval_seconds)

        logger.info("PnL update loop stopped")

    async def _config_watcher_loop(self):
        """Reload config when the file changes."""
        logger.info("Config watcher loop started")
        while self.running:
            try:
                if self.config_path and self.config_path.exists():
                    current_mtime = self.config_path.stat().st_mtime
                    if self._config_last_mtime and current_mtime > self._config_last_mtime:
                        logger.info("Config file changed, reloading...")
                        await self._reload_config()
                        self._config_last_mtime = current_mtime
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in config watcher loop: %s", exc)
                await asyncio.sleep(5)
        logger.info("Config watcher loop stopped")

    async def _reload_config(self):
        """Reload configuration from disk."""
        if not self.config_path:
            return

        try:
            config_loader = ConfigLoader(str(self.config_path))
            new_config = config_loader.load()
            self.config = new_config
            self.signal_detector = SignalDetector(new_config.entry_levels_pct)
            self.position_manager.max_sets = new_config.max_position_sets
            self.risk_limits.cooldown_minutes = new_config.cooldown_minutes
            self.risk_limits.max_position_sets = new_config.max_position_sets
            logger.info("Config reload complete")
        except Exception as exc:
            logger.error("Failed to reload config: %s", exc)

    async def _check_and_handle_entry_signals(self):
        """Open new entries for every unfilled ladder level currently reached."""
        if not self.market_data or not self.market_data.candle_manager or self._daily_open_price is None:
            return

        latest_candle = self.market_data.candle_manager.get_latest_candle()
        if not latest_candle:
            return

        trading_day = self._get_trading_day()
        used_levels = self._get_used_ladder_levels_for_day(trading_day)
        signals = self.signal_detector.check_signals(
            current_price=latest_candle.close,
            daily_open_price=self._daily_open_price,
            trading_day=trading_day,
            used_levels=used_levels,
        )

        for signal in signals:
            active_count = self.position_manager.count_active_sets()
            can_open, reason = self.risk_limits.can_open_new_position(active_count)
            if not can_open:
                logger.info("Cannot open ladder level %s: %s", signal.ladder_level, reason)
                break
            await self._open_position_set(signal)

    async def _open_position_set(self, signal: Signal):
        """Open one futures position and its optional hedge put."""
        logger.info("Opening position set for signal: %s", signal)

        position_set = PositionSet(
            bias="long",
            target_profit_pct=self.config.target_profit_pct,
            max_loss_usd=self.config.max_loss_usd,
            entry_signal_price=signal.price,
            daily_open_price=signal.daily_open_price,
            trading_day=signal.trading_day,
            ladder_level=signal.ladder_level,
            trigger_pct=signal.trigger_pct,
            close_hedge_with_future=self.config.hedge_config.close_with_future,
        )

        if not self.position_manager.add_position_set(position_set):
            logger.error("Failed to add position set to manager")
            return

        try:
            perp_leg = await self.order_manager.open_perp_leg(
                symbol=self.config.symbol,
                side="long",
                qty=self.config.perp_qty,
            )
            if not perp_leg or not perp_leg.filled:
                raise Exception("Failed to open perpetual leg")

            position_set.perp_leg = perp_leg
            position_set.target_exit_price = perp_leg.entry_price * (1 + (self.config.target_profit_pct / 100))

            if self.config.hedge_config.enabled:
                base_coin = self.config.symbol.replace("USDT", "").replace("USDC", "")
                instruments = await self.order_manager.option_selector.fetch_instruments(base_coin=base_coin)
                selected_option = self.order_manager.option_selector.select_otm_put_option(
                    spot_price=perp_leg.entry_price or signal.price,
                    min_otm_pct=self.config.hedge_config.hedge_otm_pct,
                    min_dte=self.config.hedge_config.hedge_dte_min_days,
                    instruments=instruments,
                )
                if not selected_option:
                    raise Exception("No suitable hedge put option found")

                option_leg = await self.order_manager.open_option_leg(
                    option_instrument=selected_option,
                    side="long",
                    contracts=self.config.perp_qty,
                    slippage_bps=self.config.hedge_config.slippage_bps,
                )
                if not option_leg or not option_leg.filled:
                    raise Exception("Failed to open hedge option leg")
                position_set.option_leg = option_leg

            position_set.mark_as_open()
            self.position_manager.save_positions()
            self.risk_limits.record_entry()
            logger.info("Position set %s opened successfully", position_set.set_id)
        except Exception as exc:
            logger.error("Failed to open position set: %s", exc)
            position_set.mark_as_error(str(exc))
            self.position_manager.save_positions()
            if position_set.perp_leg and position_set.perp_leg.filled and not position_set.perp_leg.closed:
                try:
                    await self.order_manager.close_leg(position_set.perp_leg, category="linear")
                except Exception as close_exc:
                    logger.error("Failed to unwind perpetual leg after hedge failure: %s", close_exc)

    async def _check_exit_conditions(self):
        """Check exit conditions for every active position set."""
        for position_set in self.position_manager.get_active_sets():
            if position_set.state == PositionState.OPEN:
                should_exit, reason = position_set.check_exit_conditions()
                if should_exit:
                    logger.info("Exit condition met for %s: %s", position_set.set_id, reason)
                    await self.close_position_set(
                        position_set.set_id,
                        reason=reason or "Target reached",
                        close_option_override=position_set.close_hedge_with_future,
                    )
            elif position_set.state == PositionState.CLOSING:
                await self.close_position_set(
                    position_set.set_id,
                    reason="Retry after restart",
                    close_option_override=True,
                )

    async def close_position_set(
        self,
        set_id: str,
        reason: str = "Manual close",
        close_option_override: Optional[bool] = True,
    ):
        """Close a specific position set."""
        position_set = self.position_manager.get_position_set(set_id)
        if not position_set:
            logger.error("Position set %s not found", set_id)
            return False

        if position_set.state not in [
            PositionState.OPEN,
            PositionState.PARTIAL,
            PositionState.CLOSING,
            PositionState.ERROR,
            PositionState.HEDGE_ONLY,
        ]:
            logger.warning("Position set %s not in closeable state: %s", set_id, position_set.state)
            return False

        position_set.mark_as_closing()
        logger.info("Closing position set %s: %s", set_id, reason)

        try:
            if position_set.perp_leg and position_set.perp_leg.filled and not position_set.perp_leg.closed:
                await self.order_manager.close_leg(position_set.perp_leg, category="linear")

            close_option = close_option_override if close_option_override is not None else True
            if (
                close_option
                and position_set.option_leg
                and position_set.option_leg.filled
                and not position_set.option_leg.closed
            ):
                await self.order_manager.close_leg(position_set.option_leg, category="option")

            await self._update_position_set_pnl(position_set)

            if (
                position_set.option_leg
                and position_set.option_leg.filled
                and not position_set.option_leg.closed
            ):
                position_set.mark_as_hedge_only()
            else:
                position_set.mark_as_closed()

            self.position_manager.save_positions()
            return True
        except Exception as exc:
            logger.error("Error closing position set %s: %s", set_id, exc)
            position_set.state = PositionState.OPEN if position_set.perp_leg and not position_set.perp_leg.closed else PositionState.HEDGE_ONLY
            position_set.error_message = f"Close attempt failed (will retry): {exc}"
            self.position_manager.save_positions()
            return False

    async def _update_all_pnl(self):
        """Update PnL for all active position sets."""
        for position_set in self.position_manager.get_active_sets():
            await self._update_position_set_pnl(position_set)

    @staticmethod
    def _parse_ticker_price(ticker: dict, *fields: str) -> float:
        """Extract the first positive ticker price from a list of fields."""
        for field in fields:
            raw = ticker.get(field)
            if raw is None:
                continue
            try:
                value = float(raw)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                continue
        return 0.0

    async def _update_position_set_pnl(self, position_set: PositionSet):
        """Update PnL for a single position set."""
        try:
            if position_set.perp_leg and position_set.perp_leg.filled and not position_set.perp_leg.closed:
                ticker = await self.client.get_tickers(symbol=position_set.perp_leg.symbol, category="linear")
                bid_price = self._parse_ticker_price(ticker, "bid1Price", "markPrice")
                ask_price = self._parse_ticker_price(ticker, "ask1Price", "markPrice")
                position_set.perp_leg.update_pnl(bid_price, ask_price)

            if position_set.option_leg and position_set.option_leg.filled and not position_set.option_leg.closed:
                ticker = await self.client.get_tickers(symbol=position_set.option_leg.symbol, category="option")
                mark_price = self._parse_ticker_price(ticker, "markPrice")
                bid_price = self._parse_ticker_price(ticker, "bid1Price", "markPrice") or mark_price
                ask_price = self._parse_ticker_price(ticker, "ask1Price", "markPrice") or mark_price
                if bid_price or ask_price:
                    position_set.option_leg.update_pnl(bid_price, ask_price)

            position_set.update_combined_pnl()
        except Exception as exc:
            logger.error("Error updating PnL for %s: %s", position_set.set_id, exc)

    def get_status(self) -> dict:
        """Get bot status for API and WebSocket responses."""
        latest_candle = self.market_data.candle_manager.get_latest_candle() if self.market_data else None
        current_price = latest_candle.close if latest_candle else None
        current_drawdown_pct = None
        if current_price is not None and self._daily_open_price:
            current_drawdown_pct = self.signal_detector.compute_drawdown_pct(self._daily_open_price, current_price)

        trading_day = self._get_trading_day()
        filled_levels_today = sorted(self._get_used_ladder_levels_for_day(trading_day))

        return {
            "bot_name": self.config.bot_name,
            "symbol": self.config.symbol,
            "running": self.running,
            "bias": self.config.bias,
            "dry_run": self.dry_run,
            "testnet": self.config.use_testnet,
            "emergency_stop": self.emergency_stop.get_status(),
            "active_position_sets": self.position_manager.count_active_sets(),
            "max_position_sets": self.config.max_position_sets,
            "cooldown_remaining": self.risk_limits.get_cooldown_remaining(),
            "latest_candle_time": latest_candle.datetime.isoformat() if latest_candle else None,
            "current_price": current_price,
            "daily_open_price": self._daily_open_price,
            "current_drawdown_pct": current_drawdown_pct,
            "entry_levels_pct": self.config.entry_levels_pct,
            "filled_levels_today": filled_levels_today,
            "target_profit_pct": self.config.target_profit_pct,
            "hedge_enabled": self.config.hedge_config.enabled,
            "close_hedge_with_future": self.config.hedge_config.close_with_future,
            "total_pnl": self.position_manager.get_total_pnl(),
            "total_exposure": self.position_manager.get_total_exposure(),
        }

    async def get_equity(self) -> Optional[float]:
        """Get current equity."""
        if self.dry_run:
            return None

        now = time.monotonic()
        if self._equity_cache is not None and (now - self._equity_cache_ts) < self._equity_cache_ttl_seconds:
            return self._equity_cache

        try:
            async with self._equity_lock:
                now = time.monotonic()
                if self._equity_cache is not None and (now - self._equity_cache_ts) < self._equity_cache_ttl_seconds:
                    return self._equity_cache

                wallet = await self.client.get_wallet_balance(account_type="UNIFIED")
                if "list" in wallet and wallet["list"]:
                    total_equity = float(wallet["list"][0].get("totalEquity", 0))
                    self._equity_cache = total_equity
                    self._equity_cache_ts = now
                    return total_equity
        except Exception as exc:
            if self._equity_cache is not None:
                logger.warning("Failed to refresh equity, using cached value: %s", exc)
                return self._equity_cache
            logger.error("Failed to get equity: %s", exc)
            return None

        return None
