"""Persist and summarize account equity history."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EquitySnapshot:
    """One equity sample."""

    timestamp: str
    equity: float


class EquityHistoryStore:
    """Append-only local store for equity samples."""

    def __init__(
        self,
        history_file: Path | None = None,
        max_points: int = 2000,
        min_interval_seconds: int = 60,
        min_change_usd: float = 1.0,
    ):
        self.history_file = history_file or Path("data/equity_history.json")
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_points = max_points
        self.min_interval_seconds = min_interval_seconds
        self.min_change_usd = min_change_usd

    def _load_raw(self) -> list[dict]:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r") as handle:
                data = json.load(handle)
            return data.get("points", [])
        except Exception:
            return []

    def _save_raw(self, points: list[dict]):
        payload = {
            "points": points[-self.max_points:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.history_file, "w") as handle:
            json.dump(payload, handle, indent=2)

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime:
        return datetime.fromisoformat(timestamp)

    def record(self, equity: float) -> bool:
        """Record a sample if enough time or value change has passed."""
        if equity <= 0:
            return False

        now = datetime.now(timezone.utc)
        points = self._load_raw()
        if points:
            last = points[-1]
            last_equity = float(last.get("equity", 0))
            last_time = self._parse_timestamp(last["timestamp"])
            elapsed = (now - last_time).total_seconds()
            change = abs(equity - last_equity)
            if elapsed < self.min_interval_seconds and change < self.min_change_usd:
                return False

        snapshot = EquitySnapshot(timestamp=now.isoformat(), equity=equity)
        points.append(asdict(snapshot))
        self._save_raw(points)
        return True

    def get_points(self, limit: int = 200) -> list[EquitySnapshot]:
        """Return recent points."""
        raw_points = self._load_raw()[-limit:]
        return [
            EquitySnapshot(
                timestamp=str(point.get("timestamp")),
                equity=float(point.get("equity", 0)),
            )
            for point in raw_points
        ]
