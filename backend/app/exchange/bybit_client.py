"""Bybit exchange client with rate limiting and retry logic."""
import hashlib
import hmac
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio

import httpx
from httpx import Response

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""

    def __init__(self, requests_per_second: int = 10):
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1


class BybitClient:
    """
    Unified Bybit client for perpetual futures and USDT-settled options.

    Implements authentication, rate limiting, retries with exponential backoff.
    Supports testnet and mainnet toggle.
    """

    MAINNET_BASE = "https://api.bybit.com"
    TESTNET_BASE = "https://api-testnet.bybit.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        rate_limit: int = 10,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.TESTNET_BASE if testnet else self.MAINNET_BASE
        self.testnet = testnet
        self.max_retries = max_retries
        self.timeout = timeout

        self.rate_limiter = RateLimiter(rate_limit)
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.info(f"BybitClient initialized ({'testnet' if testnet else 'mainnet'})")

    def _generate_signature(self, params: Dict[str, Any], timestamp: str, recv_window: str, method: str = "GET") -> str:
        """Generate HMAC SHA256 signature for authenticated requests."""
        import json

        param_str = f"{timestamp}{self.api_key}{recv_window}"

        if method == "POST":
            # For POST requests, ALWAYS add JSON body (even if empty)
            json_str = json.dumps(params, separators=(',', ':'), sort_keys=False, ensure_ascii=False)
            param_str += json_str
            logger.debug(f"POST signature base: {param_str[:150]}...")
        elif params:  # For GET, only add if params exist
            # For GET requests, add query parameters
            query_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            param_str += query_str
            logger.debug(f"GET signature base: {param_str[:150]}...")

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            param_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _prepare_auth_headers(self, params: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, str]:
        """Prepare headers for authenticated requests."""
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"

        signature = self._generate_signature(params or {}, timestamp, recv_window, method)

        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Make HTTP request with rate limiting and retries."""
        import json as json_module

        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        headers = self._prepare_auth_headers(params, method) if auth else {"Content-Type": "application/json"}

        try:
            if method == "GET":
                response = await self.client.get(url, params=params, headers=headers)
            elif method == "POST":
                # CRITICAL: Use same JSON format as signature (no spaces)
                json_body = json_module.dumps(params or {}, separators=(',', ':'), sort_keys=False, ensure_ascii=False)
                response = await self.client.post(url, content=json_body, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            data = response.json()

            # Bybit returns {"retCode": 0, "retMsg": "OK", "result": {...}}
            if data.get("retCode") != 0:
                error_msg = data.get("retMsg", "Unknown error")
                logger.error(f"Bybit API error: {error_msg} (code: {data.get('retCode')})")
                raise Exception(f"Bybit API error: {error_msg}")

            return data

        except httpx.HTTPStatusError as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"Request failed ({e.response.status_code}), retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self._request(method, endpoint, params, auth, retry_count + 1)
            logger.error(f"Request failed after {self.max_retries} retries: {e}")
            raise

        except Exception as e:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"Request error ({e}), retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                return await self._request(method, endpoint, params, auth, retry_count + 1)
            logger.error(f"Request failed: {e}")
            raise

    # ==================== PUBLIC ENDPOINTS ====================

    async def get_server_time(self) -> int:
        """Get server time."""
        data = await self._request("GET", "/v5/market/time", auth=False)
        return int(data["result"]["timeSecond"])

    async def get_klines(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "5",
        category: str = "linear",
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        """
        Get kline/candlestick data.

        Args:
            symbol: Trading pair
            interval: Kline interval in minutes (1, 5, 15, etc.)
            category: Product type (linear for perpetuals)
            limit: Number of candles (max 200)
            start_time: Start timestamp in ms
            end_time: End timestamp in ms

        Returns:
            List of klines [startTime, open, high, low, close, volume, turnover]
        """
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        data = await self._request("GET", "/v5/market/kline", params, auth=False)
        return data["result"]["list"]

    async def get_tickers(self, symbol: str = "ETHUSDT", category: str = "linear") -> Dict[str, Any]:
        """Get latest ticker data."""
        params = {"category": category, "symbol": symbol}
        data = await self._request("GET", "/v5/market/tickers", params, auth=False)
        return data["result"]["list"][0] if data["result"]["list"] else {}

    # ==================== OPTIONS ENDPOINTS ====================

    async def get_option_instruments(
        self,
        underlying: str = "ETH",
        base_coin: Optional[str] = "ETH",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Get USDT-settled option instruments.

        IMPORTANT: Bybit options use category="option" and settlement in USDT.
        Symbol format: ETH-30APR25-3000-P (underlying-date-strike-C/P)

        Returns:
            List of option instruments with symbol, strike, expiry, etc.
        """
        params = {
            "category": "option",
            "limit": limit,
        }
        if base_coin:
            params["baseCoin"] = base_coin

        data = await self._request("GET", "/v5/market/instruments-info", params, auth=False)
        instruments = data["result"]["list"]

        logger.info(f"Fetched {len(instruments)} option instruments for {underlying}")
        return instruments

    async def get_option_mark_price(self, symbol: str) -> Optional[float]:
        """Get option mark price."""
        try:
            params = {"category": "option", "symbol": symbol}
            data = await self._request("GET", "/v5/market/tickers", params, auth=False)
            if data["result"]["list"]:
                return float(data["result"]["list"][0].get("markPrice", 0))
        except Exception as e:
            logger.error(f"Failed to get option mark price for {symbol}: {e}")
        return None

    # ==================== TRADING ENDPOINTS ====================

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        category: str = "linear",
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Place an order.

        Args:
            symbol: Trading pair
            side: Buy or Sell
            order_type: Market, Limit
            qty: Order quantity
            category: linear (perp) or option
            price: Limit price (required for Limit orders)
            client_order_id: Custom order ID for idempotency
            reduce_only: Close position only

        Returns:
            Order result with orderId, orderLinkId, etc.
        """
        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }

        if price:
            params["price"] = str(price)
        if client_order_id:
            params["orderLinkId"] = client_order_id
        if reduce_only:
            params["reduceOnly"] = True

        data = await self._request("POST", "/v5/order/create", params)
        logger.info(f"Placed {side} {order_type} order for {symbol}: {data['result']}")
        return data["result"]

    async def get_order_status(
        self,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        category: str = "linear",
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get order status by order ID or client order ID."""
        params = {"category": category}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id
        if symbol:
            params["symbol"] = symbol

        data = await self._request("GET", "/v5/order/realtime", params)
        orders = data["result"]["list"]
        return orders[0] if orders else {}

    async def get_open_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get open orders for a category, optionally scoped to a symbol."""
        params: Dict[str, Any] = {
            "category": category,
            "limit": limit,
        }
        if symbol:
            params["symbol"] = symbol

        data = await self._request("GET", "/v5/order/realtime", params)
        return data["result"]["list"]

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        category: str = "linear",
    ) -> Dict[str, Any]:
        """Cancel an order."""
        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id

        data = await self._request("POST", "/v5/order/cancel", params)
        return data["result"]

    async def get_execution_records(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        category: str = "linear",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get execution records for an order from /v5/execution/list.

        Returns actual fill records with execPrice and execQty, which are
        more authoritative than avgPrice from /v5/order/realtime.

        Args:
            symbol: Trading symbol (required by Bybit)
            order_id: Filter by exchange order ID
            client_order_id: Filter by client order ID (orderLinkId)
            category: Product category
            limit: Max number of records

        Returns:
            List of execution records, each with execPrice, execQty, execFee, etc.
        """
        params: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "limit": limit,
        }
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id

        data = await self._request("GET", "/v5/execution/list", params)
        return data["result"]["list"]

    # ==================== POSITION ENDPOINTS ====================

    async def get_positions(
        self,
        symbol: Optional[str] = None,
        category: str = "linear",
        settle_coin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get current positions.

        For unified accounts without symbol, settleCoin is required.
        """
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        elif category == "linear" and not settle_coin:
            # For unified linear positions without symbol, default to USDT
            params["settleCoin"] = "USDT"
        elif settle_coin:
            params["settleCoin"] = settle_coin

        data = await self._request("GET", "/v5/position/list", params)
        return data["result"]["list"]

    async def get_position_info(self, symbol: str, category: str = "linear") -> Optional[Dict[str, Any]]:
        """Get position info for specific symbol."""
        positions = await self.get_positions(symbol=symbol, category=category)
        for pos in positions:
            if pos.get("symbol") == symbol:
                return pos
        return None

    # ==================== ACCOUNT ENDPOINTS ====================

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        """Get wallet balance."""
        params = {"accountType": account_type}
        data = await self._request("GET", "/v5/account/wallet-balance", params)
        return data["result"]

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
