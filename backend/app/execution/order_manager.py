"""Order execution manager with idempotency and option selection."""
import logging
import asyncio
import uuid
import time
from typing import Optional, Dict, Any, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from app.portfolio.position_set import Leg

logger = logging.getLogger(__name__)


@dataclass
class OptionInstrument:
    """Option instrument details."""
    symbol: str
    strike: float
    expiry: str
    expiry_date: datetime
    option_type: Literal["Call", "Put"]
    dte: int  # Days to expiry
    qty_step: float = 0.1
    min_order_qty: float = 0.1

    def __repr__(self):
        return (
            f"Option({self.symbol}, {self.option_type}, K={self.strike}, DTE={self.dte}, "
            f"qty_step={self.qty_step}, min_qty={self.min_order_qty})"
        )


class OptionSelector:
    """
    Selects appropriate options based on criteria.

    ADJUST HERE IF YOUR BYBIT OPTIONS CATEGORY/SYMBOLS DIFFER:
    - Bybit USDT-settled options use category="option"
    - Symbol format: ETH-30APR25-3000-P (underlying-date-strike-C/P)
    - baseCoin filter for options on specific underlying
    """

    def __init__(self, exchange_client):
        self.client = exchange_client
        self._cache: Dict[str, list] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes

    @staticmethod
    def _safe_float(value: Any) -> float:
        """Convert instrument metadata values to float safely."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    async def fetch_instruments(self, base_coin: str = "ETH", force_refresh: bool = False) -> list[OptionInstrument]:
        """
        Fetch and parse option instruments.

        Returns:
            List of OptionInstrument objects
        """
        cache_key = base_coin

        # Check cache
        if not force_refresh and cache_key in self._cache and self._cache_time:
            if (datetime.now() - self._cache_time).seconds < self._cache_ttl:
                return self._cache[cache_key]

        # Fetch from API
        raw_instruments = await self.client.get_option_instruments(base_coin=base_coin)

        instruments = []
        for inst in raw_instruments:
            try:
                symbol = inst["symbol"]
                # Parse symbol: ETH-25DEC26-1900-P-USDT (new format) or ETH-30APR25-3000-P (old format)
                parts = symbol.split("-")

                # Handle both old (4 parts) and new (5 parts with -USDT suffix) formats
                if len(parts) == 5:
                    # New format: ETH-25DEC26-1900-P-USDT
                    underlying, date_str, strike_str, opt_type_char, settlement = parts
                elif len(parts) == 4:
                    # Old format: ETH-30APR25-3000-P
                    underlying, date_str, strike_str, opt_type_char = parts
                else:
                    continue

                strike = float(strike_str)
                option_type = "Put" if opt_type_char == "P" else "Call"
                lot_size_filter = inst.get("lotSizeFilter", {}) or {}
                qty_step = self._safe_float(
                    lot_size_filter.get("qtyStep") or inst.get("qtyStep")
                ) or 0.1
                min_order_qty = self._safe_float(
                    lot_size_filter.get("minOrderQty") or inst.get("minOrderQty")
                ) or 0.1

                # Parse expiry date
                expiry_timestamp = int(inst.get("deliveryTime", 0))
                expiry_date = datetime.fromtimestamp(expiry_timestamp / 1000) if expiry_timestamp else None

                if not expiry_date:
                    continue

                # Calculate DTE
                dte = (expiry_date - datetime.now()).days

                instruments.append(OptionInstrument(
                    symbol=symbol,
                    strike=strike,
                    expiry=date_str,
                    expiry_date=expiry_date,
                    option_type=option_type,
                    dte=dte,
                    qty_step=qty_step,
                    min_order_qty=min_order_qty,
                ))
            except Exception as e:
                logger.debug(f"Failed to parse option instrument {inst.get('symbol', 'unknown')}: {e}")
                continue

        # Update cache
        self._cache[cache_key] = instruments
        self._cache_time = datetime.now()

        logger.info(f"Fetched {len(instruments)} {base_coin} option instruments")
        return instruments

    def select_otm_put_option(
        self,
        spot_price: float,
        min_otm_pct: float,
        min_dte: int = 20,
        instruments: Optional[list[OptionInstrument]] = None,
    ) -> Optional[OptionInstrument]:
        """
        Select the nearest OTM put strike at or beyond the configured distance.

        Args:
            spot_price: Current spot/mark price
            min_otm_pct: Minimum percent below spot for the strike
            min_dte: Minimum days to expiry
            instruments: Pre-fetched instruments (if available)

        Returns:
            Selected option instrument or None
        """
        if not instruments:
            logger.error("No instruments provided for selection")
            return None

        target_strike = spot_price * (1 - (min_otm_pct / 100))
        candidates = [inst for inst in instruments if inst.option_type == "Put"]

        # Filter by min DTE
        candidates = [inst for inst in candidates if inst.dte >= min_dte]

        if not candidates:
            logger.warning(f"No Put options with DTE >= {min_dte}")
            return None

        # Group by expiry, select nearest expiry that meets DTE requirement.
        nearest_expiry = min(candidates, key=lambda x: x.dte).expiry
        candidates = [inst for inst in candidates if inst.expiry == nearest_expiry]

        otm_candidates = [inst for inst in candidates if inst.strike <= target_strike]
        if not otm_candidates:
            logger.warning(
                "No Put strike found at least %.2f%% OTM for spot %.2f on nearest expiry %s",
                min_otm_pct,
                spot_price,
                nearest_expiry,
            )
            return None

        selected_option = max(otm_candidates, key=lambda x: x.strike)
        logger.info(
            "Selected OTM Put: %s for spot %.2f (target strike <= %.2f)",
            selected_option,
            spot_price,
            target_strike,
        )
        return selected_option


class OrderManager:
    """
    Manages order placement, confirmation, and fills.

    Implements idempotency using client_order_id.
    Handles partial fills and retries.
    """

    BOT_ORDER_PREFIX = "daily_ladder_bot"
    MAX_CLIENT_ORDER_ID_LENGTH = 36
    _BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

    def __init__(self, exchange_client, dry_run: bool = True):
        self.client = exchange_client
        self.dry_run = dry_run
        self.option_selector = OptionSelector(exchange_client)
        self._order_id_sequence = 0

    @classmethod
    def _to_base36(cls, value: int, width: int = 0) -> str:
        """Encode an integer compactly for orderLinkId."""
        if value < 0:
            raise ValueError("value must be non-negative")

        if value == 0:
            encoded = "0"
        else:
            chars = []
            while value:
                value, remainder = divmod(value, 36)
                chars.append(cls._BASE36_ALPHABET[remainder])
            encoded = "".join(reversed(chars))

        return encoded.rjust(width, "0")

    @staticmethod
    def _normalize_order_prefix(prefix: str) -> str:
        """Keep orderLinkId prefix Bybit-safe and readable."""
        normalized = "".join(
            char.lower() if char.isalnum() else "_"
            for char in prefix
        ).strip("_")
        return normalized or "order"

    def generate_client_order_id(self, prefix: str = "ema") -> str:
        """Generate a bot-owned client order ID for idempotency and filtering."""
        normalized_prefix = self._normalize_order_prefix(prefix)
        if normalized_prefix.startswith(f"{self.BOT_ORDER_PREFIX}_"):
            base_prefix = normalized_prefix
        else:
            base_prefix = f"{self.BOT_ORDER_PREFIX}_{normalized_prefix}"

        self._order_id_sequence = (self._order_id_sequence + 1) % (36 ** 3)
        timestamp = self._to_base36(int(time.time() * 1000))[-8:]
        sequence = self._to_base36(self._order_id_sequence, width=3)[-3:]
        random_part = uuid.uuid4().hex[:4]
        suffix = f"{timestamp}{sequence}{random_part}"

        available_prefix_length = self.MAX_CLIENT_ORDER_ID_LENGTH - len(suffix) - 1
        base_prefix = base_prefix[:available_prefix_length].rstrip("_")
        return f"{base_prefix}_{suffix}"

    def is_bot_client_order_id(self, client_order_id: Optional[str]) -> bool:
        """Return True only for orders created by this bot."""
        return bool(client_order_id and client_order_id.startswith(f"{self.BOT_ORDER_PREFIX}_"))

    def _require_bot_client_order_id(self, client_order_id: Optional[str], context: str):
        """Prevent monitoring/cancelling unrelated account orders."""
        if not self.is_bot_client_order_id(client_order_id):
            raise ValueError(
                f"Refusing to {context} non-bot order without a {self.BOT_ORDER_PREFIX}_ orderLinkId: "
                f"{client_order_id or 'missing'}"
            )

    async def get_bot_open_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        """Return only open orders created by this bot."""
        if self.dry_run:
            return []

        orders = await self.client.get_open_orders(
            category=category,
            symbol=symbol,
            limit=limit,
        )
        return [
            order for order in orders
            if self.is_bot_client_order_id(order.get("orderLinkId"))
        ]

    async def place_market_order(
        self,
        symbol: str,
        side: Literal["Buy", "Sell"],
        qty: float,
        category: str = "linear",
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Place a market order.

        Args:
            symbol: Trading symbol
            side: Buy or Sell
            qty: Quantity
            category: linear or option
            reduce_only: Close position only
            client_order_id: Custom order ID

        Returns:
            Order result or None
        """
        if not client_order_id:
            client_order_id = self.generate_client_order_id()
        self._require_bot_client_order_id(client_order_id, "place market order")

        if self.dry_run:
            logger.info(f"[DRY RUN] Place {side} {qty} {symbol} (market, {category})")
            return {
                "orderId": f"dry_{uuid.uuid4().hex[:8]}",
                "orderLinkId": client_order_id,
                "dry_run": True,
            }

        try:
            result = await self.client.place_order(
                symbol=symbol,
                side=side,
                order_type="Market",
                qty=qty,
                category=category,
                client_order_id=client_order_id,
                reduce_only=reduce_only,
            )
            logger.info(f"Placed market order: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to place market order: {e}")
            return None

    async def place_aggressive_limit_order(
        self,
        symbol: str,
        side: Literal["Buy", "Sell"],
        qty: float,
        reference_price: float,
        slippage_bps: int = 50,
        category: str = "option",
        client_order_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Place aggressive limit order (for options if market not supported).

        Args:
            symbol: Trading symbol
            side: Buy or Sell
            qty: Quantity
            reference_price: Reference price (mark/last)
            slippage_bps: Slippage in basis points
            category: Product category
            client_order_id: Custom order ID

        Returns:
            Order result or None
        """
        if not client_order_id:
            client_order_id = self.generate_client_order_id()
        self._require_bot_client_order_id(client_order_id, "place aggressive limit order")

        # Calculate aggressive limit price
        slippage_factor = slippage_bps / 10000
        if side == "Buy":
            limit_price = reference_price * (1 + slippage_factor)
        else:  # Sell
            limit_price = reference_price * (1 - slippage_factor)

        if self.dry_run:
            logger.info(f"[DRY RUN] Place {side} {qty} {symbol} @ {limit_price:.4f} (limit, {category})")
            return {
                "orderId": f"dry_{uuid.uuid4().hex[:8]}",
                "orderLinkId": client_order_id,
                "dry_run": True,
            }

        try:
            result = await self.client.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=qty,
                price=limit_price,
                category=category,
                client_order_id=client_order_id,
            )
            logger.info(f"Placed aggressive limit order: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to place aggressive limit order: {e}")
            return None

    async def place_best_quote_limit_order(
        self,
        symbol: str,
        side: Literal["Buy", "Sell"],
        qty: float,
        category: str = "option",
        client_order_id: Optional[str] = None,
        fallback_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Place a limit order at the current best quote without chasing.

        For buys, this uses the current best ask. For sells, it uses the current
        best bid. If the book is empty, it can fall back to a single reference
        price instead of widening aggressively like a market-style order.
        """
        if not client_order_id:
            client_order_id = self.generate_client_order_id()
        self._require_bot_client_order_id(client_order_id, "place best-quote limit order")

        try:
            ticker = await self.client.get_tickers(symbol=symbol, category=category)
        except Exception as e:
            logger.error(f"Failed to fetch ticker for best-quote order {symbol}: {e}")
            return None

        quote_field = "ask1Price" if side == "Buy" else "bid1Price"
        limit_price = 0.0

        raw_quote = ticker.get(quote_field)
        if raw_quote not in (None, "", "0", 0):
            try:
                limit_price = float(raw_quote)
            except (TypeError, ValueError):
                limit_price = 0.0

        if limit_price <= 0 and fallback_price and fallback_price > 0:
            limit_price = fallback_price
            logger.warning(
                f"No valid {quote_field} for {symbol}; falling back to reference price {limit_price:.8f}"
            )

        if limit_price <= 0:
            logger.error(f"No valid best quote available for {symbol} ({quote_field})")
            return None

        if self.dry_run:
            logger.info(f"[DRY RUN] Place {side} {qty} {symbol} @ {limit_price:.4f} (best-quote limit, {category})")
            return {
                "orderId": f"dry_{uuid.uuid4().hex[:8]}",
                "orderLinkId": client_order_id,
                "dry_run": True,
            }

        try:
            result = await self.client.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=qty,
                price=limit_price,
                category=category,
                client_order_id=client_order_id,
            )
            logger.info(f"Placed best-quote limit order @ {limit_price}: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to place best-quote limit order: {e}")
            return None

    async def confirm_fill(
        self,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        category: str = "linear",
        symbol: Optional[str] = None,
        timeout: int = 30,
        poll_interval: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Confirm order fill by polling order status.

        Args:
            order_id: Order ID
            client_order_id: Client order ID
            category: Product category
            symbol: Trading symbol
            timeout: Max wait time in seconds
            poll_interval: Poll interval in seconds

        Returns:
            Order info if filled, None otherwise
        """
        self._require_bot_client_order_id(client_order_id, "monitor")

        if self.dry_run:
            logger.info(f"[DRY RUN] Confirm fill for order {order_id or client_order_id}")
            await asyncio.sleep(1)  # Simulate delay
            return {
                "orderStatus": "Filled",
                "avgPrice": "2500.00",
                "cumExecQty": "1.0",
                "dry_run": True,
            }

        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < timeout:
            try:
                order_info = await self.client.get_order_status(
                    client_order_id=client_order_id,
                    category=category,
                    symbol=symbol,
                )

                if not order_info:
                    logger.warning(f"Order not found: {order_id or client_order_id}")
                    await asyncio.sleep(poll_interval)
                    continue

                order_status = order_info.get("orderStatus", "")

                if order_status == "Filled":
                    logger.info(f"Order filled: {order_id or client_order_id}")
                    return order_info

                if order_status in ["Cancelled", "Rejected"]:
                    logger.error(f"Order {order_status.lower()}: {order_id or client_order_id}")
                    return None

                # Still pending
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error confirming fill: {e}")
                await asyncio.sleep(poll_interval)

        logger.warning(f"Order fill confirmation timeout: {order_id or client_order_id}")
        return None

    @staticmethod
    def _safe_float(value: Any) -> float:
        """Convert exchange values to float safely."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _normalize_option_contracts(
        self,
        requested_contracts: float,
        option_instrument: OptionInstrument,
    ) -> float:
        """Normalize option quantity to the instrument's allowed increment."""
        requested = Decimal(str(requested_contracts))
        qty_step = Decimal(str(option_instrument.qty_step or 0.1))
        min_qty = Decimal(str(option_instrument.min_order_qty or 0.1))
        effective_min = max(qty_step, min_qty)

        if requested <= 0:
            raise ValueError("Option contracts must be positive")

        if requested < effective_min:
            normalized = effective_min
        else:
            increments = (requested / qty_step).to_integral_value(rounding=ROUND_DOWN)
            normalized = increments * qty_step
            if normalized < effective_min:
                normalized = effective_min

        normalized_float = float(normalized)
        if abs(normalized_float - requested_contracts) > 1e-9:
            logger.warning(
                "Adjusted option contracts for %s from %.8f to %.8f to match Bybit qty step %.8f",
                option_instrument.symbol,
                requested_contracts,
                normalized_float,
                option_instrument.qty_step,
            )
        return normalized_float

    async def open_perp_leg(
        self,
        symbol: str,
        side: Literal["short", "long"],
        qty: float,
    ) -> Optional[Leg]:
        """
        Open perpetual leg.

        Returns:
            Leg object or None
        """
        bybit_side = "Sell" if side == "short" else "Buy"
        client_order_id = self.generate_client_order_id("perp")

        leg = Leg(
            leg_type="perp",
            symbol=symbol,
            side=side,
            qty=qty,
            client_order_id=client_order_id,
        )

        # Place order
        order_result = await self.place_market_order(
            symbol=symbol,
            side=bybit_side,
            qty=qty,
            category="linear",
            client_order_id=client_order_id,
        )

        if not order_result:
            logger.error("Failed to place perp order")
            return None

        leg.order_id = order_result.get("orderId")

        # Confirm fill
        fill_info = await self.confirm_fill(
            client_order_id=client_order_id,
            category="linear",
            symbol=symbol,
        )

        if not fill_info:
            logger.error("Failed to confirm perp fill")
            return leg

        leg.filled = True
        leg.filled_qty = float(fill_info.get("cumExecQty", qty))
        leg.entry_price = float(fill_info.get("avgPrice", 0))

        logger.info(f"Perp leg opened: {symbol} {side} {leg.filled_qty} @ {leg.entry_price}")
        return leg

    async def open_option_leg(
        self,
        option_instrument: OptionInstrument,
        side: Literal["short", "long"],
        contracts: float,
        slippage_bps: int = 50,
    ) -> Optional[Leg]:
        """
        Open option leg.

        Args:
            option_instrument: Selected option instrument
            side: short or long
            contracts: Number of contracts
            slippage_bps: Slippage for aggressive limit

        Returns:
            Leg object or None
        """
        bybit_side = "Sell" if side == "short" else "Buy"
        client_order_id = self.generate_client_order_id("opt")
        normalized_contracts = self._normalize_option_contracts(float(contracts), option_instrument)

        leg = Leg(
            leg_type="option",
            symbol=option_instrument.symbol,
            side=side,
            qty=normalized_contracts,
            client_order_id=client_order_id,
            strike=option_instrument.strike,
            expiry=option_instrument.expiry,
            option_type=option_instrument.option_type,
        )

        # Get mark price as a one-time fallback if the order book has no valid top quote.
        mark_price = await self.client.get_option_mark_price(option_instrument.symbol)
        if not mark_price:
            logger.error("Failed to get option mark price")
            return None

        # Requote slowly: take the current best offer/bid, wait a few seconds,
        # and only cancel/repost if the order is still untouched.
        max_attempts = 4
        attempt_timeout_seconds = 5
        partial_fill_grace_seconds = 15
        retry_pause_seconds = 2
        fill_info = None

        for attempt in range(1, max_attempts + 1):
            attempt_client_order_id = f"{client_order_id}_{attempt}"
            logger.info(
                f"Option entry attempt {attempt}/{max_attempts} for {option_instrument.symbol}"
            )

            order_result = await self.place_best_quote_limit_order(
                symbol=option_instrument.symbol,
                side=bybit_side,
                qty=normalized_contracts,
                category="option",
                client_order_id=attempt_client_order_id,
                fallback_price=mark_price,
            )

            if not order_result:
                logger.warning(
                    f"Option entry attempt {attempt} failed to place for {option_instrument.symbol}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(retry_pause_seconds)
                continue

            leg.order_id = order_result.get("orderId")
            leg.client_order_id = attempt_client_order_id

            fill_info = await self.confirm_fill(
                client_order_id=attempt_client_order_id,
                category="option",
                symbol=option_instrument.symbol,
                timeout=attempt_timeout_seconds,
                poll_interval=1,
            )
            if fill_info:
                break

            if self.dry_run:
                break

            latest_order = await self.client.get_order_status(
                client_order_id=attempt_client_order_id,
                category="option",
                symbol=option_instrument.symbol,
            )
            latest_status = latest_order.get("orderStatus", "")
            executed_qty = self._safe_float(latest_order.get("cumExecQty"))

            if latest_status == "PartiallyFilled" or executed_qty > 0:
                logger.warning(
                    f"Option order {attempt_client_order_id} partially filled "
                    f"({executed_qty}/{normalized_contracts}); waiting longer without repricing"
                )
                fill_info = await self.confirm_fill(
                    client_order_id=attempt_client_order_id,
                    category="option",
                    symbol=option_instrument.symbol,
                    timeout=partial_fill_grace_seconds,
                    poll_interval=2,
                )
                if fill_info:
                    break

                latest_order = await self.client.get_order_status(
                    client_order_id=attempt_client_order_id,
                    category="option",
                    symbol=option_instrument.symbol,
                )
                latest_status = latest_order.get("orderStatus", "")
                executed_qty = self._safe_float(latest_order.get("cumExecQty"))

                if executed_qty > 0:
                    leg.filled = True
                    leg.filled_qty = executed_qty
                    leg.entry_price = self._safe_float(latest_order.get("avgPrice"))
                    logger.warning(
                        f"Using partial option fill for {option_instrument.symbol}: "
                        f"{leg.filled_qty} @ {leg.entry_price}"
                    )
                    return leg

            if latest_status not in ["Cancelled", "Rejected", "Filled"]:
                logger.info(
                    f"Option order {attempt_client_order_id} not filled; cancelling before repricing"
                )
                try:
                    await self.client.cancel_order(
                        symbol=option_instrument.symbol,
                        client_order_id=attempt_client_order_id,
                        category="option",
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to cancel unfilled option order {attempt_client_order_id}: {e}"
                    )

            if attempt < max_attempts:
                await asyncio.sleep(retry_pause_seconds)

        if not fill_info:
            logger.error(
                f"Failed to confirm option fill after {max_attempts} calm reprice attempts"
            )
            return leg

        leg.filled = True
        leg.filled_qty = float(fill_info.get("cumExecQty", normalized_contracts))
        leg.entry_price = float(fill_info.get("avgPrice", 0))

        logger.info(f"Option leg opened: {option_instrument.symbol} {side} {leg.filled_qty} @ {leg.entry_price}")
        return leg

    async def close_leg(
        self,
        leg: Leg,
        category: str = "linear",
    ) -> bool:
        """
        Close a leg (perp or option).

        Args:
            leg: Leg to close
            category: Product category

        Returns:
            True if closed successfully

        Raises:
            Exception: If order placement or confirmation fails
        """
        if leg.closed:
            logger.info(f"Leg {leg.symbol} already closed")
            return True

        # Opposite side to close
        close_side = "Buy" if leg.side == "short" else "Sell"
        client_order_id = self.generate_client_order_id(f"close_{leg.leg_type}")

        logger.info(f"Closing {leg.leg_type} leg: {leg.symbol} {close_side} {leg.filled_qty}")

        # Try market order first
        order_result = await self.place_market_order(
            symbol=leg.symbol,
            side=close_side,
            qty=leg.filled_qty,
            category=category,
            reduce_only=True,
            client_order_id=client_order_id,
        )

        # If market order fails and this is an option, try aggressive limit
        if not order_result and category == "option":
            logger.warning(f"Market order failed for option {leg.symbol}, trying aggressive limit")

            # Get current mark price
            mark_price = await self.client.get_option_mark_price(leg.symbol)
            if mark_price:
                order_result = await self.place_aggressive_limit_order(
                    symbol=leg.symbol,
                    side=close_side,
                    qty=leg.filled_qty,
                    reference_price=mark_price,
                    slippage_bps=100,  # More aggressive for closing
                    category=category,
                    client_order_id=client_order_id,
                )

        if not order_result:
            error_msg = f"Failed to place close order for {leg.symbol}"
            logger.error(error_msg)
            raise Exception(error_msg)

        leg.close_order_id = order_result.get("orderId")
        leg.close_client_order_id = client_order_id

        # Confirm fill
        fill_info = await self.confirm_fill(
            client_order_id=client_order_id,
            category=category,
            symbol=leg.symbol,
            timeout=60 if category == "option" else 30,
        )

        if not fill_info:
            error_msg = f"Failed to confirm close for {leg.symbol}"
            logger.error(error_msg)
            raise Exception(error_msg)

        leg.closed = True

        # Determine exit price
        if fill_info.get("dry_run"):
            # Dry run: use last known mark price as proxy
            exit_price = leg.mark_price
        else:
            # Live: fetch execution records for exact fill price
            exit_price = None
            try:
                exec_records = await self.client.get_execution_records(
                    symbol=leg.symbol,
                    client_order_id=client_order_id,
                    category=category,
                )
                if exec_records:
                    total_qty = sum(float(r["execQty"]) for r in exec_records)
                    if total_qty > 0:
                        exit_price = (
                            sum(float(r["execPrice"]) * float(r["execQty"]) for r in exec_records)
                            / total_qty
                        )
                        logger.info(f"Exact fill price from execution records: {exit_price} ({len(exec_records)} records)")
            except Exception as e:
                logger.warning(f"Failed to fetch execution records for {leg.symbol}, falling back to avgPrice: {e}")

            if not exit_price:
                raw = float(fill_info.get("avgPrice", 0))
                exit_price = raw if raw else None
                if exit_price:
                    logger.info(f"Using avgPrice as exit price fallback: {exit_price}")

        leg.exit_price = exit_price

        # Recompute final realized PnL from actual entry/exit fill prices
        if leg.entry_price and exit_price:
            if leg.side == "short":
                price_pnl = (leg.entry_price - exit_price) * leg.filled_qty
            else:
                price_pnl = (exit_price - leg.entry_price) * leg.filled_qty

            if leg.leg_type == "perp":
                # 0.05% per side (entry + exit)
                fees = (leg.entry_price + exit_price) * leg.filled_qty * 0.0005
            else:
                # 0.02% of strike per side (entry + exit)
                strike = leg.strike or exit_price
                fees = strike * leg.filled_qty * 0.0004

            leg.unrealized_pnl = price_pnl - fees

        logger.info(
            f"✓ Leg closed: {leg.symbol} exit={exit_price} "
            f"realized_pnl={leg.unrealized_pnl:.4f}"
        )
        return True
