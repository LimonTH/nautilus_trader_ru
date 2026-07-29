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

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.adapters.tinvest.providers import _try_dict_to_instrument
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.live.cancellation import DEFAULT_FUTURE_CANCELLATION_TIMEOUT
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import BookOrder
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

# Native gRPC streaming import (PyO3)
try:
    from nautilus_trader.core.nautilus_pyo3.tinvest import TInvestMarketDataStream

    _HAS_NATIVE_STREAM_CLASS = True
except ImportError:
    TInvestMarketDataStream = None  # type: ignore
    _HAS_NATIVE_STREAM_CLASS = False

# Map T-Invest candle interval to BarSpec string
_CANDLE_INTERVAL_MAP: dict[int, str] = {
    1: "1-MINUTE",
    2: "5-MINUTE",
    3: "15-MINUTE",
    4: "1-HOUR",
    5: "1-DAY",
    6: "2-MINUTE",
    7: "3-MINUTE",
    8: "10-MINUTE",
    9: "30-MINUTE",
    10: "2-HOUR",
    11: "4-HOUR",
    12: "1-WEEK",
    13: "1-MONTH",
}

# Reverse map from BarSpec string to T-Invest candle interval
_BAR_SPEC_TO_INTERVAL: dict[str, int] = {v: k for k, v in _CANDLE_INTERVAL_MAP.items()}


def _price_from_quotation(quotation: dict | None) -> float:
    """Convert T-Invest Quotation dict (units/nano) to float."""
    if quotation is None:
        return 0.0
    if isinstance(quotation, dict):
        units = float(quotation.get("units", 0))
        nano = float(quotation.get("nano", 0))
        return units + nano * 1e-9
    return 0.0


