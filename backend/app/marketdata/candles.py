"""Market data and candles with EMA calculation."""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """Single candlestick data."""
    timestamp: int  # Unix timestamp in ms
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000)

    def __repr__(self):
        return f"Candle({self.datetime.strftime('%Y-%m-%d %H:%M')}, C={self.close:.2f})"


class CandleManager:
    """
    Manages candle data and EMA calculations.

    Ensures no duplicate candles (by timestamp) and provides EMA computation.
    Uses standard EMA formula with SMA seed for first period.
    """

    def __init__(self, ema_period: int = 200):
        self.ema_period = ema_period
        self.candles: List[Candle] = []
        self._candle_timestamps: set = set()
        self._last_ema: Optional[float] = None

    def add_candle(self, candle: Candle) -> bool:
        """
        Add a candle if not duplicate.

        Returns:
            True if candle was added, False if duplicate
        """
        if candle.timestamp in self._candle_timestamps:
            return False

        self.candles.append(candle)
        self._candle_timestamps.add(candle.timestamp)

        # Keep sorted by timestamp
        self.candles.sort(key=lambda c: c.timestamp)

        # Keep only what we need for EMA
        if len(self.candles) > self.ema_period + 100:
            removed = self.candles.pop(0)
            self._candle_timestamps.discard(removed.timestamp)

        return True

    def add_candles_from_bybit(self, klines: List[List]) -> int:
        """
        Add candles from Bybit kline response.

        Bybit returns: [startTime, open, high, low, close, volume, turnover]

        Returns:
            Number of new candles added
        """
        added = 0
        for kline in klines:
            candle = Candle(
                timestamp=int(kline[0]),
                open=float(kline[1]),
                high=float(kline[2]),
                low=float(kline[3]),
                close=float(kline[4]),
                volume=float(kline[5]),
            )
            if self.add_candle(candle):
                added += 1

        logger.debug(f"Added {added} new candles, total: {len(self.candles)}")
        return added

    def compute_ema(self, period: Optional[int] = None) -> Optional[float]:
        """
        Compute EMA using standard formula.

        EMA = (Close - EMA_prev) * multiplier + EMA_prev
        where multiplier = 2 / (period + 1)

        For first period, use SMA as seed.

        Returns:
            Current EMA value or None if insufficient data
        """
        period = period or self.ema_period

        if len(self.candles) < period:
            logger.debug(f"Insufficient candles for EMA{period}: {len(self.candles)}/{period}")
            return None

        closes = [c.close for c in self.candles]

        # Calculate SMA for first period as seed
        sma = sum(closes[:period]) / period
        ema = sma

        # Calculate EMA for remaining values
        multiplier = 2 / (period + 1)
        for close in closes[period:]:
            ema = (close - ema) * multiplier + ema

        self._last_ema = ema
        return ema

    def get_ema_series(self, period: Optional[int] = None) -> List[Tuple[datetime, float]]:
        """
        Get full EMA series with timestamps.

        Returns:
            List of (datetime, ema_value) tuples
        """
        period = period or self.ema_period

        if len(self.candles) < period:
            return []

        closes = [c.close for c in self.candles]
        timestamps = [c.datetime for c in self.candles]

        # SMA seed
        sma = sum(closes[:period]) / period
        ema = sma
        ema_series = [(timestamps[period - 1], ema)]

        # Rest of EMA
        multiplier = 2 / (period + 1)
        for i, close in enumerate(closes[period:], start=period):
            ema = (close - ema) * multiplier + ema
            ema_series.append((timestamps[i], ema))

        return ema_series

    def get_latest_candle(self) -> Optional[Candle]:
        """Get most recent candle."""
        return self.candles[-1] if self.candles else None

    def get_previous_candle(self) -> Optional[Candle]:
        """Get second most recent candle."""
        return self.candles[-2] if len(self.candles) >= 2 else None

    def get_candles(self, n: int) -> List[Candle]:
        """Get last n candles."""
        return self.candles[-n:] if len(self.candles) >= n else self.candles

    def get_last_ema(self) -> Optional[float]:
        """Get last computed EMA value."""
        return self._last_ema

    def clear(self):
        """Clear all candle data."""
        self.candles.clear()
        self._candle_timestamps.clear()
        self._last_ema = None

    def __len__(self):
        return len(self.candles)

    def __repr__(self):
        return f"CandleManager({len(self.candles)} candles, EMA{self.ema_period})"


class MarketDataFeed:
    """
    High-level market data interface.

    Fetches candles from exchange and manages CandleManager.
    """

    def __init__(self, exchange_client, symbol: str = "ETHUSDT", interval: str = "5"):
        self.client = exchange_client
        self.symbol = symbol
        self.interval = interval
        self.candle_manager: Optional[CandleManager] = None

    async def initialize(self, ema_period: int = 200, historical_limit: int = 200):
        """
        Initialize with historical candles.

        Fetches enough historical data to compute EMA.
        """
        self.candle_manager = CandleManager(ema_period)

        logger.info(f"Fetching {historical_limit} historical {self.interval}m candles for {self.symbol}")
        klines = await self.client.get_klines(
            symbol=self.symbol,
            interval=self.interval,
            limit=historical_limit,
        )

        # Bybit returns newest first, reverse to oldest first
        klines.reverse()

        added = self.candle_manager.add_candles_from_bybit(klines)
        logger.info(f"Initialized with {added} candles")

        # Compute initial EMA
        ema = self.candle_manager.compute_ema()
        if ema:
            logger.info(f"Computed EMA{ema_period}: {ema:.2f}")
        else:
            logger.warning(f"Could not compute EMA{ema_period} (need at least {ema_period} candles)")

    async def update(self) -> int:
        """
        Fetch latest candles and update manager.

        Returns:
            Number of new candles added
        """
        if not self.candle_manager:
            raise RuntimeError("MarketDataFeed not initialized")

        # Fetch last few candles
        klines = await self.client.get_klines(
            symbol=self.symbol,
            interval=self.interval,
            limit=10,
        )

        klines.reverse()
        added = self.candle_manager.add_candles_from_bybit(klines)

        # Recompute EMA after adding new candles
        if added > 0:
            self.candle_manager.compute_ema()

        return added

    def get_current_price(self) -> Optional[float]:
        """Get current close price from latest candle."""
        if not self.candle_manager:
            return None
        candle = self.candle_manager.get_latest_candle()
        return candle.close if candle else None

    async def get_live_price(self) -> Optional[float]:
        """Get live price from ticker."""
        try:
            ticker = await self.client.get_tickers(symbol=self.symbol)
            return float(ticker.get("lastPrice", 0))
        except Exception as e:
            logger.error(f"Failed to get live price: {e}")
            return None
