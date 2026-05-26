"""Configuration models for the daily open ladder strategy."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HedgeConfig(BaseModel):
    """Configuration for the protective option hedge."""

    enabled: bool = Field(default=True, description="Open a long option hedge with each futures entry")
    hedge_otm_pct: float = Field(
        default=3.0,
        gt=0,
        description="Minimum OTM distance for the hedge strike relative to spot",
    )
    hedge_dte_min_days: int = Field(
        default=20,
        ge=1,
        description="Minimum days to expiry for hedge option selection",
    )
    close_with_future: bool = Field(
        default=True,
        description="Close the hedge option automatically when the futures leg exits",
    )
    slippage_bps: int = Field(
        default=50,
        ge=0,
        description="Fallback slippage for option exit fallback orders",
    )


class BotConfig(BaseModel):
    """Main configuration for the daily open ladder bot."""

    bot_name: str = Field(default="Advantage Price Bot", description="Bot name for identification")
    account_name: str = Field(default="Primary Account", description="Account display name for identification")
    long_symbol: str = Field(default="ETHUSDT", description="Perpetual symbol used for long ladder entries")
    short_symbol: str = Field(default="ETHPERP", description="Perpetual symbol used for short ladder entries")
    bias: Literal["long", "short", "both", "off"] = Field(
        default="both",
        description="Strategy mode. Use off to disable new entries.",
    )
    timeframe: Literal["5m"] = Field(default="5m", description="Polling chart timeframe")

    long_entry_levels_pct: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0],
        description="Drawdown percentages from the UTC 00:00 daily open that trigger long ladder entries",
    )
    short_entry_levels_pct: list[float] = Field(
        default_factory=lambda: [1.0, 2.0, 3.0],
        description="Rally percentages from the UTC 00:00 daily open that trigger short ladder entries",
    )
    target_profit_pct: float = Field(
        default=1.0,
        gt=0,
        description="Take-profit percent from each futures entry price in the favorable direction",
    )
    max_loss_usd: Optional[float] = Field(
        default=None,
        ge=0,
        description="Optional stop-loss per entry pair in USD. Leave null or 0 to disable.",
    )

    max_position_sets: int = Field(default=3, ge=1, le=20, description="Max concurrent tracked entries")
    cooldown_minutes: int = Field(default=0, ge=0, description="Cooldown between entries")
    perp_qty: float = Field(default=0.1, gt=0, description="Futures quantity per ladder entry")

    hedge_config: HedgeConfig = Field(default_factory=HedgeConfig, description="Protective option hedge settings")

    poll_interval_seconds: int = Field(default=10, ge=1, description="Polling interval")
    use_testnet: bool = Field(default=True, description="Use Bybit testnet")
    dry_run: bool = Field(default=True, description="Dry run mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @field_validator("long_entry_levels_pct", "short_entry_levels_pct")
    @classmethod
    def validate_entry_levels_pct(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("entry level arrays must contain at least one percentage")

        cleaned = [round(float(v), 6) for v in value]
        if any(v <= 0 for v in cleaned):
            raise ValueError("entry level values must be positive")
        if cleaned != sorted(cleaned):
            raise ValueError("entry level arrays must be sorted ascending")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("entry level arrays must not contain duplicates")
        return cleaned

    @field_validator("max_loss_usd")
    @classmethod
    def validate_max_loss(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("max_loss_usd must be >= 0")
        return value

    class Config:
        json_schema_extra = {
            "example": {
                "bot_name": "Advantage Price Bot",
                "account_name": "Primary Account",
                "long_symbol": "ETHUSDT",
                "short_symbol": "ETHPERP",
                "bias": "both",
                "timeframe": "5m",
                "long_entry_levels_pct": [1.0, 2.0, 3.0],
                "short_entry_levels_pct": [1.0, 2.0, 3.0],
                "target_profit_pct": 1.0,
                "max_loss_usd": 200.0,
                "max_position_sets": 3,
                "cooldown_minutes": 0,
                "perp_qty": 0.1,
                "hedge_config": {
                    "enabled": True,
                    "hedge_otm_pct": 3.0,
                    "hedge_dte_min_days": 20,
                    "close_with_future": True,
                    "slippage_bps": 50,
                },
                "poll_interval_seconds": 10,
                "use_testnet": True,
                "dry_run": True,
                "log_level": "INFO",
            }
        }
