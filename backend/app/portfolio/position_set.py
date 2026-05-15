"""Position set management with combined PnL tracking."""
import logging
from typing import Optional, Literal, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid
import json
from pathlib import Path

logger = logging.getLogger(__name__)

BOT_POSITION_TAG = "daily_ladder_bot"


class PositionState(str, Enum):
    """Position set state machine."""
    OPENING = "opening"  # Orders being placed
    OPEN = "open"  # Both legs filled
    CLOSING = "closing"  # Closing orders being placed
    CLOSED = "closed"  # Both legs closed
    ERROR = "error"  # Error state
    PARTIAL = "partial"  # One leg filled, other failed
    HEDGE_ONLY = "hedge_only"  # Futures leg closed, hedge option intentionally left open


@dataclass
class Leg:
    """Individual position leg (perp or option)."""
    leg_type: Literal["perp", "option"]
    symbol: str
    side: Literal["short", "long"]
    qty: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    mark_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    close_order_id: Optional[str] = None
    close_client_order_id: Optional[str] = None
    filled: bool = False
    filled_qty: float = 0.0
    closed: bool = False

    # Option-specific fields
    strike: Optional[float] = None
    expiry: Optional[str] = None
    option_type: Optional[Literal["Call", "Put"]] = None

    def update_pnl(self, bid_price: float, ask_price: float):
        """
        Update unrealized PnL based on current bid/ask prices with trading fees.

        Uses realistic exit prices:
        - For LONG: Use bid price (what we can sell at)
        - For SHORT: Use ask price (what we need to buy back at)

        Trading fees:
        - Futures (perp): 0.05% of entry price (entry + exit = 0.1% total)
        - Options: 0.02% of strike price (entry + exit = 0.04% total)

        Formula:
        For SHORT: PnL = (entry_price - ask_price) * qty - fees
        For LONG: PnL = (bid_price - entry_price) * qty - fees
        """
        if not self.filled or self.entry_price is None:
            self.unrealized_pnl = 0.0
            return

        # Calculate exit price based on side
        if self.side == "short":
            exit_price = ask_price  # Need to buy back at ask
            price_pnl = (self.entry_price - exit_price) * self.filled_qty
        else:  # long
            exit_price = bid_price  # Can sell at bid
            price_pnl = (exit_price - self.entry_price) * self.filled_qty

        # Store mark price (midpoint) for display
        self.mark_price = (bid_price + ask_price) / 2

        # Calculate trading fees
        if self.leg_type == "perp":
            # Futures: 0.05% on entry + 0.05% on exit = 0.1% total
            # Use entry price as reference (conservative estimate)
            fees = self.entry_price * self.filled_qty * 0.001  # 0.1% total
        else:  # option
            # Options: 0.02% on entry + 0.02% on exit = 0.04% total
            # Use strike price as reference
            if self.strike:
                fees = self.strike * self.filled_qty * 0.0004  # 0.04% total
            else:
                # Fallback to mark price if strike not available
                fees = self.mark_price * self.filled_qty * 0.0004

        # Net PnL after fees
        self.unrealized_pnl = price_pnl - fees

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "leg_type": self.leg_type,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl,
            "filled": self.filled,
            "filled_qty": self.filled_qty,
            "closed": self.closed,
            "strike": self.strike,
            "expiry": self.expiry,
            "option_type": self.option_type,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "close_order_id": self.close_order_id,
            "close_client_order_id": self.close_client_order_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Leg':
        """Create Leg from dictionary."""
        return Leg(
            leg_type=data["leg_type"],
            symbol=data["symbol"],
            side=data["side"],
            qty=data["qty"],
            entry_price=data.get("entry_price"),
            exit_price=data.get("exit_price"),
            mark_price=data.get("mark_price"),
            unrealized_pnl=data.get("unrealized_pnl", 0.0),
            order_id=data.get("order_id"),
            client_order_id=data.get("client_order_id"),
            close_order_id=data.get("close_order_id"),
            close_client_order_id=data.get("close_client_order_id"),
            filled=data.get("filled", False),
            filled_qty=data.get("filled_qty", 0.0),
            closed=data.get("closed", False),
            strike=data.get("strike"),
            expiry=data.get("expiry"),
            option_type=data.get("option_type"),
        )