class TInvestDataClient(LiveMarketDataClient):
    """
    Provides a data client for the T-Invest (MOEX) API.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    client : TInvestGrpcClient
        The T-Invest gRPC client wrapper.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : TInvestInstrumentProvider
        The instrument provider.
    config : TInvestDataClientConfig
        The configuration for the client.
    name : str, optional
        The custom client ID.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: TInvestGrpcClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: TInvestInstrumentProvider,
        config: TInvestDataClientConfig,
        name: str | None,
    ):
        super().__init__(
            loop=loop,
            client_id=ClientId(name or TINVEST_VENUE.value),
            venue=TINVEST_VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
        )

        self._client = client
        self._config = config
        self._instrument_provider = instrument_provider

        self._log.info(f"T-Invest DataClient initialized", LogColor.BLUE)
        self._log.info(f"{config.update_instruments_interval_mins=}", LogColor.BLUE)

        # Periodic instrument update task
        self._update_instruments_interval_mins: int | None = config.update_instruments_interval_mins
        self._update_instruments_task: asyncio.Task | None = None

        # Native gRPC market data stream (replaces polling when available)
        self._market_data_stream = None
        self._native_stream_task: asyncio.Task | None = None

    # -- Connection -------------------------------------------------------------------------------

    async def _connect(self) -> None:
        self._log.info("Connecting T-Invest data client...", LogColor.BLUE)

        # Connect gRPC client
        await self._client.connect()

        # Load instruments via provider (like Bybit does)
        await self._instrument_provider.load_all()
        self._cache_instruments()
        self._send_all_instruments_to_data_engine()

        # Start native gRPC streaming if available
        if self._client._has_native_streaming() and _HAS_NATIVE_STREAM_CLASS:
            native_client = self._client._native
            if native_client is not None:
                self._log.info("Starting native gRPC market data stream", LogColor.BLUE)
                loop = asyncio.get_running_loop()
                self._market_data_stream = TInvestMarketDataStream(
                    native_client,
                    loop,
                )
                self._native_stream_task = self.create_task(
                    self._native_stream_loop(),
                )
                self._log.info("Native gRPC market data stream started", LogColor.GREEN)
        else:
            self._log.info(
                "Native gRPC streaming not available, using polling fallback",
                LogColor.BLUE,
            )

        # Start periodic instrument update if configured
        if self._update_instruments_interval_mins:
            self._update_instruments_task = self.create_task(
                self._update_instruments(self._update_instruments_interval_mins),
            )

        self._log.info("T-Invest data client connected", LogColor.GREEN)

    async def _disconnect(self) -> None:
        self._log.info("Disconnecting T-Invest data client...", LogColor.BLUE)

        # Cancel update task
        if self._update_instruments_task is not None:
            self._update_instruments_task.cancel()
            self._update_instruments_task = None

        # Cancel native stream task
        if self._native_stream_task is not None:
            self._native_stream_task.cancel()
            self._native_stream_task = None

        # Stop native market data stream
        if self._market_data_stream is not None:
            self._market_data_stream.stop()
            self._market_data_stream = None
            self._log.info("Native gRPC market data stream stopped", LogColor.GREEN)

        await self._client.disconnect()
        self._log.info("T-Invest data client disconnected", LogColor.GREEN)

    def _cache_instruments(self) -> None:
        """Cache instruments from provider into the local cache."""
        for instrument_id, instrument in self._instrument_provider.get_instruments().items():
            self._cache.add_instrument(instrument)
            self._handle_data(instrument)

    def _send_all_instruments_to_data_engine(self) -> None:
        """Send all loaded instruments to the data engine."""
        for instrument_id, instrument in self._instrument_provider.get_instruments().items():
            self._cache.add_instrument(instrument)
            self._handle_data(instrument)

    async def _update_instruments(self, interval_mins: int) -> None:
        """Periodically update instruments."""
        while True:
            await asyncio.sleep(interval_mins * 60)
            try:
                await self._instrument_provider.load_all()
                self._cache_instruments()
            except Exception as e:
                self._log.warning(f"Failed to update instruments: {e}")

    # -- Subscriptions ----------------------------------------------------------------------------

    async def _subscribe_instruments(self) -> None:
        # Instruments are loaded on demand via request, not streamed
        pass

    async def _subscribe_instrument(self, instrument_id: InstrumentId) -> None:
        pass

    async def _unsubscribe_instruments(self) -> None:
        pass

    async def _unsubscribe_instrument(self, instrument_id: InstrumentId) -> None:
        pass

    async def _subscribe_order_book_deltas(self, instrument_id: InstrumentId) -> None:
        # T-Invest doesn't provide order book deltas separately; use snapshot
        pass

    async def _unsubscribe_order_book_deltas(self, instrument_id: InstrumentId) -> None:
        pass

    async def _subscribe_order_book_snapshot(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: subscribing to order book for {figi}")
            self._market_data_stream.subscribe([figi], "orderbook")
        else:
            self._log.info(f"Polling: subscribing to order book snapshot for {figi}")
            await self._client.subscribe_order_book(
                figi=figi,
                depth=10,
                callback=lambda data: self._on_order_book(instrument_id, data),
            )

    async def _unsubscribe_order_book_snapshot(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: unsubscribing from order book for {figi}")
            self._market_data_stream.unsubscribe([figi], "orderbook")
        else:
            self._log.info(f"Polling: unsubscribing from order book snapshot for {figi}")
            await self._client.unsubscribe_order_book(figi, depth=10)

    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            # Native orderbook stream provides best bid/ask for QuoteTick extraction
            self._log.info(f"Native streaming: subscribing to order book for quotes {figi}")
            self._market_data_stream.subscribe([figi], "orderbook")
        else:
            self._log.info(f"Polling: subscribing to quote ticks for {figi}")
            # Best bid/ask from order book → QuoteTick
            await self._client.subscribe_order_book(
                figi=figi,
                depth=1,
                callback=lambda data: self._on_quote_tick(instrument_id, data),
            )

    async def _unsubscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: unsubscribing from quotes for {figi}")
            self._market_data_stream.unsubscribe([figi], "orderbook")
        else:
            self._log.info(f"Polling: unsubscribing from quote ticks for {figi}")
            await self._client.unsubscribe_order_book(figi, depth=1)

    async def _subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: subscribing to trades for {figi}")
            self._market_data_stream.subscribe([figi], "trades")
        else:
            self._log.info(f"Polling: subscribing to trade ticks for {figi}")
            await self._client.subscribe_trades(
                figi=figi,
                callback=lambda data: self._on_trade_tick(instrument_id, data),
            )

    async def _unsubscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: unsubscribing from trades for {figi}")
            self._market_data_stream.unsubscribe([figi], "trades")
        else:
            self._log.info(f"Polling: unsubscribing from trade ticks for {figi}")
            await self._client.unsubscribe_trades(figi)

    async def _subscribe_bars(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        # Default to 1-minute bars; the bar type is determined by DataType
        interval = 1

        if use_native:
            self._log.info(f"Native streaming: subscribing to candles for {figi}")
            self._market_data_stream.subscribe([figi], "candles")
        else:
            self._log.info(f"Polling: subscribing to bars for {figi} (interval={interval})")
            await self._client.subscribe_candles(
                figi=figi,
                interval=interval,
                callback=lambda data: self._on_bar(instrument_id, interval, data),
            )

    async def _unsubscribe_bars(self, instrument_id: InstrumentId) -> None:
        figi = instrument_id.symbol.to_string()
        use_native = (
            self._market_data_stream is not None
            and self._market_data_stream.is_active
        )

        if use_native:
            self._log.info(f"Native streaming: unsubscribing from candles for {figi}")
            # Note: Native stream doesn't support candle unsubscription; stop polling instead
            self._log.debug(f"Candle unsubscribe via native stream not supported for {figi}")
        else:
            self._log.info(f"Polling: unsubscribing from bars for {figi}")
            await self._client.unsubscribe_candles(figi, interval=1)

    async def _subscribe_instrument_status(self, instrument_id: InstrumentId) -> None:
        pass

    async def _unsubscribe_instrument_status(self, instrument_id: InstrumentId) -> None:
        pass

    async def _subscribe_instrument_close(self, instrument_id: InstrumentId) -> None:
        pass

    async def _unsubscribe_instrument_close(self, instrument_id: InstrumentId) -> None:
        pass

    # -- Native Stream Loop -----------------------------------------------------------------------

    async def _native_stream_loop(self) -> None:
        """Background task that reads from the native gRPC stream queue.

        Reads Python dicts from `self._market_data_stream.queue` (asyncio.Queue)
        and converts them into Nautilus model objects, then pushes via
        `_handle_data()`.

        Runs until cancelled or the stream is stopped.
        """
        if self._market_data_stream is None:
            self._log.warning("Native stream loop started but stream is None")
            return

        queue = self._market_data_stream.queue
        self._log.info("Native gRPC stream loop started")

        while True:
            try:
                # Wait for data from the native stream queue
                # Use a timeout to periodically check if we should exit
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if stream is still active
                if (
                    self._market_data_stream is None
                    or not self._market_data_stream.is_active
                ):
                    break
                continue
            except asyncio.CancelledError:
                self._log.info("Native gRPC stream loop cancelled")
                break

            if data is None:
                continue

            try:
                self._process_native_stream_data(data)
            except Exception as e:
                self._log.warning(f"Error processing native stream data: {e}")

    def _process_native_stream_data(self, data: dict) -> None:
        """Process a single data dict from the native gRPC stream.

        Parameters
        ----------
        data : dict
            The data dict from the native stream, must contain at least
            ``payload_type`` key.

        """
        payload_type = data.get("payload_type")
        if payload_type is None:
            return

        figi = data.get("figi", "")
        if not figi:
            return

        instrument_id = InstrumentId.from_str(f"{figi}.{TINVEST_VENUE.value}")
        instrument = self._cache.instrument(instrument_id)
        price_precision = instrument.price_precision if instrument else 2
        size_precision = instrument.size_precision if instrument else 0
        ts_init = self._clock.timestamp_ns()

        if payload_type == "trade":
            self._process_native_trade(
                instrument_id, data, price_precision, size_precision, ts_init,
            )
        elif payload_type == "orderbook":
            self._process_native_orderbook(
                instrument_id, data, price_precision, size_precision, ts_init,
            )
        elif payload_type == "candle":
            self._process_native_candle(
                instrument_id, data, price_precision, size_precision, ts_init,
            )
        # Skip subscription confirmations, pings, status updates, etc.

    def _process_native_trade(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        """Convert native trade dict to TradeTick and push to data engine."""
        try:
            direction = data.get("direction", 0)
            if direction == 1:
                aggressor_side = AggressorSide.BUY
            elif direction == 2:
                aggressor_side = AggressorSide.SELL
            else:
                aggressor_side = AggressorSide.BUY

            price_val = _price_from_quotation(data.get("price"))
            quantity = float(data.get("quantity", 0))

            time_seconds = data.get("time_seconds") or 0
            time_nanos = data.get("time_nanos") or 0
            ts_event = time_seconds * 1_000_000_000 + time_nanos

            trade_id_str = data.get("trade_id", "")
            trade_id = TradeId(trade_id_str) if trade_id_str else TradeId("0")

            tick = TradeTick(
                instrument_id=instrument_id,
                price=Price(price_val, price_precision),
                size=Quantity(quantity, size_precision),
                aggressor_side=aggressor_side,
                trade_id=trade_id,
                ts_event=ts_event or ts_init,
                ts_init=ts_init,
            )
            self._handle_data(tick)
        except Exception as e:
            self._log.warning(
                f"Failed to process native trade for {instrument_id}: {e}",
            )

    def _process_native_orderbook(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        """Convert native orderbook dict to OrderBookDepth10 and QuoteTick.

        The native stream delivers order book with bids/asks as dicts
        keyed by quantity (string), values are Quotation dicts.
        """
        try:
            bids_raw = data.get("bids") or {}
            asks_raw = data.get("asks") or {}

            time_seconds = data.get("time_seconds") or 0
            time_nanos = data.get("time_nanos") or 0
            ts_event = time_seconds * 1_000_000_000 + time_nanos

            # Build BookOrder lists: sorted by price descending (bids) / ascending (asks)
            bid_entries: list[tuple[float, float]] = []
            ask_entries: list[tuple[float, float]] = []

            for qty_str, price_quot in bids_raw.items():
                try:
                    qty = float(qty_str)
                    px = _price_from_quotation(price_quot)
                    bid_entries.append((px, qty))
                except (ValueError, TypeError):
                    continue

            for qty_str, price_quot in asks_raw.items():
                try:
                    qty = float(qty_str)
                    px = _price_from_quotation(price_quot)
                    ask_entries.append((px, qty))
                except (ValueError, TypeError):
                    continue

            # Sort bids descending by price, asks ascending by price
            bid_entries.sort(key=lambda x: x[0], reverse=True)
            ask_entries.sort(key=lambda x: x[0])

            # Take top 10 for each side
            bid_entries = bid_entries[:10]
            ask_entries = ask_entries[:10]

            if not bid_entries or not ask_entries:
                return

            bid_orders: list[BookOrder] = []
            ask_orders: list[BookOrder] = []
            bid_counts: list[int] = []
            ask_counts: list[int] = []

            for px, qty in bid_entries:
                bid_orders.append(
                    BookOrder(
                        side=OrderSide.BUY,
                        price=Price(px, price_precision),
                        size=Quantity(qty, size_precision),
                        order_id=0,
                    ),
                )
                bid_counts.append(1)

            for px, qty in ask_entries:
                ask_orders.append(
                    BookOrder(
                        side=OrderSide.SELL,
                        price=Price(px, price_precision),
                        size=Quantity(qty, size_precision),
                        order_id=0,
                    ),
                )
                ask_counts.append(1)

            # Push OrderBookDepth10
            snapshot = OrderBookDepth10(
                instrument_id=instrument_id,
                bids=bid_orders,
                asks=ask_orders,
                bid_counts=bid_counts,
                ask_counts=ask_counts,
                flags=0,
                sequence=0,
                ts_event=ts_event or ts_init,
                ts_init=ts_init,
            )
            self._handle_data(snapshot)

            # Also extract QuoteTick from best bid/ask
            best_bid_px, best_bid_qty = bid_entries[0]
            best_ask_px, best_ask_qty = ask_entries[0]
            quote_tick = QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(best_bid_px, price_precision),
                ask_price=Price(best_ask_px, price_precision),
                bid_size=Quantity(best_bid_qty, size_precision),
                ask_size=Quantity(best_ask_qty, size_precision),
                ts_event=ts_event or ts_init,
                ts_init=ts_init,
            )
            self._handle_data(quote_tick)

        except Exception as e:
            self._log.warning(
                f"Failed to process native orderbook for {instrument_id}: {e}",
            )

    def _process_native_candle(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        """Convert native candle dict to Bar and push to data engine."""
        try:
            interval = data.get("interval", 1)
            bar_spec = _CANDLE_INTERVAL_MAP.get(interval, "1-MINUTE")
            bar_type = BarType(instrument_id, bar_spec)

            open_px = _price_from_quotation(data.get("open"))
            high_px = _price_from_quotation(data.get("high"))
            low_px = _price_from_quotation(data.get("low"))
            close_px = _price_from_quotation(data.get("close"))
            volume = float(data.get("volume", 0))

            time_seconds = data.get("time_seconds") or 0
            time_nanos = data.get("time_nanos") or 0
            ts_event = time_seconds * 1_000_000_000 + time_nanos

            bar = Bar(
                bar_type=bar_type,
                open=Price(open_px, price_precision),
                high=Price(high_px, price_precision),
                low=Price(low_px, price_precision),
                close=Price(close_px, price_precision),
                volume=Quantity(volume, size_precision),
                ts_event=ts_event or ts_init,
                ts_init=ts_init,
            )
            self._handle_data(bar)
        except Exception as e:
            self._log.warning(
                f"Failed to process native candle for {instrument_id}: {e}",
            )

    # -- Callback Handlers ------------------------------------------------------------------------

    def _on_order_book(self, instrument_id: InstrumentId, data: dict) -> None:
        """Handle order book update from streaming.

        Converts T-Invest order book dict to OrderBookDepth10 and pushes
        via _handle_data().
        """
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            ts_event = self._clock.timestamp_ns()
            ts_init = self._clock.timestamp_ns()

            # Determine the instrument
            instrument = self._cache.instrument(instrument_id)
            if instrument is None:
                self._log.debug(f"Instrument {instrument_id} not in cache for order book")
                return

            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            # Build BookOrder lists for bids and asks
            bid_orders: list[BookOrder] = []
            ask_orders: list[BookOrder] = []
            bid_counts: list[int] = []
            ask_counts: list[int] = []

            for b in bids[:10]:
                if b.get("price") is not None:
                    order = BookOrder(
                        side=OrderSide.BUY,
                        price=Price(_price_from_quotation(b.get("price")), price_precision),
                        size=Quantity(float(b.get("quantity", 0)), size_precision),
                        order_id=0,
                    )
                    bid_orders.append(order)
                    bid_counts.append(1)

            for a in asks[:10]:
                if a.get("price") is not None:
                    order = BookOrder(
                        side=OrderSide.SELL,
                        price=Price(_price_from_quotation(a.get("price")), price_precision),
                        size=Quantity(float(a.get("quantity", 0)), size_precision),
                        order_id=0,
                    )
                    ask_orders.append(order)
                    ask_counts.append(1)

            if not bid_orders or not ask_orders:
                return

            # Create OrderBookDepth10
            snapshot = OrderBookDepth10(
                instrument_id=instrument_id,
                bids=bid_orders,
                asks=ask_orders,
                bid_counts=bid_counts,
                ask_counts=ask_counts,
                flags=0,
                sequence=0,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._handle_data(snapshot)

        except Exception as e:
            self._log.warning(f"Failed to process order book for {instrument_id}: {e}")

    def _on_quote_tick(self, instrument_id: InstrumentId, data: dict) -> None:
        """Handle best bid/ask from order book as QuoteTick.

        Uses depth=1 order book data to extract best bid/ask.
        """
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            if not bids or not asks:
                return

            best_bid = bids[0]
            best_ask = asks[0]

            bid_price = _price_from_quotation(best_bid.get("price"))
            ask_price = _price_from_quotation(best_ask.get("price"))
            bid_size = float(best_bid.get("quantity", 0))
            ask_size = float(best_ask.get("quantity", 0))
            ts_event = self._clock.timestamp_ns()
            ts_init = self._clock.timestamp_ns()

            # Determine the instrument for price precision
            instrument = self._cache.instrument(instrument_id)
            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            tick = QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(bid_price, price_precision),
                ask_price=Price(ask_price, price_precision),
                bid_size=Quantity(bid_size, size_precision),
                ask_size=Quantity(ask_size, size_precision),
                ts_event=ts_event,
                ts_init=ts_init,
            )
            self._handle_data(tick)

        except Exception as e:
            self._log.warning(f"Failed to process quote tick for {instrument_id}: {e}")

    def _on_trade_tick(self, instrument_id: InstrumentId, data: list[dict]) -> None:
        """Handle trade updates from streaming.

        Converts T-Invest trade list to TradeTick objects.
        """
        try:
            if not data:
                return

            instrument = self._cache.instrument(instrument_id)
            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            for trade in data:
                price_val = _price_from_quotation(trade.get("price"))
                quantity = float(trade.get("quantity", 0))
                direction_str = trade.get("direction", "UNSPECIFIED")

                # Map direction to aggressor side
                if direction_str == "BUY":
                    aggressor_side = AggressorSide.BUY
                elif direction_str == "SELL":
                    aggressor_side = AggressorSide.SELL
                else:
                    # Default to BUY for unspecified
                    aggressor_side = AggressorSide.BUY

                trade_id_str = trade.get("trade_id", "")
                trade_id = TradeId(trade_id_str) if trade_id_str else TradeId("0")
                trade_time_s = trade.get("time", 0)
                ts_event = trade_time_s * 1_000_000_000 if trade_time_s else self._clock.timestamp_ns()
                ts_init = self._clock.timestamp_ns()

                tick = TradeTick(
                    instrument_id=instrument_id,
                    price=Price(price_val, price_precision),
                    size=Quantity(quantity, size_precision),
                    aggressor_side=aggressor_side,
                    trade_id=trade_id,
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                self._handle_data(tick)

        except Exception as e:
            self._log.warning(f"Failed to process trade tick for {instrument_id}: {e}")

    def _on_bar(self, instrument_id: InstrumentId, interval: int, data: list[dict]) -> None:
        """Handle candle updates from polling.

        Converts T-Invest candle list to Bar objects.
        """
        try:
            if not data:
                return

            instrument = self._cache.instrument(instrument_id)
            price_precision = instrument.price_precision if instrument else 2
            size_precision = instrument.size_precision if instrument else 0

            # Determine bar spec from interval
            bar_spec = _CANDLE_INTERVAL_MAP.get(interval, "1-MINUTE")
            bar_type = BarType(instrument_id, bar_spec)

            for candle in data:
                open_px = _price_from_quotation(candle.get("open"))
                high_px = _price_from_quotation(candle.get("high"))
                low_px = _price_from_quotation(candle.get("low"))
                close_px = _price_from_quotation(candle.get("close"))
                volume = float(candle.get("volume", 0))
                candle_time_s = candle.get("time", 0)
                ts_event = candle_time_s * 1_000_000_000 if candle_time_s else self._clock.timestamp_ns()
                ts_init = self._clock.timestamp_ns()

                bar = Bar(
                    bar_type=bar_type,
                    open=Price(open_px, price_precision),
                    high=Price(high_px, price_precision),
                    low=Price(low_px, price_precision),
                    close=Price(close_px, price_precision),
                    volume=Quantity(volume, size_precision),
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                self._handle_data(bar)

        except Exception as e:
            self._log.warning(f"Failed to process bar for {instrument_id}: {e}")

    # -- Requests ---------------------------------------------------------------------------------

    async def _request_instrument(self, instrument_id: InstrumentId) -> None:
        # Check cache first
        cached = self._instrument_provider.get_instrument(str(instrument_id))
        if cached is not None:
            self._cache.add_instrument(cached)
            self._handle_data(cached)
            return

        # Try loading via gRPC
        figi = instrument_id.symbol.to_string()
        result = await self._client.request_instrument(figi)
        if result is not None:
            instrument = _try_dict_to_instrument(result)
            if instrument is not None:
                instrument_id_str = str(instrument.id)
                self._instrument_provider.add_instrument(instrument_id_str, instrument)
                self._cache.add_instrument(instrument)
                self._handle_data(instrument)
                self._log.info(f"Loaded instrument via gRPC: {figi}")
            else:
                self._log.warning(f"Could not convert instrument: {figi}")
        else:
            self._log.warning(f"Instrument not found: {instrument_id}")

    async def _request_instruments(self) -> None:
        # Load all instruments via the provider
        if not self._instrument_provider.is_loaded:
            await self._instrument_provider.load_all()
            for instrument_id, instrument in self._instrument_provider.get_instruments().items():
                self._cache.add_instrument(instrument)
                self._handle_data(instrument)

    async def _request_quote_ticks(
        self,
        instrument_id: InstrumentId,
        limit: int | None = None,
    ) -> None:
        figi = instrument_id.symbol.to_string()
        depth = limit or 10

        self._log.info(f"Requesting order book for {figi} depth={depth}")

        order_book = await self._client.request_order_book(figi, depth)
        if order_book is not None:
            bids = order_book.get("bids", [])
            asks = order_book.get("asks", [])
            self._log.info(
                f"Got order book for {figi}: {len(bids)} bids, {len(asks)} asks",
            )

            # Convert best bid/ask to QuoteTick
            if bids and asks:
                best_bid = bids[0]
                best_ask = asks[0]
                bid_price = _price_from_quotation(best_bid.get("price"))
                ask_price = _price_from_quotation(best_ask.get("price"))
                bid_size = float(best_bid.get("quantity", 0))
                ask_size = float(best_ask.get("quantity", 0))
                ts_event = self._clock.timestamp_ns()

                instrument = self._cache.instrument(instrument_id)
                price_precision = instrument.price_precision if instrument else 2
                size_precision = instrument.size_precision if instrument else 0

                tick = QuoteTick(
                    instrument_id=instrument_id,
                    bid_price=Price(bid_price, price_precision),
                    ask_price=Price(ask_price, price_precision),
                    bid_size=Quantity(bid_size, size_precision),
                    ask_size=Quantity(ask_size, size_precision),
                    ts_event=ts_event,
                    ts_init=ts_event,
                )
                self._handle_data(tick)

    async def _request_trade_ticks(
        self,
        instrument_id: InstrumentId,
        limit: int | None = None,
    ) -> None:
        figi = instrument_id.symbol.to_string()
        self._log.info(f"Requesting trades for {figi}")

        trades = await self._client.request_trades(figi)
        self._log.info(f"Got {len(trades)} trades for {figi}")

        # Process via callback handler
        self._on_trade_tick(instrument_id, trades)

    async def _request_bars(self, data_type: DataType) -> None:
        metadata = data_type.metadata
        instrument_id = metadata.get("instrument_id")
        bar_spec = metadata.get("bar_spec")

        if instrument_id is None:
            self._log.warning("No instrument_id in bar request metadata")
            return

        self._log.info(f"Requesting bars for {instrument_id} spec={bar_spec}")

        # Map bar_spec to T-Invest candle interval
        interval = _BAR_SPEC_TO_INTERVAL.get(str(bar_spec))
        if interval is None:
            self._log.warning(f"Unknown bar spec: {bar_spec}")
            return

        figi = str(instrument_id)
        now_ns = self._clock.timestamp_ns()
        one_day_ns = 86_400_000_000_000  # 24 hours in nanos
        from_ns = now_ns - one_day_ns * 30  # Default: last 30 days

        candles = await self._client.request_candles(
            figi=figi,
            interval=interval,
            from_ts=from_ns,
            to_ts=now_ns,
            limit=100,
        )

        self._log.info(f"Got {len(candles)} candles for {figi}")

        # Process via callback handler
        self._on_bar(instrument_id, interval, candles)
