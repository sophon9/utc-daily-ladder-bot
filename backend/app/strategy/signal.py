"""Daily open ladder signal detection."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Signal:
    """Entry signal for one daily-open ladder level."""

    timestamp: datetime
    trading_day: str
    signal_type: str
    price: float
    daily_open_price: float
    trigger_move_pct: float
    trigger_pct: float
    ladder_level: int
    bias: str = "long"

    def __repr__(self) -> str:
        return (
            "Signal("
            f"level={self.ladder_level}, trigger={self.trigger_pct:.2f}%, "
            f"move={self.trigger_move_pct:.2f}%, bias={self.bias}, price={self.price:.2f}, "
            f"daily_open={self.daily_open_price:.2f}, day={self.trading_day}"
            ")"
        )


class SignalDetector:
    """Detects long or short ladder entries from the UTC daily open."""

    @staticmethod
    def compute_move_pct(
        daily_open_price: float,
        current_price: float,
        bias: Literal["long", "short"] = "long",
    ) -> float:
        """Return the percent move from the daily open in the configured bias direction."""
        if daily_open_price <= 0:
            return 0.0
        if bias == "short":
            return ((current_price - daily_open_price) / daily_open_price) * 100
        return ((daily_open_price - current_price) / daily_open_price) * 100

    def check_signals(
        self,
        current_price: float,
        daily_open_price: float,
        trading_day: str,
        used_levels: set[int],
        entry_levels_pct: list[float],
        bias: Literal["long", "short"] = "long",
    ) -> list[Signal]:
        """Return every unfilled ladder level currently reached."""
        trigger_move_pct = self.compute_move_pct(daily_open_price, current_price, bias=bias)
        signals: list[Signal] = []

        for index, trigger_pct in enumerate(sorted(entry_levels_pct)):
            if index in used_levels:
                continue
            if trigger_move_pct >= trigger_pct:
                signals.append(
                    Signal(
                        timestamp=datetime.now(),
                        trading_day=trading_day,
                        signal_type=f"daily_open_{bias}_entry",
                        price=current_price,
                        daily_open_price=daily_open_price,
                        trigger_move_pct=trigger_move_pct,
                        trigger_pct=trigger_pct,
                        ladder_level=index,
                        bias=bias,
                    )
                )

        return signals