@dataclass
class PositionSet:
    """
    A position set consisting of a perpetual leg and an option leg.

    Tracks combined PnL and manages exit logic.
    """
    set_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    bias: Literal["short", "long"] = "short"
    perp_leg: Optional[Leg] = None
    option_leg: Optional[Leg] = None
    state: PositionState = PositionState.OPENING
    created_at: datetime = field(default_factory=datetime.now)
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    # Exit parameters
    target_profit_pct: float = 1.0
    target_exit_price: Optional[float] = None
    max_loss_usd: Optional[float] = None

    # Combined PnL
    combined_pnl: float = 0.0
    high_water_mark: float = 0.0

    # Metadata
    strategy_tag: str = BOT_POSITION_TAG
    entry_signal_price: Optional[float] = None
    daily_open_price: Optional[float] = None
    trading_day: Optional[str] = None
    ladder_level: Optional[int] = None
    trigger_pct: Optional[float] = None
    close_hedge_with_future: bool = True
    error_message: Optional[str] = None

    def update_combined_pnl(self) -> float:
        """
        Update combined PnL from both legs.

        Includes closed legs so the final realized PnL is preserved after close.

        Returns:
            Current combined PnL
        """
        self.combined_pnl = 0.0

        if self.perp_leg and self.perp_leg.filled:
            self.combined_pnl += self.perp_leg.unrealized_pnl

        if self.option_leg and self.option_leg.filled:
            self.combined_pnl += self.option_leg.unrealized_pnl

        # Track high water mark
        if self.combined_pnl > self.high_water_mark:
            self.high_water_mark = self.combined_pnl

        return self.combined_pnl

    def is_bot_managed(self, bot_tag: str = BOT_POSITION_TAG) -> bool:
        """Return True only for position sets created and managed by this bot."""
        if self.strategy_tag == bot_tag:
            return True

        leg_client_ids = [
            self.perp_leg.client_order_id if self.perp_leg else None,
            self.option_leg.client_order_id if self.option_leg else None,
            self.perp_leg.close_client_order_id if self.perp_leg else None,
            self.option_leg.close_client_order_id if self.option_leg else None,
        ]
        return any(client_id and client_id.startswith(f"{bot_tag}_") for client_id in leg_client_ids)

    def check_exit_conditions(self) -> tuple[bool, Optional[str]]:
        """
        Check if exit conditions are met.

        Returns:
            (should_exit, reason)
        """
        if self.state != PositionState.OPEN:
            return False, None

        if (
            self.perp_leg
            and self.perp_leg.filled
            and not self.perp_leg.closed
            and self.perp_leg.mark_price is not None
            and self.target_exit_price is not None
            and self.perp_leg.mark_price >= self.target_exit_price
        ):
            return True, (
                f"Futures target reached: mark ${self.perp_leg.mark_price:.2f} "
                f">= target ${self.target_exit_price:.2f}"
            )

        # Max loss (max_loss_usd=0 or None means stop-loss is disabled)
        if self.max_loss_usd and self.combined_pnl <= -self.max_loss_usd:
            return True, f"Max loss hit: ${self.combined_pnl:.2f}"

        return False, None

    def mark_as_open(self):
        """Mark position set as fully open."""
        self.state = PositionState.OPEN
        self.opened_at = datetime.now()
        logger.info(f"Position set {self.set_id} is now OPEN")

    def mark_as_closing(self):
        """Mark position set as closing."""
        self.state = PositionState.CLOSING
        logger.info(f"Position set {self.set_id} is now CLOSING")

    def mark_as_closed(self):
        """Mark position set as closed."""
        self.state = PositionState.CLOSED
        self.closed_at = datetime.now()
        logger.info(f"Position set {self.set_id} is now CLOSED with PnL: ${self.combined_pnl:.2f}")

    def mark_as_hedge_only(self):
        """Mark position set as hedge-only after futures exit."""
        self.state = PositionState.HEDGE_ONLY
        logger.info(f"Position set {self.set_id} is now HEDGE_ONLY")

    def mark_as_error(self, error: str):
        """Mark position set as error."""
        self.state = PositionState.ERROR
        self.error_message = error
        logger.error(f"Position set {self.set_id} error: {error}")

    def is_active(self) -> bool:
        """Check if position set is active (opening, open, or closing)."""
        return self.state in [
            PositionState.OPENING,
            PositionState.OPEN,
            PositionState.CLOSING,
            PositionState.HEDGE_ONLY,
        ]

    def is_complete(self) -> bool:
        """Check if position set is complete (closed or error)."""
        return self.state in [PositionState.CLOSED, PositionState.ERROR]

    def get_hold_time_minutes(self) -> Optional[float]:
        """Get current hold time in minutes."""
        if not self.opened_at:
            return None
        return (datetime.now() - self.opened_at).total_seconds() / 60

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/storage."""
        return {
            "set_id": self.set_id,
            "bias": self.bias,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "perp_leg": self.perp_leg.to_dict() if self.perp_leg else None,
            "option_leg": self.option_leg.to_dict() if self.option_leg else None,
            "combined_pnl": self.combined_pnl,
            "high_water_mark": self.high_water_mark,
            "target_profit_pct": self.target_profit_pct,
            "target_exit_price": self.target_exit_price,
            "max_loss_usd": self.max_loss_usd,
            "strategy_tag": self.strategy_tag,
            "hold_time_minutes": self.get_hold_time_minutes(),
            "entry_signal_price": self.entry_signal_price,
            "daily_open_price": self.daily_open_price,
            "trading_day": self.trading_day,
            "ladder_level": self.ladder_level,
            "trigger_pct": self.trigger_pct,
            "close_hedge_with_future": self.close_hedge_with_future,
            "error_message": self.error_message,
        }

    def __repr__(self):
        return f"PositionSet({self.set_id}, {self.state.value}, PnL=${self.combined_pnl:.2f})"

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'PositionSet':
        """Create PositionSet from dictionary."""
        ps = PositionSet(
            set_id=data["set_id"],
            bias=data["bias"],
            state=PositionState(data["state"]),
            target_profit_pct=data.get("target_profit_pct", 1.0),
            target_exit_price=data.get("target_exit_price"),
            max_loss_usd=data.get("max_loss_usd"),
            combined_pnl=data.get("combined_pnl", 0.0),
            high_water_mark=data.get("high_water_mark", 0.0),
            strategy_tag=data.get("strategy_tag") or "",
            entry_signal_price=data.get("entry_signal_price"),
            daily_open_price=data.get("daily_open_price"),
            trading_day=data.get("trading_day"),
            ladder_level=data.get("ladder_level"),
            trigger_pct=data.get("trigger_pct"),
            close_hedge_with_future=data.get("close_hedge_with_future", True),
            error_message=data.get("error_message"),
        )

        # Parse timestamps
        ps.created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        ps.opened_at = datetime.fromisoformat(data["opened_at"]) if data.get("opened_at") else None
        ps.closed_at = datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None

        # Restore legs
        if data.get("perp_leg"):
            ps.perp_leg = Leg.from_dict(data["perp_leg"])
        if data.get("option_leg"):
            ps.option_leg = Leg.from_dict(data["option_leg"])

        if not data.get("strategy_tag") and (
            (ps.perp_leg and ps.perp_leg.client_order_id and ps.perp_leg.client_order_id.startswith(f"{BOT_POSITION_TAG}_")) or
            (ps.option_leg and ps.option_leg.client_order_id and ps.option_leg.client_order_id.startswith(f"{BOT_POSITION_TAG}_"))
        ):
            ps.strategy_tag = BOT_POSITION_TAG

        return ps


class PositionManager:
    """Manages multiple position sets."""

    def __init__(self, max_sets: int = 3, persistence_file: Optional[Path] = None):
        self.max_sets = max_sets
        self.position_sets: Dict[str, PositionSet] = {}
        self.persistence_file = persistence_file or Path("data/positions.json")
        self.persistence_file.parent.mkdir(parents=True, exist_ok=True)

    def add_position_set(self, position_set: PositionSet) -> bool:
        """
        Add a new position set.

        Returns:
            True if added, False if max sets reached
        """
        active_count = self.count_active_sets()
        if active_count >= self.max_sets:
            logger.warning(f"Max position sets reached: {active_count}/{self.max_sets}")
            return False

        self.position_sets[position_set.set_id] = position_set
        logger.info(f"Added position set {position_set.set_id} (state={position_set.state.value})")
        if position_set.option_leg:
            logger.debug(f"  - Option leg: filled={position_set.option_leg.filled}, qty={position_set.option_leg.filled_qty}")
        return True

    def get_position_set(self, set_id: str) -> Optional[PositionSet]:
        """Get position set by ID."""
        return self.position_sets.get(set_id)

    def get_active_sets(self) -> list[PositionSet]:
        """Get all active position sets."""
        return [ps for ps in self.position_sets.values() if ps.is_active()]

    def get_all_sets(self) -> list[PositionSet]:
        """Get all position sets."""
        return list(self.position_sets.values())

    def count_active_sets(self) -> int:
        """Count active position sets."""
        return len(self.get_active_sets())

    def update_all_pnl(self):
        """Update PnL for all active position sets."""
        for ps in self.get_active_sets():
            ps.update_combined_pnl()

    def remove_set(self, set_id: str):
        """Remove a position set."""
        if set_id in self.position_sets:
            del self.position_sets[set_id]
            logger.info(f"Removed position set {set_id}")

    def cleanup_old_sets(self, days: int = 7):
        """Remove closed sets older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)
        to_remove = []

        for set_id, ps in self.position_sets.items():
            if ps.state == PositionState.CLOSED and ps.closed_at and ps.closed_at < cutoff:
                to_remove.append(set_id)

        for set_id in to_remove:
            self.remove_set(set_id)

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old position sets")

    def get_total_exposure(self) -> Dict[str, float]:
        """Get total exposure across all active sets."""
        total_perp_qty = 0.0
        total_option_contracts = 0.0

        active_sets = self.get_active_sets()
        for ps in active_sets:
            if ps.perp_leg and ps.perp_leg.filled:
                total_perp_qty += ps.perp_leg.filled_qty
            if ps.option_leg and ps.option_leg.filled:
                total_option_contracts += ps.option_leg.filled_qty
                logger.debug(f"Position {ps.set_id} has option leg: qty={ps.option_leg.filled_qty}, total={total_option_contracts}")
            elif ps.option_leg:
                logger.debug(f"Position {ps.set_id} has option leg but not filled: filled={ps.option_leg.filled}")

        return {
            "perp_qty": total_perp_qty,
            "option_contracts": total_option_contracts,
        }

    def get_total_pnl(self) -> float:
        """Get total PnL across all active sets."""
        return sum(ps.combined_pnl for ps in self.get_active_sets())

    def get_last_entry_price(self, bias: str) -> Optional[float]:
        """
        Get the last entry price for active positions.

        Args:
            bias: "short" or "long"

        Returns:
            Last entry signal price or None if no active positions
        """
        active_sets = self.get_active_sets()
        if not active_sets:
            return None

        # Get positions with the same bias
        same_bias_sets = [ps for ps in active_sets if ps.bias == bias and ps.entry_signal_price]

        if not same_bias_sets:
            return None

        # Return the most recent entry price
        most_recent = max(same_bias_sets, key=lambda ps: ps.created_at)
        return most_recent.entry_signal_price

    def check_zone_condition(self, current_price: float, bias: str, zone_size_usd: float) -> tuple[bool, Optional[str]]:
        """
        Check if current price meets zone condition for new entry.

        For SHORT: New entry only if price is HIGHER than last entry by zone_size_usd
                   (better short entry — shorting at a higher price)
        For LONG:  New entry only if price is LOWER than last entry by zone_size_usd
                   (better long entry — buying at a lower price)

        Args:
            current_price: Current market price
            bias: Trading bias ("short" or "long")
            zone_size_usd: Zone size in USD

        Returns:
            (allowed, reason) tuple
        """
        if zone_size_usd <= 0:
            return True, None  # Zone checking disabled

        last_entry = self.get_last_entry_price(bias)

        if last_entry is None:
            return True, None  # No previous positions, allow entry

        if bias == "short":
            # For SHORT: price must be HIGHER than last entry by zone amount
            # (allows a better short entry — shorting at a higher price than before)
            price_diff = current_price - last_entry
            if price_diff >= zone_size_usd:
                return True, None
            else:
                return False, f"Zone not met: price ${current_price:.2f} needs to be ${zone_size_usd:.2f} higher than last entry ${last_entry:.2f} (diff: ${price_diff:.2f})"

        elif bias == "long":
            # For LONG: price must be LOWER than last entry by zone amount
            # (allows a better long entry — buying at a lower price than before)
            price_diff = last_entry - current_price
            if price_diff >= zone_size_usd:
                return True, None
            else:
                return False, f"Zone not met: price ${current_price:.2f} needs to be ${zone_size_usd:.2f} lower than last entry ${last_entry:.2f} (diff: ${price_diff:.2f})"

        return True, None

    def save_positions(self):
        """Save all position sets to disk."""
        try:
            data = {
                "positions": [ps.to_dict() for ps in self.position_sets.values()],
                "last_saved": datetime.now().isoformat(),
            }

            with open(self.persistence_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(self.position_sets)} position sets to {self.persistence_file}")
        except Exception as e:
            logger.error(f"Failed to save positions: {e}")

    def load_positions(self) -> bool:
        """Load position sets from disk."""
        if not self.persistence_file.exists():
            logger.info("No saved positions found")
            return False

        try:
            with open(self.persistence_file, 'r') as f:
                data = json.load(f)

            positions_data = data.get("positions", [])
            loaded_count = 0

            for ps_data in positions_data:
                try:
                    ps = PositionSet.from_dict(ps_data)
                    if not ps.is_bot_managed():
                        logger.info(
                            f"Skipping non-bot-managed position set {ps.set_id} "
                            f"(strategy_tag={ps.strategy_tag})"
                        )
                        continue
                    self.position_sets[ps.set_id] = ps
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to load position {ps_data.get('set_id')}: {e}")

            logger.info(f"Loaded {loaded_count} position sets from {self.persistence_file}")

            # Log active positions
            active = self.get_active_sets()
            if active:
                logger.info(f"Found {len(active)} active position sets:")
                for ps in active:
                    logger.info(f"  - {ps.set_id}: {ps.bias} {ps.state.value} PnL=${ps.combined_pnl:.2f}")

            return True
        except Exception as e:
            logger.error(f"Failed to load positions: {e}")
            return False
