# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""
Python wrapper for T-Invest gRPC client.

This module provides a Python interface to the Rust TInvestGrpcClient
via PyO3 bindings (nautilus_pyo3.tinvest.TInvestGrpcClient) when available,
falling back to a local stub for development/testing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from typing import Callable

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig


logger = logging.getLogger(__name__)


class TInvestGrpcClient:
    """
    Wrapper around the Rust TInvestGrpcClient (PyO3).

    Provides connect/disconnect, data query, order execution, and streaming
    subscription methods. Streaming is implemented via REST polling when the
    native gRPC streaming is not available through PyO3 bindings.

    When the Rust extension is not available, acts as a stub
    with logging for development purposes.
    """

    def __init__(self, config: TInvestClientConfig) -> None:
        self._config = config
        self._native = self._create_native_client(config)

        # Polling-based subscription state
        self._polling_tasks: dict[str, asyncio.Task] = {}
        self._subscription_callbacks: dict[str, Callable] = {}

        # Native streaming availability
        self._native_streaming = self._detect_native_streaming()

    def _detect_native_streaming(self) -> bool:
        """
        Detect whether native gRPC streaming is available via PyO3.

        Returns
        -------
        bool
            True if native streaming methods are exposed on the Rust client.

        """
        if self._native is not None:
            try:
                return bool(self._native.has_native_streaming)
            except AttributeError:
                logger.debug(
                    "Native streaming not available: PyTInvestGrpcClient "
                    "does not expose has_native_streaming property. "
                    "Falling back to polling-based subscriptions.",
                )
                return False
        return False

    def _has_native_streaming(self) -> bool:
        """
        Check if native gRPC streaming is available via PyO3.

        Returns
        -------
        bool
            True if native streaming is available and can be used instead
            of polling-based subscriptions.

        """
        return self._native_streaming

    @staticmethod
    def _create_native_client(config: TInvestClientConfig) -> Any:
        """Try to create the native Rust client via PyO3."""
        try:
            from nautilus_trader.core import nautilus_pyo3

            return nautilus_pyo3.tinvest.TInvestGrpcClient(config.to_pyo3())  # type: ignore
        except (AttributeError, ImportError) as e:
            logger.debug(
                "T-Invest native gRPC client not available (PyO3 module missing): %s. "
                "Using stub. Rebuild with: make build-debug",
                e,
            )
            return None

    def is_connected(self) -> bool:
        if self._native is not None:
            return self._native.is_connected
        return False

    async def connect(self) -> None:
        if self._native is not None:
            await self._native.connect()
            logger.info(
                "Connected to T-Invest API (sandbox=%s)",
                self._config.sandbox,
            )
        else:
            logger.warning(
                "T-Invest gRPC client not available. "
                "Token=%s..., sandbox=%s",
                self._config.token[:10],
                self._config.sandbox,
            )

    async def disconnect(self) -> None:
        # Cancel all polling tasks
        for key, task in list(self._polling_tasks.items()):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._polling_tasks.clear()
        self._subscription_callbacks.clear()

        if self._native is not None:
            await self._native.disconnect()
        logger.info("Disconnected from T-Invest API")

    # -- Data Methods -------------------------------------------------------------------------

    async def request_instruments(self) -> list[dict]:
        """
        Load all instruments from T-Invest API.

        Returns
        -------
        list[dict]
            List of instrument dicts with fields: figi, ticker, name,
            instrument_type, currency, lot, etc.

        """
        if self._native is not None:
            return await self._native.request_instruments()
        logger.warning("request_instruments: native client not available")
        return []

    async def request_instrument(self, figi: str) -> dict | None:
        """
        Load a single instrument by FIGI.

        Parameters
        ----------
        figi : str
            The instrument FIGI.

        Returns
        -------
        dict | None
            Instrument dict or None if not found.

        """
        if self._native is not None:
            try:
                return await self._native.request_instrument(figi)
            except Exception as e:
                logger.warning(f"Instrument not found: {figi}: {e}")
                return None
        logger.warning("request_instrument: native client not available")
        return None

    async def request_candles(
        self,
        figi: str,
        interval: int,
        from_ts: int | None = None,
        to_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Request historical candles.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        interval : int
            Candle interval (1=1min, 2=5min, 3=15min, 4=1hour, 5=1day, etc.).
        from_ts : int, optional
            Start time as unix nanos.
        to_ts : int, optional
            End time as unix nanos.
        limit : int, optional
            Max number of candles.

        Returns
        -------
        list[dict]
            List of candle dicts with open, high, low, close, volume, time.

        """
        if self._native is not None:
            return await self._native.request_candles(
                figi,
                interval,
                from_ts,
                to_ts,
                limit,
            )
        logger.warning("request_candles: native client not available")
        return []

    async def request_order_book(self, figi: str, depth: int = 10) -> dict | None:
        """
        Request order book.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        depth : int
            Order book depth.

        Returns
        -------
        dict | None
            Order book dict with bids and asks lists.

        """
        if self._native is not None:
            return await self._native.request_order_book(figi, depth)
        logger.warning("request_order_book: native client not available")
        return None

    async def request_trades(
        self,
        figi: str,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[dict]:
        """
        Request last trades.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        from_ts : int, optional
            Start time as unix nanos.
        to_ts : int, optional
            End time as unix nanos.

        Returns
        -------
        list[dict]
            List of trade dicts with price, quantity, direction, time.

        """
        if self._native is not None:
            return await self._native.request_trades(figi, from_ts, to_ts)
        logger.warning("request_trades: native client not available")
        return []

    async def get_tech_analysis(
        self,
        indicator_type: int,
        instrument_uid: str,
        from_ts: int,
        to_ts: int,
        interval: int,
        type_of_price: int = 1,
        length: int = 0,
    ) -> list[dict]:
        """
        Get technical analysis indicators for an instrument (F5).

        This is a heavy gRPC call — the Rust client executes it with retry
        and exponential backoff. Requires an ``instrument_uid`` (FIGI/ticker
        are not sufficient for this endpoint).

        Parameters
        ----------
        indicator_type : int
            Indicator type (1=BB, 2=EMA, 3=RSI, 4=MACD, 5=SMA).
        instrument_uid : str
            The instrument UID.
        from_ts : int
            Start time as unix nanos.
        to_ts : int
            End time as unix nanos.
        interval : int
            Indicator interval (1=1min, 2=5min, ..., 13=month).
        type_of_price : int, default 1
            Price type used for the calculation (1=Close, 2=Open, ...).
        length : int, default 0
            Trading period for the indicator.

        Returns
        -------
        list[dict]
            List of technical indicator items with timestamp and
            middle_band/upper_band/lower_band/signal/macd keys.

        """
        if self._native is not None:
            return await self._native.get_tech_analysis(
                indicator_type=indicator_type,
                instrument_uid=instrument_uid,
                from_ts=from_ts,
                to_ts=to_ts,
                interval=interval,
                type_of_price=type_of_price,
                length=length,
            )
        logger.warning("get_tech_analysis: native client not available")
        return []

    # -- Streaming Subscriptions (polling-based) ---------------------------------------------

    def _start_polling(
        self,
        key: str,
        poll_fn: Callable[[], Any],
        interval_ms: int,
        callback: Callable,
    ) -> None:
        """
        Start a polling loop for a subscription.

        Parameters
        ----------
        key : str
            Unique key for this subscription (e.g. "order_book:FIGI:10").
        poll_fn : Callable
            Async function that returns the data.
        interval_ms : int
            Polling interval in milliseconds.
        callback : Callable
            Callback to invoke with the polled data.

        """
        if key in self._polling_tasks:
            logger.debug(f"Polling already active for {key}")
            return

        self._subscription_callbacks[key] = callback

        async def _poll_loop() -> None:
            logger.info(f"Polling started for {key} (interval={interval_ms}ms)")
            while True:
                try:
                    data = await poll_fn()
                    if data is not None:
                        cb = self._subscription_callbacks.get(key)
                        if cb is not None:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(data)
                            else:
                                cb(data)
                except asyncio.CancelledError:
                    logger.debug(f"Polling cancelled for {key}")
                    return
                except Exception as e:
                    logger.warning(f"Polling error for {key}: {e}")
                await asyncio.sleep(interval_ms / 1000.0)

        self._polling_tasks[key] = asyncio.ensure_future(_poll_loop())

    def _stop_polling(self, key: str) -> None:
        """
        Stop a polling loop for a subscription.

        Parameters
        ----------
        key : str
            Unique key for the subscription.

        """
        task = self._polling_tasks.pop(key, None)
        if task is not None:
            task.cancel()
            logger.info(f"Polling stopped for {key}")
        self._subscription_callbacks.pop(key, None)

    async def subscribe_order_book(
        self,
        figi: str,
        depth: int = 10,
        callback: Callable | None = None,
    ) -> None:
        """
        Subscribe to order book updates.

        Uses native gRPC streaming when available (PyO3 with
        has_native_streaming=True), falling back to REST polling.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        depth : int
            Order book depth.
        callback : Callable, optional
            Callback receiving the order book dict.

        """
        key = f"order_book:{figi}:{depth}"

        if callback is None:
            logger.warning(f"subscribe_order_book: no callback provided for {figi}")
            return

        if self._native is not None:
            if self._has_native_streaming():
                # TODO: Use native gRPC bidirectional streaming when
                # PyO3 bindings expose TInvestMarketDataStream.
                # The Rust stream supports subscribe_order_book(instrument_id, depth).
                # For now, fall through to polling.
                logger.debug(
                    "Native streaming available but order_book subscription "
                    "not yet wired through PyO3. Using polling fallback for %s.",
                    figi,
                )

            # Use polling via REST request_order_book (500ms interval)
            self._start_polling(
                key=key,
                poll_fn=lambda: self.request_order_book(figi, depth),
                interval_ms=500,
                callback=callback,
            )
        else:
            logger.warning(f"subscribe_order_book: native client not available for {figi}")

    async def unsubscribe_order_book(self, figi: str, depth: int = 10) -> None:
        """
        Unsubscribe from order book updates.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        depth : int
            Order book depth.

        """
        key = f"order_book:{figi}:{depth}"
        self._stop_polling(key)

    async def subscribe_trades(
        self,
        figi: str,
        callback: Callable | None = None,
    ) -> None:
        """
        Subscribe to trade stream.

        Uses native gRPC streaming when available, falling back to REST polling.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        callback : Callable, optional
            Callback receiving the list of trade dicts.

        """
        key = f"trades:{figi}"

        if callback is None:
            logger.warning(f"subscribe_trades: no callback provided for {figi}")
            return

        if self._native is not None:
            if self._has_native_streaming():
                # TODO: Use native gRPC bidirectional streaming when
                # PyO3 bindings expose TInvestMarketDataStream.
                # The Rust stream supports subscribe_trades(instrument_id).
                # For now, fall through to polling.
                logger.debug(
                    "Native streaming available but trades subscription "
                    "not yet wired through PyO3. Using polling fallback for %s.",
                    figi,
                )

            # Use polling via REST request_trades (1s interval)
            self._start_polling(
                key=key,
                poll_fn=lambda: self.request_trades(figi),
                interval_ms=1000,
                callback=callback,
            )
        else:
            logger.warning(f"subscribe_trades: native client not available for {figi}")

    async def unsubscribe_trades(self, figi: str) -> None:
        """
        Unsubscribe from trade stream.

        Parameters
        ----------
        figi : str
            Instrument FIGI.

        """
        key = f"trades:{figi}"
        self._stop_polling(key)

    async def subscribe_candles(
        self,
        figi: str,
        interval: int = 1,
        callback: Callable | None = None,
    ) -> None:
        """
        Subscribe to candle stream.

        Uses native gRPC streaming when available, falling back to REST polling.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        interval : int
            Candle interval (1=1min, 5=1day, etc.).
        callback : Callable, optional
            Callback receiving the list of candle dicts.

        """
        key = f"candles:{figi}:{interval}"

        if callback is None:
            logger.warning(f"subscribe_candles: no callback provided for {figi}")
            return

        if self._native is not None:
            if self._has_native_streaming():
                # TODO: Use native gRPC server-side streaming when
                # PyO3 bindings expose TInvestMarketDataServerSideStream.
                # T-Invest does not have a dedicated candle stream, but
                # MarketDataServerSideStreamRequest with subscribe_candles
                # payload can provide candle updates.
                # For now, fall through to polling.
                logger.debug(
                    "Native streaming available but candles subscription "
                    "not yet wired through PyO3. Using polling fallback for %s.",
                    figi,
                )

            _last_time: int = 0

            async def _poll_candles() -> list[dict]:
                nonlocal _last_time
                import time

                now_ns = int(time.time() * 1_000_000_000)
                # Use last known time as from_ts to get only new candles
                from_ns = _last_time if _last_time > 0 else now_ns - 86_400_000_000_000
                candles = await self.request_candles(
                    figi=figi,
                    interval=interval,
                    from_ts=from_ns,
                    to_ts=now_ns,
                    limit=10,
                )
                if candles:
                    # Update last time from the most recent candle
                    last_candle = candles[-1]
                    candle_time = last_candle.get("time", 0)
                    if candle_time > _last_time:
                        _last_time = candle_time
                return candles

            # Poll every 60s for 1-min candles, every 5min for daily
            poll_ms = 60000 if interval == 1 else 300000

            self._start_polling(
                key=key,
                poll_fn=_poll_candles,
                interval_ms=poll_ms,
                callback=callback,
            )
        else:
            logger.warning(f"subscribe_candles: native client not available for {figi}")

    async def unsubscribe_candles(self, figi: str, interval: int = 1) -> None:
        """
        Unsubscribe from candle stream.

        Parameters
        ----------
        figi : str
            Instrument FIGI.
        interval : int
            Candle interval.

        """
        key = f"candles:{figi}:{interval}"
        self._stop_polling(key)

    # -- Execution Methods --------------------------------------------------------------------

    async def post_order(
        self,
        account_id: str,
        figi: str,
        quantity: int,
        price: float | None = None,
        direction: int = 1,
        order_type: int = 2,
        order_id: str | None = None,
    ) -> dict | None:
        """
        Submit an order.

        Parameters
        ----------
        account_id : str
            The account ID.
        figi : str
            Instrument FIGI.
        quantity : int
            Order quantity in lots.
        price : float, optional
            Order price (for limit orders).
        direction : int
            Order direction (1=Buy, 2=Sell).
        order_type : int
            Order type (1=Limit, 2=Market).
        order_id : str, optional
            Client order ID for idempotency.

        Returns
        -------
        dict | None
            Order response dict with order_id, execution_report_status, etc.

        """
        if self._native is not None:
            return await self._native.post_order(
                account_id=account_id,
                figi=figi,
                quantity=quantity,
                price=price,
                direction=direction,
                order_type=order_type,
                order_id=order_id or "",
            )
        logger.warning("post_order: native client not available")
        return None

    async def post_order_async(
        self,
        account_id: str,
        figi: str,
        quantity: int,
        price: float | None = None,
        direction: int = 1,
        order_type: int = 2,
        order_id: str | None = None,
    ) -> dict | None:
        """
        Submit an order asynchronously without waiting for the exchange response.

        The T-Invest ``PostOrderAsync`` method returns an idempotency
        ``order_request_id`` immediately. The final order state is delivered
        via the order state stream or polled with :meth:`get_order_state`.

        Parameters
        ----------
        account_id : str
            The account ID.
        figi : str
            Instrument FIGI.
        quantity : int
            Order quantity in lots.
        price : float, optional
            Order price (for limit orders).
        direction : int
            Order direction (1=Buy, 2=Sell).
        order_type : int
            Order type (1=Limit, 2=Market, 3=BestPrice).
        order_id : str, optional
            Client order ID for idempotency.

        Returns
        -------
        dict | None
            Async order response dict with order_request_id,
            execution_report_status and trade_intent_id keys.

        """
        if self._native is not None:
            return await self._native.post_order_async(
                account_id=account_id,
                figi=figi,
                quantity=quantity,
                price=price,
                direction=direction,
                order_type=order_type,
                order_id=order_id or "",
            )
        logger.warning("post_order_async: native client not available")
        return None

    async def cancel_order(self, account_id: str, order_id: str) -> dict | None:
        """
        Cancel an order.

        Parameters
        ----------
        account_id : str
            The account ID.
        order_id : str
            The order ID to cancel.

        Returns
        -------
        dict | None
            Response dict with success field.

        """
        if self._native is not None:
            return await self._native.cancel_order(account_id, order_id)
        logger.warning("cancel_order: native client not available")
        return None

    async def replace_order(
        self,
        account_id: str,
        order_id: str,
        idempotency_key: str,
        quantity: int,
        price: float | None = None,
    ) -> dict | None:
        """
        Replace (modify) an existing order.

        Parameters
        ----------
        account_id : str
            The account ID.
        order_id : str
            The exchange order ID to replace.
        idempotency_key : str
            New idempotency key for the replacement order.
        quantity : int
            New quantity in lots.
        price : float, optional
            New price (for limit orders).

        Returns
        -------
        dict | None
            Order response dict with order_id, execution_report_status, etc.

        """
        if self._native is not None:
            return await self._native.replace_order(
                account_id=account_id,
                order_id=order_id,
                idempotency_key=idempotency_key,
                quantity=quantity,
                price=price,
            )
        logger.warning("replace_order: native client not available")
        return None

    async def get_order_state(self, account_id: str, order_id: str) -> dict | None:
        """
        Get order state.

        Parameters
        ----------
        account_id : str
            The account ID.
        order_id : str
            The order ID.

        Returns
        -------
        dict | None
            Order state dict.

        """
        if self._native is not None:
            return await self._native.get_order_state(account_id, order_id)
        logger.warning("get_order_state: native client not available")
        return None

    async def get_orders(self, account_id: str) -> list[dict]:
        """
        Get all active orders.

        Parameters
        ----------
        account_id : str
            The account ID.

        Returns
        -------
        list[dict]
            List of order state dicts.

        """
        if self._native is not None:
            return await self._native.get_orders(account_id)
        logger.warning("get_orders: native client not available")
        return []

    async def get_portfolio(self, account_id: str) -> dict | None:
        """
        Get portfolio.

        Parameters
        ----------
        account_id : str
            The account ID.

        Returns
        -------
        dict | None
            Portfolio dict with positions, totals, etc.

        """
        if self._native is not None:
            return await self._native.get_portfolio(account_id)
        logger.warning("get_portfolio: native client not available")
        return None

    async def get_positions(self, account_id: str) -> dict | None:
        """
        Get positions.

        Parameters
        ----------
        account_id : str
            The account ID.

        Returns
        -------
        dict | None
            Positions dict with securities, futures, currencies.

        """
        if self._native is not None:
            return await self._native.get_positions(account_id)
        logger.warning("get_positions: native client not available")
        return None

    async def get_operations(
        self,
        account_id: str,
        figi: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> dict | None:
        """
        Get operations for the account.

        Parameters
        ----------
        account_id : str
            The account ID.
        figi : str, optional
            Filter by instrument FIGI.
        from_ts : int, optional
            Start time as unix nanos.
        to_ts : int, optional
            End time as unix nanos.

        Returns
        -------
        dict | None
            Operations response dict with items list.

        """
        if self._native is not None:
            return await self._native.get_operations(
                account_id=account_id,
                figi=figi,
                from_ts=from_ts,
                to_ts=to_ts,
            )
        logger.warning("get_operations: native client not available")
        return None

    async def get_operations_by_cursor(
        self,
        account_id: str,
        instrument_id: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
        operation_types: list[int] | None = None,
        state: int | None = None,
        without_commissions: bool = False,
        without_trades: bool = False,
        without_overnights: bool = False,
    ) -> dict | None:
        """
        Get operations for the account with explicit pagination (F6).

        Parameters
        ----------
        account_id : str
            The account ID.
        instrument_id : str, optional
            Instrument identifier (figi/uid/ticker_class).
        from_ts : int, optional
            Start time as unix nanos.
        to_ts : int, optional
            End time as unix nanos.
        cursor : str, optional
            Opaque cursor from the previous page.
        limit : int, default 100
            Max number of operations per page (1..1000).
        operation_types : list[int], optional
            Filter by operation type enum values.
        state : int, optional
            Operation state filter (1=Executed, 2=Canceled, 3=Progress).
        without_commissions : bool, default False
            Exclude commissions from the response.
        without_trades : bool, default False
            Exclude trade details from the response.
        without_overnights : bool, default False
            Exclude overnight operations.

        Returns
        -------
        dict | None
            Response dict with has_next, next_cursor and items list.

        """
        if self._native is not None:
            return await self._native.get_operations_by_cursor(
                account_id=account_id,
                instrument_id=instrument_id,
                from_ts=from_ts,
                to_ts=to_ts,
                cursor=cursor,
                limit=limit,
                operation_types=operation_types,
                state=state,
                without_commissions=without_commissions,
                without_trades=without_trades,
                without_overnights=without_overnights,
            )
        logger.warning("get_operations_by_cursor: native client not available")
        return None

    async def get_withdraw_limits(self, account_id: str) -> dict | None:
        """
        Get the available withdraw limits for an account (F7).

        Parameters
        ----------
        account_id : str
            The account ID.

        Returns
        -------
        dict | None
            Response dict with money, blocked and blocked_guarantee lists.

        """
        if self._native is not None:
            return await self._native.get_withdraw_limits(account_id=account_id)
        logger.warning("get_withdraw_limits: native client not available")
        return None

    async def get_user_tariff(self) -> dict | None:
        """
        Get the current user tariff / request limits (F8).

        Returns
        -------
        dict | None
            Response dict with unary_limits and stream_limits lists.

        """
        if self._native is not None:
            return await self._native.get_user_tariff()
        logger.warning("get_user_tariff: native client not available")
        return None

    async def get_order_price(
        self,
        account_id: str,
        instrument_id: str,
        price: float,
        direction: int,
        quantity: int,
    ) -> dict | None:
        """
        Estimate the cost/price of an order (F9).

        Parameters
        ----------
        account_id : str
            The account ID.
        instrument_id : str
            Instrument identifier (figi/uid/ticker_class).
        price : float
            The order price per instrument.
        direction : int
            Order direction (1=Buy, 2=Sell).
        quantity : int
            Order quantity in lots.

        Returns
        -------
        dict | None
            Response dict with total_order_amount, initial_order_amount,
            lots_requested and commission fields.

        """
        if self._native is not None:
            return await self._native.get_order_price(
                account_id=account_id,
                instrument_id=instrument_id,
                price=price,
                direction=direction,
                quantity=quantity,
            )
        logger.warning("get_order_price: native client not available")
        return None

    async def get_instrument_by(
        self,
        id_type: int,
        id: str,
        class_code: str | None = None,
    ) -> dict | None:
        """
        Find an instrument by figi/ticker/uid (F10).

        Parameters
        ----------
        id_type : int
            InstrumentIdType (1=FIGI, 2=Ticker, 3=UID, 4=PositionUid, 5=Id).
        id : str
            The identifier value to search for.
        class_code : str, optional
            The class code; required when ``id_type`` is ticker.

        Returns
        -------
        dict | None
            Instrument dict or None if not found.

        """
        if self._native is not None:
            try:
                return await self._native.get_instrument_by(
                    id_type=id_type,
                    id=id,
                    class_code=class_code,
                )
            except Exception as e:
                logger.warning(f"Instrument not found by {id_type}:{id}: {e}")
                return None
        logger.warning("get_instrument_by: native client not available")
        return None

    async def get_trading_schedules(
        self,
        exchange: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[dict]:
        """
        Get the trading schedules for an exchange (F11).

        Parameters
        ----------
        exchange : str, optional
            Exchange name; if omitted, all exchanges are returned.
        from_ts : int, optional
            Start time as unix nanos.
        to_ts : int, optional
            End time as unix nanos.

        Returns
        -------
        list[dict]
            List of exchange schedules with days list.

        """
        if self._native is not None:
            return await self._native.get_trading_schedules(
                exchange=exchange,
                from_ts=from_ts,
                to_ts=to_ts,
            )
        logger.warning("get_trading_schedules: native client not available")
        return []

    async def get_trading_statuses(self, instrument_ids: list[str]) -> list[dict]:
        """
        Get trading statuses for multiple instruments (F11).

        Parameters
        ----------
        instrument_ids : list[str]
            Instrument identifiers (figi/uid/ticker_class).

        Returns
        -------
        list[dict]
            List of trading status dicts.

        """
        if self._native is not None:
            return await self._native.get_trading_statuses(instrument_ids=instrument_ids)
        logger.warning("get_trading_statuses: native client not available")
        return []

    async def get_accrued_interests(
        self,
        instrument_id: str,
        from_ts: int,
        to_ts: int,
    ) -> list[dict]:
        """
        Get the accrued interest (coupon income) for a bond (F12).

        Parameters
        ----------
        instrument_id : str
            Instrument identifier (figi/uid/ticker_class).
        from_ts : int
            Start time as unix nanos.
        to_ts : int
            End time as unix nanos.

        Returns
        -------
        list[dict]
            List of accrued interest dicts with date, value, value_percent, nominal.

        """
        if self._native is not None:
            return await self._native.get_accrued_interests(
                instrument_id=instrument_id,
                from_ts=from_ts,
                to_ts=to_ts,
            )
        logger.warning("get_accrued_interests: native client not available")
        return []

    async def get_signals(self, strategy_id: str | None = None) -> list[dict]:
        """
        Get available signal strategies (F15, NOT_APPLICABLE).

        The SignalsService exposes analytical signals which have no Nautilus
        event-model equivalent (ADR-5). This is a contract-completeness stub
        only — no engine integration is performed.

        Parameters
        ----------
        strategy_id : str, optional
            Filter by strategy identifier.

        Returns
        -------
        list[dict]
            List of signal strategy dicts.

        """
        if self._native is not None:
            return await self._native.get_signals(strategy_id=strategy_id)
        logger.warning("get_signals: native client not available")
        return []

    async def get_accounts(self) -> list[dict]:
        """
        Get user accounts.

        Returns
        -------
        list[dict]
            List of account dicts with id, type, name, status.

        """
        if self._native is not None:
            return await self._native.get_accounts()
        logger.warning("get_accounts: native client not available")
        return []

    # -- Stop-Order Methods -------------------------------------------------------------------

    async def post_stop_order(
        self,
        account_id: str,
        figi: str,
        quantity: int,
        order_id: str,
        price: float | None = None,
        stop_price: float | None = None,
        direction: int = 1,
        expiration_type: int = 1,
        stop_order_type: int = 1,
        exchange_order_type: int = 0,
        take_profit_type: int = 0,
    ) -> dict | None:
        """
        Submit a stop-order.

        Parameters
        ----------
        account_id : str
            The account ID.
        figi : str
            Instrument FIGI.
        quantity : int
            Order quantity in lots.
        order_id : str
            Client order ID for idempotency (UUID).
        price : float, optional
            Order price (for stop-limit orders).
        stop_price : float, optional
            Stop trigger price.
        direction : int
            Order direction (1=Buy, 2=Sell).
        expiration_type : int
            Stop order expiration (1=GoodTillCancel, 2=GoodTillDate).
        stop_order_type : int
            Stop order type (1=TakeProfit, 2=StopLoss, 3=StopLimit).
        exchange_order_type : int, default 0
            The child exchange order type (0=Unspecified, 1=Market, 2=Limit).
        take_profit_type : int, default 0
            TakeProfit subtype (0=Unspecified, 1=Regular, 2=Trailing).

        Returns
        -------
        dict | None
            Stop-order response dict with stop_order_id, etc.

        """
        if self._native is not None:
            return await self._native.post_stop_order(
                account_id=account_id,
                figi=figi,
                quantity=quantity,
                order_id=order_id,
                price=price,
                stop_price=stop_price,
                direction=direction,
                expiration_type=expiration_type,
                stop_order_type=stop_order_type,
                exchange_order_type=exchange_order_type,
                take_profit_type=take_profit_type,
            )
        logger.warning("post_stop_order: native client not available")
        return None

    async def replace_stop_order(
        self,
        account_id: str,
        stop_order_id: str,
        figi: str,
        quantity: int,
        order_id: str,
        price: float | None = None,
        stop_price: float | None = None,
        direction: int = 1,
        expiration_type: int = 1,
        stop_order_type: int = 1,
        exchange_order_type: int = 0,
        take_profit_type: int = 0,
    ) -> dict | None:
        """
        Replace a stop-order (F4).

        The T-Invest StopOrdersService has no ``ReplaceStopOrder`` RPC, so a
        replacement is implemented as *cancel the old stop-order* followed by
        *submit a new stop-order* with the updated parameters.

        Parameters
        ----------
        account_id : str
            The account ID.
        stop_order_id : str
            The stop-order ID to replace.
        figi : str
            Instrument FIGI.
        quantity : int
            Order quantity in lots.
        order_id : str
            New client order ID for idempotency (UUID).
        price : float, optional
            Order price (for stop-limit orders).
        stop_price : float, optional
            Stop trigger price.
        direction : int
            Order direction (1=Buy, 2=Sell).
        expiration_type : int
            Stop order expiration (1=GoodTillCancel, 2=GoodTillDate).
        stop_order_type : int
            Stop order type (1=TakeProfit, 2=StopLoss, 3=StopLimit).
        exchange_order_type : int, default 0
            The child exchange order type (0=Unspecified, 1=Market, 2=Limit).
        take_profit_type : int, default 0
            TakeProfit subtype (0=Unspecified, 1=Regular, 2=Trailing).

        Returns
        -------
        dict | None
            Response dict with old_stop_order_id, stop_order_id, etc.

        """
        if self._native is not None:
            return await self._native.replace_stop_order(
                account_id=account_id,
                stop_order_id=stop_order_id,
                figi=figi,
                quantity=quantity,
                order_id=order_id,
                price=price,
                stop_price=stop_price,
                direction=direction,
                expiration_type=expiration_type,
                stop_order_type=stop_order_type,
                exchange_order_type=exchange_order_type,
                take_profit_type=take_profit_type,
            )
        logger.warning("replace_stop_order: native client not available")
        return None

    async def cancel_stop_order(
        self,
        account_id: str,
        stop_order_id: str,
    ) -> dict | None:
        """
        Cancel a stop-order.

        Parameters
        ----------
        account_id : str
            The account ID.
        stop_order_id : str
            The stop-order ID to cancel.

        Returns
        -------
        dict | None
            Response dict with time field.

        """
        if self._native is not None:
            return await self._native.cancel_stop_order(
                account_id=account_id,
                stop_order_id=stop_order_id,
            )
        logger.warning("cancel_stop_order: native client not available")
        return None

    async def get_stop_orders(
        self,
        account_id: str,
    ) -> list[dict]:
        """
        Get all active stop-orders for an account.

        Parameters
        ----------
        account_id : str
            The account ID.

        Returns
        -------
        list[dict]
            List of stop-order dicts.

        """
        if self._native is not None:
            return await self._native.get_stop_orders(account_id=account_id)
        logger.warning("get_stop_orders: native client not available")
        return []

    # -- Sandbox Methods ----------------------------------------------------------------------

    async def open_sandbox_account(self, name: str | None = None) -> dict | None:
        """
        Open a sandbox account.

        Parameters
        ----------
        name : str, optional
            Display name for the sandbox account.

        Returns
        -------
        dict | None
            Account dict with account_id.

        """
        if self._native is not None:
            return await self._native.open_sandbox_account(name=name)
        logger.warning("open_sandbox_account: native client not available")
        return None

    async def close_sandbox_account(self, account_id: str) -> dict | None:
        """
        Close a sandbox account.

        Parameters
        ----------
        account_id : str
            The account ID to close.

        Returns
        -------
        dict | None
            Response dict with success field.

        """
        if self._native is not None:
            return await self._native.close_sandbox_account(account_id)
        logger.warning("close_sandbox_account: native client not available")
        return None

    async def sandbox_pay_in(
        self,
        account_id: str,
        amount: dict,
    ) -> dict | None:
        """
        Deposit money into sandbox account.

        Parameters
        ----------
        account_id : str
            The account ID.
        amount : dict
            Amount dict with currency, units, nano keys.
            Example: {'currency': 'RUB', 'units': 100000, 'nano': 0}.

        Returns
        -------
        dict | None
            Response dict with success field.

        """
        if self._native is not None:
            return await self._native.sandbox_pay_in(
                account_id=account_id,
                amount=amount,
            )
        logger.warning("sandbox_pay_in: native client not available")
        return None

    # -- F14: Full sandbox method surface ------------------------------------------------------

    async def get_sandbox_accounts(self) -> list[dict]:
        """Get sandbox accounts (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_accounts()
        logger.warning("get_sandbox_accounts: native client not available")
        return []

    async def post_sandbox_order_async(
        self,
        account_id: str,
        figi: str,
        quantity: int,
        price: float | None = None,
        direction: int = 1,
        order_type: int = 2,
        order_id: str | None = None,
    ) -> dict | None:
        """Submit an order asynchronously in the sandbox (F14)."""
        if self._native is not None:
            return await self._native.post_sandbox_order_async(
                account_id=account_id,
                figi=figi,
                quantity=quantity,
                price=price,
                direction=direction,
                order_type=order_type,
                order_id=order_id or "",
            )
        logger.warning("post_sandbox_order_async: native client not available")
        return None

    async def replace_sandbox_order(
        self,
        account_id: str,
        order_id: str,
        idempotency_key: str,
        quantity: int,
        price: float | None = None,
    ) -> dict | None:
        """Replace (modify) an order in the sandbox (F14)."""
        if self._native is not None:
            return await self._native.replace_sandbox_order(
                account_id=account_id,
                order_id=order_id,
                idempotency_key=idempotency_key,
                quantity=quantity,
                price=price,
            )
        logger.warning("replace_sandbox_order: native client not available")
        return None

    async def cancel_sandbox_order(self, account_id: str, order_id: str) -> dict | None:
        """Cancel an order in the sandbox (F14)."""
        if self._native is not None:
            return await self._native.cancel_sandbox_order(account_id, order_id)
        logger.warning("cancel_sandbox_order: native client not available")
        return None

    async def get_sandbox_orders(self, account_id: str) -> list[dict]:
        """Get active orders for a sandbox account (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_orders(account_id)
        logger.warning("get_sandbox_orders: native client not available")
        return []

    async def get_sandbox_order_state(self, account_id: str, order_id: str) -> dict | None:
        """Get order state for a sandbox account (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_order_state(account_id, order_id)
        logger.warning("get_sandbox_order_state: native client not available")
        return None

    async def get_sandbox_order_price(
        self,
        account_id: str,
        instrument_id: str,
        price: float,
        direction: int,
        quantity: int,
    ) -> dict | None:
        """Estimate the cost of a sandbox order (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_order_price(
                account_id=account_id,
                instrument_id=instrument_id,
                price=price,
                direction=direction,
                quantity=quantity,
            )
        logger.warning("get_sandbox_order_price: native client not available")
        return None

    async def get_sandbox_operations_by_cursor(
        self,
        account_id: str,
        instrument_id: str | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
        operation_types: list[int] | None = None,
        state: int | None = None,
        without_commissions: bool = False,
        without_trades: bool = False,
        without_overnights: bool = False,
    ) -> dict | None:
        """Get sandbox operations with pagination (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_operations_by_cursor(
                account_id=account_id,
                instrument_id=instrument_id,
                from_ts=from_ts,
                to_ts=to_ts,
                cursor=cursor,
                limit=limit,
                operation_types=operation_types,
                state=state,
                without_commissions=without_commissions,
                without_trades=without_trades,
                without_overnights=without_overnights,
            )
        logger.warning("get_sandbox_operations_by_cursor: native client not available")
        return None

    async def get_sandbox_withdraw_limits(self, account_id: str) -> dict | None:
        """Get the available withdraw limits for a sandbox account (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_withdraw_limits(account_id)
        logger.warning("get_sandbox_withdraw_limits: native client not available")
        return None

    async def get_sandbox_max_lots(
        self,
        account_id: str,
        instrument_id: str,
        price: float | None = None,
    ) -> dict | None:
        """Get the max lots available for a sandbox account (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_max_lots(
                account_id=account_id,
                instrument_id=instrument_id,
                price=price,
            )
        logger.warning("get_sandbox_max_lots: native client not available")
        return None

    async def post_sandbox_stop_order(
        self,
        account_id: str,
        figi: str,
        quantity: int,
        order_id: str,
        price: float | None = None,
        stop_price: float | None = None,
        direction: int = 1,
        expiration_type: int = 1,
        stop_order_type: int = 1,
        exchange_order_type: int = 0,
        take_profit_type: int = 0,
    ) -> dict | None:
        """Post a stop-order in the sandbox (F14)."""
        if self._native is not None:
            return await self._native.post_sandbox_stop_order(
                account_id=account_id,
                figi=figi,
                quantity=quantity,
                order_id=order_id,
                price=price,
                stop_price=stop_price,
                direction=direction,
                expiration_type=expiration_type,
                stop_order_type=stop_order_type,
                exchange_order_type=exchange_order_type,
                take_profit_type=take_profit_type,
            )
        logger.warning("post_sandbox_stop_order: native client not available")
        return None

    async def get_sandbox_stop_orders(self, account_id: str) -> list[dict]:
        """Get active stop-orders for a sandbox account (F14)."""
        if self._native is not None:
            return await self._native.get_sandbox_stop_orders(account_id)
        logger.warning("get_sandbox_stop_orders: native client not available")
        return []

    async def cancel_sandbox_stop_order(
        self,
        account_id: str,
        stop_order_id: str,
    ) -> dict | None:
        """Cancel a stop-order in the sandbox (F14)."""
        if self._native is not None:
            return await self._native.cancel_sandbox_stop_order(account_id, stop_order_id)
        logger.warning("cancel_sandbox_stop_order: native client not available")
        return None
