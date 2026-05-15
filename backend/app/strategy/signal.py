"""Daily drawdown ladder signal detection."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Signal:
    """Entry signal for one daily drawdown ladder level."""

    timestamp: datetime
    trading_day: str
    signal_type: str
    price: float
    daily_open_price: float
    drawdown_pct: float
    trigger_pct: float
    ladder_level: int
    bias: str = "long"

    def __repr__(self) -> str:
        return (
            "Signal("
            f"level={self.ladder_level}, trigger={self.trigger_pct:.2f}%, "
            f"drawdown={self.drawdown_pct:.2f}%, price={self.price:.2f}, "
            f"daily_open={self.daily_open_price:.2f}, day={self.trading_day}"
            ")"
        )


class SignalDetector:
    """Detects drawdown ladder entries from the UTC daily open."""

    def __init__(self, entry_levels_pct: list[float]):
        self.entry_levels_pct = sorted(entry_levels_pct)

    @staticmethod
    def compute_drawdown_pct(daily_open_price: float, current_price: float) -> float:
        """Return the percent drawdown from the daily open."""
        if daily_open_price <= 0:
            return 0.0
        return ((daily_open_price - current_price) / daily_open_price) * 100

    def check_signals(
        self,
        current_price: float,
        daily_open_price: float,
        trading_day: str,
        used_levels: set[int],
    ) -> list[Signal]:
        """Return every unfilled ladder level currently reached."""
        drawdown_pct = self.compute_drawdown_pct(daily_open_price, current_price)
        signals: list[Signal] = []

        for index, trigger_pct in enumerate(self.entry_levels_pct):
            if index in used_levels:
                continue
            if drawdown_pct >= trigger_pct:
                signals.append(
                    Signal(
                        timestamp=datetime.now(),
                        trading_day=trading_day,
                        signal_type="daily_drawdown_entry",
                        price=current_price,
                        daily_open_price=daily_open_price,
                        drawdown_pct=drawdown_pct,
                        trigger_pct=trigger_pct,
                        ladder_level=index,
                    )
                )

        return signals
