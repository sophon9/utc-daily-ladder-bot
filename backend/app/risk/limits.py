"""Risk management and limits."""
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RiskLimits:
    """
    Enforces risk limits and cooldowns.

    Tracks when last entry occurred and enforces cooldown period.
    """

    def __init__(self, cooldown_minutes: int = 60, max_position_sets: int = 3):
        self.cooldown_minutes = cooldown_minutes
        self.max_position_sets = max_position_sets
        self._last_entry_time: Optional[datetime] = None

    def record_entry(self):
        """Record that a new entry was made."""
        self._last_entry_time = datetime.now()
        logger.info(f"Entry recorded, cooldown until {self.get_cooldown_expiry()}")

    def is_in_cooldown(self) -> bool:
        """Check if currently in cooldown period."""
        if not self._last_entry_time:
            return False

        elapsed = (datetime.now() - self._last_entry_time).total_seconds() / 60
        return elapsed < self.cooldown_minutes

    def get_cooldown_remaining(self) -> float:
        """Get remaining cooldown time in minutes."""
        if not self._last_entry_time:
            return 0.0

        elapsed = (datetime.now() - self._last_entry_time).total_seconds() / 60
        remaining = self.cooldown_minutes - elapsed
        return max(0.0, remaining)

    def get_cooldown_expiry(self) -> Optional[datetime]:
        """Get cooldown expiry time."""
        if not self._last_entry_time:
            return None
        return self._last_entry_time + timedelta(minutes=self.cooldown_minutes)

    def can_open_new_position(self, current_position_count: int) -> tuple[bool, Optional[str]]:
        """
        Check if new position can be opened.

        Returns:
            (allowed, reason_if_not_allowed)
        """
        # Check cooldown
        if self.is_in_cooldown():
            remaining = self.get_cooldown_remaining()
            return False, f"Cooldown active: {remaining:.1f} minutes remaining"

        # Check max positions
        if current_position_count >= self.max_position_sets:
            return False, f"Max position sets reached: {current_position_count}/{self.max_position_sets}"

        return True, None

    def reset(self):
        """Reset all limits."""
        self._last_entry_time = None
        logger.info("Risk limits reset")


class EmergencyStop:
    """
    Emergency stop mechanism.

    Can be triggered manually or by system conditions.
    """

    def __init__(self):
        self._stopped = False
        self._stop_reason: Optional[str] = None
        self._stop_time: Optional[datetime] = None

    def trigger(self, reason: str = "Manual stop"):
        """Trigger emergency stop."""
        self._stopped = True
        self._stop_reason = reason
        self._stop_time = datetime.now()
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")

    def reset(self):
        """Reset emergency stop."""
        self._stopped = False
        self._stop_reason = None
        self._stop_time = None
        logger.info("Emergency stop reset")

    def is_stopped(self) -> bool:
        """Check if stopped."""
        return self._stopped

    def get_status(self) -> dict:
        """Get stop status."""
        return {
            "stopped": self._stopped,
            "reason": self._stop_reason,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
        }
