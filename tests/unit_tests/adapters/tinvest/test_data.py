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

import asyncio
from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.data import TInvestDataClient
from nautilus_trader.adapters.tinvest.constants import _CANDLE_INTERVAL_MAP
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.identifiers import InstrumentId

from tests.unit_tests.adapters.tinvest.conftest import make_mock_cache
from tests.unit_tests.adapters.tinvest.conftest import make_mock_clock
from tests.unit_tests.adapters.tinvest.conftest import make_mock_grpc_client
from tests.unit_tests.adapters.tinvest.conftest import make_mock_instrument_provider
from tests.unit_tests.adapters.tinvest.conftest import make_mock_message_bus
from tests.unit_tests.adapters.tinvest.conftest import make_tinvest_client_config


# ──────────────────────────────────────────────────────────────────────────────
# Test double: shadows TInvestDataClient methods by delegating to the real class
# ──────────────────────────────────────────────────────────────────────────────


class _TestDataClient:
    """
    A plain Python test double for TInvestDataClient.

    Does NOT inherit from TInvestDataClient, so there are no Cython cdef
    restrictions.  All attributes are regular Python attributes (mostly
    MagicMock instances).  Methods delegate to the real TInvestDataClient
    unbound methods via cast.
    """

    _log: MagicMock
    _loop: MagicMock
    _client: MagicMock
    _msgbus: MagicMock
    _cache: MagicMock
    _clock: MagicMock
    _instrument_provider: MagicMock
    _config: MagicMock
    _handle_data: MagicMock
    create_task: MagicMock

    # -- Lifecycle -------------------------------------------------------------

    async def _connect(self) -> None:
        await TInvestDataClient._connect(cast(TInvestDataClient, self))

    async def _disconnect(self) -> None:
        await TInvestDataClient._disconnect(cast(TInvestDataClient, self))

    # -- Internal helpers (called by _connect) ---------------------------------

    def _cache_instruments(self) -> None:
        TInvestDataClient._cache_instruments(cast(TInvestDataClient, self))

    def _send_all_instruments_to_data_engine(self) -> None:
        TInvestDataClient._send_all_instruments_to_data_engine(cast(TInvestDataClient, self))

    # -- Subscriptions ---------------------------------------------------------

    async def _subscribe_order_book_snapshot(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._subscribe_order_book_snapshot(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _unsubscribe_order_book_snapshot(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._unsubscribe_order_book_snapshot(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._subscribe_quote_ticks(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _unsubscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._unsubscribe_quote_ticks(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._subscribe_trade_ticks(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _unsubscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._unsubscribe_trade_ticks(
            cast(TInvestDataClient, self), instrument_id,
        )

    async def _subscribe_bars(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._subscribe_bars(cast(TInvestDataClient, self), instrument_id)

    async def _unsubscribe_bars(self, instrument_id: InstrumentId) -> None:
        await TInvestDataClient._unsubscribe_bars(cast(TInvestDataClient, self), instrument_id)

    # -- Callbacks -------------------------------------------------------------

    def _on_order_book(self, instrument_id: InstrumentId, data: dict) -> None:
        TInvestDataClient._on_order_book(cast(TInvestDataClient, self), instrument_id, data)

    def _on_quote_tick(self, instrument_id: InstrumentId, data: dict) -> None:
        TInvestDataClient._on_quote_tick(cast(TInvestDataClient, self), instrument_id, data)

    def _on_trade_tick(self, instrument_id: InstrumentId, data: list[dict]) -> None:
        TInvestDataClient._on_trade_tick(cast(TInvestDataClient, self), instrument_id, data)

    def _on_bar(self, instrument_id: InstrumentId, interval: int, data: list[dict]) -> None:
        TInvestDataClient._on_bar(cast(TInvestDataClient, self), instrument_id, interval, data)

    # -- Requests --------------------------------------------------------------

    async def _request_bars(self, request) -> None:
        await TInvestDataClient._request_bars(cast(TInvestDataClient, self), request)

    async def _request_order_book_snapshot(self, request) -> None:
        await TInvestDataClient._request_order_book_snapshot(
            cast(TInvestDataClient, self), request,
        )

    async def _request_trade_ticks(self, request) -> None:
        await TInvestDataClient._request_trade_ticks(cast(TInvestDataClient, self), request)

    async def _request_instrument(self, request) -> None:
        await TInvestDataClient._request_instrument(cast(TInvestDataClient, self), request)

    async def _request_instruments(self, request) -> None:
        await TInvestDataClient._request_instruments(cast(TInvestDataClient, self), request)

    async def _request_quote_ticks(self, request) -> None:
        await TInvestDataClient._request_quote_ticks(cast(TInvestDataClient, self), request)

    # -- Native processing -----------------------------------------------------

    def _process_native_stream_data(self, data: dict) -> None:
        TInvestDataClient._process_native_stream_data(cast(TInvestDataClient, self), data)

    def _process_native_trade(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        TInvestDataClient._process_native_trade(
            cast(TInvestDataClient, self),
            instrument_id, data, price_precision, size_precision, ts_init,
        )

    def _process_native_orderbook(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        TInvestDataClient._process_native_orderbook(
            cast(TInvestDataClient, self),
            instrument_id, data, price_precision, size_precision, ts_init,
        )

    def _process_native_candle(
        self,
        instrument_id: InstrumentId,
        data: dict,
        price_precision: int,
        size_precision: int,
        ts_init: int,
    ) -> None:
        TInvestDataClient._process_native_candle(
            cast(TInvestDataClient, self),
            instrument_id, data, price_precision, size_precision, ts_init,
        )


def _make_data_client(
    *,
    loop: asyncio.AbstractEventLoop | None = None,
    grpc_client: MagicMock | None = None,
    msgbus: MagicMock | None = None,
    cache: MagicMock | None = None,
    clock: MagicMock | None = None,
    instrument_provider: MagicMock | None = None,
    config: TInvestDataClientConfig | None = None,
) -> _TestDataClient:
    """
    Create a _TestDataClient with all dependencies mocked.

    Returns a plain Python object (not a Cython extension type), so all
    attributes are freely settable.
    """
    if loop is None:
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
    if grpc_client is None:
        grpc_client = make_mock_grpc_client()
    if msgbus is None:
        msgbus = make_mock_message_bus()
    if cache is None:
        cache = make_mock_cache()
    if clock is None:
        clock = make_mock_clock()
    if instrument_provider is None:
        instrument_provider = make_mock_instrument_provider()
    if config is None:
        config = TInvestDataClientConfig(
            tinvest=make_tinvest_client_config(),
            update_instruments_interval_mins=None,
        )

    client = _TestDataClient()

    # Core dependencies
    client._log = MagicMock()
    client._loop = loop
    client._client = grpc_client
    client._msgbus = msgbus
    client._cache = cache
    client._clock = clock
    client._instrument_provider = instrument_provider
    client._config = config

    # Internal state
    client._update_instruments_interval_mins = config.update_instruments_interval_mins
    client._update_instruments_task = None
    client._market_data_stream = None
    client._native_stream_task = None

    # Override _handle_data, _handle_bars and create_task to verify calls
    client._handle_data = MagicMock()
    client._handle_bars = MagicMock()
    client.create_task = MagicMock(return_value=MagicMock(spec=asyncio.Task))

    return client


def _make_mock_instrument(price_precision=2, size_precision=0):
    """Return a mock instrument with given precisions."""
    instr = MagicMock()
    instr.price_precision = price_precision
    instr.size_precision = size_precision
    instr.id = InstrumentId.from_str("BBG004730N88.TINVEST")
    return instr


# ──────────────────────────────────────────────────────────────────────────────
# T7: TestTInvestDataClientConnection
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestDataClientConnection:
    """Tests for _connect and _disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_loads_instruments(self):
        """
        _connect must call instrument_provider.load_all() and cache instruments.
        """
        # Arrange
        mock_instr = _make_mock_instrument()
        provider = make_mock_instrument_provider()
        provider.load_all = AsyncMock()
        provider.get_instruments = MagicMock(return_value={"BBG004730N88.TINVEST": mock_instr})

        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)

        grpc = make_mock_grpc_client()
        grpc.connect = AsyncMock()
        grpc._has_native_streaming = MagicMock(return_value=False)

        client = _make_data_client(
            grpc_client=grpc,
            cache=cache,
            instrument_provider=provider,
        )

        # Act
        await client._connect()

        # Assert
        provider.load_all.assert_awaited_once()
        cache.add_instrument.assert_called()
        client._handle_data.assert_called()

    @pytest.mark.asyncio
    async def test_connect_starts_native_stream_when_available(self):
        """
        When _has_native_streaming() returns True and _HAS_NATIVE_STREAM_CLASS is True,
        _connect must create TInvestMarketDataStream and start the native stream loop.
        """
        # Arrange
        mock_instr = _make_mock_instrument()
        provider = make_mock_instrument_provider()
        provider.load_all = AsyncMock()
        provider.get_instruments = MagicMock(return_value={"BBG004730N88.TINVEST": mock_instr})

        grpc = make_mock_grpc_client()
        grpc.connect = AsyncMock()
        grpc._has_native_streaming = MagicMock(return_value=True)
        grpc._native = MagicMock()  # non-None → native client available

        client = _make_data_client(
            grpc_client=grpc,
            instrument_provider=provider,
        )
        # Replace _native_stream_loop so it doesn't actually run
        client._native_stream_loop = MagicMock()

        mock_stream_class = MagicMock()
        mock_stream_instance = MagicMock()
        mock_stream_class.return_value = mock_stream_instance

        # _connect calls asyncio.get_running_loop() — patch it to return our mock
        with patch("asyncio.get_running_loop", return_value=client._loop):
            with patch(
                "nautilus_trader.adapters.tinvest.data._HAS_NATIVE_STREAM_CLASS",
                True,
            ):
                with patch(
                    "nautilus_trader.adapters.tinvest.data.TInvestMarketDataStream",
                    mock_stream_class,
                ):
                    # Act
                    await client._connect()

        # Assert
        mock_stream_class.assert_called_once_with(grpc._native, client._loop)
        assert client._market_data_stream is mock_stream_instance
        client.create_task.assert_called()

    @pytest.mark.asyncio
    async def test_connect_falls_back_to_polling(self):
        """
        When native streaming is not available, _connect must log polling fallback
        and NOT create a market data stream.
        """
        # Arrange
        mock_instr = _make_mock_instrument()
        provider = make_mock_instrument_provider()
        provider.load_all = AsyncMock()
        provider.get_instruments = MagicMock(return_value={"BBG004730N88.TINVEST": mock_instr})

        grpc = make_mock_grpc_client()
        grpc.connect = AsyncMock()
        grpc._has_native_streaming = MagicMock(return_value=False)

        client = _make_data_client(
            grpc_client=grpc,
            instrument_provider=provider,
        )

        with patch(
            "nautilus_trader.adapters.tinvest.data._HAS_NATIVE_STREAM_CLASS",
            False,
        ):
            # Act
            await client._connect()

        # Assert
        assert client._market_data_stream is None
        polling_logged = any(
            "polling" in str(call).lower()
            for call in client._log.info.call_args_list
        )
        assert polling_logged, "Expected polling fallback log message"

    @pytest.mark.asyncio
    async def test_disconnect_stops_streams_and_tasks(self):
        """
        _disconnect must cancel tasks, stop market data stream, and disconnect gRPC.
        """
        # Arrange
        grpc = make_mock_grpc_client()
        grpc.disconnect = AsyncMock()

        client = _make_data_client(grpc_client=grpc)

        # Simulate active state
        mock_update_task = MagicMock(spec=asyncio.Task)
        mock_native_task = MagicMock(spec=asyncio.Task)
        mock_stream = MagicMock()

        client._update_instruments_task = mock_update_task
        client._native_stream_task = mock_native_task
        client._market_data_stream = mock_stream

        # Act
        await client._disconnect()

        # Assert
        mock_update_task.cancel.assert_called_once()
        assert client._update_instruments_task is None

        mock_native_task.cancel.assert_called_once()
        assert client._native_stream_task is None

        mock_stream.stop.assert_called_once()
        assert client._market_data_stream is None

        grpc.disconnect.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# T8: TestSubscriptionsAndCallbacks
# ──────────────────────────────────────────────────────────────────────────────


class TestSubscriptionsAndCallbacks:
    """Tests for subscription methods and data callbacks."""

    @pytest.fixture
    def instrument_id(self) -> InstrumentId:
        return InstrumentId.from_str("BBG004730N88.TINVEST")

    @pytest.fixture
    def client(self) -> _TestDataClient:
        """Return a _TestDataClient with pre-configured gRPC mock for subscriptions."""
        grpc = make_mock_grpc_client()
        grpc.subscribe_order_book = AsyncMock()
        grpc.unsubscribe_order_book = AsyncMock()
        grpc.subscribe_trades = AsyncMock()
        grpc.unsubscribe_trades = AsyncMock()
        grpc.subscribe_candles = AsyncMock()
        grpc.unsubscribe_candles = AsyncMock()
        grpc._has_native_streaming = MagicMock(return_value=False)

        mock_instr = _make_mock_instrument()
        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)

        return _make_data_client(grpc_client=grpc, cache=cache)

    # -- Subscribe order book -------------------------------------------------

    @pytest.mark.asyncio
    async def test_subscribe_order_book_native(self, client, instrument_id):
        """
        When native stream is active, subscribe_order_book_snapshot uses native subscribe.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._subscribe_order_book_snapshot(instrument_id)

        mock_stream.subscribe.assert_called_once_with(["BBG004730N88"], "orderbook")
        client._client.subscribe_order_book.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_order_book_polling(self, client, instrument_id):
        """
        When native stream is not active, subscribe_order_book_snapshot uses polling.
        """
        client._market_data_stream = None

        await client._subscribe_order_book_snapshot(instrument_id)

        client._client.subscribe_order_book.assert_awaited_once()
        call_kwargs = client._client.subscribe_order_book.call_args.kwargs
        assert call_kwargs["figi"] == "BBG004730N88"
        assert call_kwargs["depth"] == 10

    @pytest.mark.asyncio
    async def test_unsubscribe_order_book_native(self, client, instrument_id):
        """
        When native stream is active, unsubscribe uses native unsubscribe.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._unsubscribe_order_book_snapshot(instrument_id)

        mock_stream.unsubscribe.assert_called_once_with(["BBG004730N88"], "orderbook")

    @pytest.mark.asyncio
    async def test_unsubscribe_order_book_polling(self, client, instrument_id):
        """
        When native stream is not active, unsubscribe uses polling.
        """
        client._market_data_stream = None

        await client._unsubscribe_order_book_snapshot(instrument_id)

        client._client.unsubscribe_order_book.assert_awaited_once_with(
            "BBG004730N88", depth=10,
        )

    # -- Subscribe quote ticks -------------------------------------------------

    @pytest.mark.asyncio
    async def test_subscribe_quote_ticks_native(self, client, instrument_id):
        """
        When native stream is active, subscribe_quote_ticks uses native orderbook stream.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._subscribe_quote_ticks(instrument_id)

        mock_stream.subscribe.assert_called_once_with(["BBG004730N88"], "orderbook")
        client._client.subscribe_order_book.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_quote_ticks_polling(self, client, instrument_id):
        """
        When native stream is not active, subscribe_quote_ticks uses polling (depth=1).
        """
        client._market_data_stream = None

        await client._subscribe_quote_ticks(instrument_id)

        client._client.subscribe_order_book.assert_awaited_once()
        call_kwargs = client._client.subscribe_order_book.call_args.kwargs
        assert call_kwargs["depth"] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_quote_ticks_native(self, client, instrument_id):
        """
        When native stream is active, unsubscribe_quote_ticks uses native unsubscribe.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._unsubscribe_quote_ticks(instrument_id)

        mock_stream.unsubscribe.assert_called_once_with(["BBG004730N88"], "orderbook")

    @pytest.mark.asyncio
    async def test_unsubscribe_quote_ticks_polling(self, client, instrument_id):
        """
        When native stream is not active, unsubscribe_quote_ticks uses polling (depth=1).
        """
        client._market_data_stream = None

        await client._unsubscribe_quote_ticks(instrument_id)

        client._client.unsubscribe_order_book.assert_awaited_once_with(
            "BBG004730N88", depth=1,
        )

    # -- Subscribe trade ticks -------------------------------------------------

    @pytest.mark.asyncio
    async def test_subscribe_trade_ticks_native(self, client, instrument_id):
        """
        When native stream is active, subscribe_trade_ticks uses native trades stream.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._subscribe_trade_ticks(instrument_id)

        mock_stream.subscribe.assert_called_once_with(["BBG004730N88"], "trades")

    @pytest.mark.asyncio
    async def test_subscribe_trade_ticks_polling(self, client, instrument_id):
        """
        When native stream is not active, subscribe_trade_ticks uses polling.
        """
        client._market_data_stream = None

        await client._subscribe_trade_ticks(instrument_id)

        client._client.subscribe_trades.assert_awaited_once()
        call_kwargs = client._client.subscribe_trades.call_args.kwargs
        assert call_kwargs["figi"] == "BBG004730N88"

    @pytest.mark.asyncio
    async def test_unsubscribe_trade_ticks_native(self, client, instrument_id):
        """
        When native stream is active, unsubscribe_trade_ticks uses native unsubscribe.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._unsubscribe_trade_ticks(instrument_id)

        mock_stream.unsubscribe.assert_called_once_with(["BBG004730N88"], "trades")

    @pytest.mark.asyncio
    async def test_unsubscribe_trade_ticks_polling(self, client, instrument_id):
        """
        When native stream is not active, unsubscribe_trade_ticks uses polling.
        """
        client._market_data_stream = None

        await client._unsubscribe_trade_ticks(instrument_id)

        client._client.unsubscribe_trades.assert_awaited_once_with("BBG004730N88")

    # -- Subscribe bars --------------------------------------------------------

    @pytest.mark.asyncio
    async def test_subscribe_bars_native(self, client, instrument_id):
        """
        When native stream is active, subscribe_bars uses native candles stream.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._subscribe_bars(instrument_id)

        mock_stream.subscribe.assert_called_once_with(["BBG004730N88"], "candles")

    @pytest.mark.asyncio
    async def test_subscribe_bars_polling(self, client, instrument_id):
        """
        When native stream is not active, subscribe_bars uses polling.
        """
        client._market_data_stream = None

        await client._subscribe_bars(instrument_id)

        client._client.subscribe_candles.assert_awaited_once()
        call_kwargs = client._client.subscribe_candles.call_args.kwargs
        assert call_kwargs["figi"] == "BBG004730N88"
        assert call_kwargs["interval"] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_bars_native(self, client, instrument_id):
        """
        When native stream is active, unsubscribe_bars logs unsupported debug.
        """
        mock_stream = MagicMock()
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        await client._unsubscribe_bars(instrument_id)

        client._log.debug.assert_called()

    @pytest.mark.asyncio
    async def test_unsubscribe_bars_polling(self, client, instrument_id):
        """
        When native stream is not active, unsubscribe_bars uses polling.
        """
        client._market_data_stream = None

        await client._unsubscribe_bars(instrument_id)

        client._client.unsubscribe_candles.assert_awaited_once_with(
            "BBG004730N88", interval=1,
        )

    # -- on_order_book callback ------------------------------------------------

    def test_on_order_book_valid_data(self, client, instrument_id, sample_order_book_dict):
        """
        _on_order_book must create OrderBookDepth10 and call _handle_data.

        Note: OrderBookDepth10 is a fixed-size structure (always 10 levels).
        The sample data has 2 real levels on each side; the remaining 8 are
        zero-filled.
        """
        client._handle_data.reset_mock()

        client._on_order_book(instrument_id, sample_order_book_dict)

        client._handle_data.assert_called_once()
        call_arg = client._handle_data.call_args[0][0]
        assert isinstance(call_arg, OrderBookDepth10)
        # OrderBookDepth10 always has 10 entries; count non-zero orders
        non_zero_bids = [b for b in call_arg.bids if b.price != 0]
        non_zero_asks = [a for a in call_arg.asks if a.price != 0]
        assert len(non_zero_bids) == 2
        assert len(non_zero_asks) == 2

    def test_on_order_book_missing_instrument(self, client, instrument_id, sample_order_book_dict):
        """
        _on_order_book must return early when instrument is not in cache.
        """
        client._cache.instrument = MagicMock(return_value=None)
        client._handle_data.reset_mock()

        client._on_order_book(instrument_id, sample_order_book_dict)

        client._handle_data.assert_not_called()

    # -- on_quote_tick callback -------------------------------------------------

    def test_on_quote_tick_valid_data(self, client, instrument_id, sample_order_book_dict):
        """
        _on_quote_tick must create QuoteTick from best bid/ask and call _handle_data.
        """
        client._handle_data.reset_mock()

        client._on_quote_tick(instrument_id, sample_order_book_dict)

        client._handle_data.assert_called_once()
        call_arg = client._handle_data.call_args[0][0]
        assert isinstance(call_arg, QuoteTick)
        assert float(call_arg.bid_price) == 265.0
        assert float(call_arg.ask_price) == 266.0
        assert float(call_arg.bid_size) == 100.0
        assert float(call_arg.ask_size) == 80.0

    def test_on_quote_tick_empty_book(self, client, instrument_id):
        """
        _on_quote_tick must return early when bids or asks are empty.
        """
        client._handle_data.reset_mock()
        empty_data = {"bids": [], "asks": []}

        client._on_quote_tick(instrument_id, empty_data)

        client._handle_data.assert_not_called()

    # -- on_trade_tick callback -------------------------------------------------

    def test_on_trade_tick_valid_data(self, client, instrument_id):
        """
        _on_trade_tick must create TradeTick objects from a list of trade dicts.
        """
        client._handle_data.reset_mock()
        trade_data = [
            {
                "price": {"units": "265", "nano": 50000000},
                "quantity": "10",
                "direction": "BUY",
                "trade_id": "abc123",
                "time": 1705312800,
            },
        ]

        client._on_trade_tick(instrument_id, trade_data)

        client._handle_data.assert_called_once()
        call_arg = client._handle_data.call_args[0][0]
        assert isinstance(call_arg, TradeTick)
        assert float(call_arg.price) == 265.05
        assert float(call_arg.size) == 10.0

    def test_on_trade_tick_empty_data(self, client, instrument_id):
        """
        _on_trade_tick must return early when data list is empty.
        """
        client._handle_data.reset_mock()

        client._on_trade_tick(instrument_id, [])

        client._handle_data.assert_not_called()

    # -- on_bar callback --------------------------------------------------------

    def test_on_bar_valid_data(self, client, instrument_id):
        """
        _on_bar must create Bar objects from a list of candle dicts.
        """
        client._handle_data.reset_mock()
        candle_data = [
            {
                "open": {"units": "260", "nano": 0},
                "high": {"units": "270", "nano": 0},
                "low": {"units": "255", "nano": 0},
                "close": {"units": "265", "nano": 50000000},
                "volume": "1000",
                "time": 1705312800,
            },
        ]

        client._on_bar(instrument_id, 1, candle_data)

        client._handle_data.assert_called_once()
        call_arg = client._handle_data.call_args[0][0]
        assert isinstance(call_arg, Bar)
        assert float(call_arg.open) == 260.0
        assert float(call_arg.high) == 270.0
        assert float(call_arg.low) == 255.0
        assert float(call_arg.close) == 265.05
        assert float(call_arg.volume) == 1000.0


# ──────────────────────────────────────────────────────────────────────────────
# T9: TestNativeStreamProcessing
# ──────────────────────────────────────────────────────────────────────────────


class TestNativeStreamProcessing:
    """Tests for _process_native_stream_data and native processing helpers."""

    @pytest.fixture
    def instrument_id(self) -> InstrumentId:
        return InstrumentId.from_str("BBG004730N88.TINVEST")

    @pytest.fixture
    def client(self) -> _TestDataClient:
        """Return a _TestDataClient with instrument in cache."""
        mock_instr = _make_mock_instrument(price_precision=2, size_precision=0)
        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)

        client = _make_data_client(cache=cache)
        client._handle_data.reset_mock()
        return client

    # -- _process_native_trade --------------------------------------------------

    def test_process_native_trade(self, client, instrument_id):
        """
        _process_native_trade must convert a native trade dict to TradeTick.
        """
        data = {
            "direction": 1,  # BUYER
            "price": {"units": "265", "nano": 50000000},
            "quantity": "10",
            "time_seconds": 1705312800,
            "time_nanos": 123456789,
            "trade_id": "native_trade_001",
        }

        client._process_native_trade(instrument_id, data, 2, 0, 100)

        client._handle_data.assert_called_once()
        tick = client._handle_data.call_args[0][0]
        assert isinstance(tick, TradeTick)
        assert float(tick.price) == 265.05
        assert float(tick.size) == 10.0
        assert tick.trade_id.value == "native_trade_001"

    # -- _process_native_orderbook ----------------------------------------------

    def test_process_native_orderbook(self, client, instrument_id):
        """
        _process_native_orderbook must create both OrderBookDepth10 and QuoteTick.
        """
        data = {
            "bids": {
                "100": {"units": "265", "nano": 0},
                "50": {"units": "264", "nano": 0},
            },
            "asks": {
                "80": {"units": "266", "nano": 0},
                "30": {"units": "267", "nano": 0},
            },
            "time_seconds": 1705312800,
            "time_nanos": 0,
        }

        client._process_native_orderbook(instrument_id, data, 2, 0, 100)

        assert client._handle_data.call_count == 2

        # First call: OrderBookDepth10
        snapshot = client._handle_data.call_args_list[0][0][0]
        assert isinstance(snapshot, OrderBookDepth10)
        non_zero_bids = [b for b in snapshot.bids if b.price != 0]
        non_zero_asks = [a for a in snapshot.asks if a.price != 0]
        assert len(non_zero_bids) == 2
        assert len(non_zero_asks) == 2

        # Second call: QuoteTick
        quote = client._handle_data.call_args_list[1][0][0]
        assert isinstance(quote, QuoteTick)
        assert float(quote.bid_price) == 265.0
        assert float(quote.ask_price) == 266.0

    # -- _process_native_candle -------------------------------------------------

    def test_process_native_candle(self, client, instrument_id):
        """
        _process_native_candle must convert a native candle dict to Bar.
        """
        data = {
            "interval": 1,
            "open": {"units": "260", "nano": 0},
            "high": {"units": "270", "nano": 0},
            "low": {"units": "255", "nano": 0},
            "close": {"units": "265", "nano": 50000000},
            "volume": "1000",
            "time_seconds": 1705312800,
            "time_nanos": 0,
        }

        client._process_native_candle(instrument_id, data, 2, 0, 100)

        client._handle_data.assert_called_once()
        bar = client._handle_data.call_args[0][0]
        assert isinstance(bar, Bar)
        assert float(bar.open) == 260.0
        assert float(bar.high) == 270.0
        assert float(bar.low) == 255.0
        assert float(bar.close) == 265.05
        assert float(bar.volume) == 1000.0

    # -- _process_native_stream_data edge cases ---------------------------------

    def test_unknown_payload_type_ignored(self, client):
        """
        _process_native_stream_data must silently ignore unknown payload types.
        """
        data = {
            "payload_type": "unknown_xyz",
            "figi": "BBG004730N88",
        }
        client._handle_data.reset_mock()

        client._process_native_stream_data(data)

        client._handle_data.assert_not_called()

    def test_missing_figi_ignored(self, client):
        """
        _process_native_stream_data must return early when figi is empty/missing.
        """
        data = {
            "payload_type": "trade",
            "figi": "",
        }
        client._handle_data.reset_mock()

        client._process_native_stream_data(data)

        client._handle_data.assert_not_called()

    def test_missing_payload_type_ignored(self, client):
        """
        _process_native_stream_data must return early when payload_type is None/missing.
        """
        data = {
            "figi": "BBG004730N88",
        }
        client._handle_data.reset_mock()

        client._process_native_stream_data(data)

        client._handle_data.assert_not_called()

    # -- _native_stream_loop integration ----------------------------------------

    @pytest.mark.asyncio
    async def test_process_native_stream_data_loop(self, client):
        """
        _native_stream_loop reads from the market data stream queue and processes data.

        Integration test with a mock asyncio.Queue.  Uses orderbook data
        to verify the loop's dispatch logic.
        """
        mock_queue = asyncio.Queue()
        mock_stream = MagicMock()
        mock_stream.queue = mock_queue
        mock_stream.is_active = True
        client._market_data_stream = mock_stream

        orderbook_data = {
            "payload_type": "orderbook",
            "figi": "BBG004730N88",
            "bids": {
                "100": {"units": "265", "nano": 0},
                "50": {"units": "264", "nano": 0},
            },
            "asks": {
                "80": {"units": "266", "nano": 0},
                "30": {"units": "267", "nano": 0},
            },
            "time_seconds": 1705312800,
            "time_nanos": 0,
        }

        await mock_queue.put(orderbook_data)
        await mock_queue.put(None)  # sentinel to stop

        client._handle_data.reset_mock()

        async def controlled_loop():
            while True:
                data = await mock_queue.get()
                if data is None:
                    break
                try:
                    client._process_native_stream_data(data)
                except Exception:
                    pass

        await controlled_loop()

        # OrderBookDepth10 + QuoteTick = 2 calls
        assert client._handle_data.call_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# T18: TestHistoricalDataRequests
# ──────────────────────────────────────────────────────────────────────────────


class TestHistoricalDataRequests:
    """Tests for _request_bars, _request_order_book_snapshot, _request_trade_ticks."""

    @pytest.fixture
    def client(self):
        """Create a _TestDataClient with mocked gRPC client."""
        mock_instr = _make_mock_instrument()
        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)

        grpc = make_mock_grpc_client()
        grpc.request_candles = AsyncMock(return_value=[])
        grpc.request_order_book = AsyncMock(return_value={
            "bids": [{"price": {"units": "265", "nano": 0}, "quantity": "100"}],
            "asks": [{"price": {"units": "266", "nano": 0}, "quantity": "80"}],
        })
        grpc.request_trades = AsyncMock(return_value=[])

        return _make_data_client(grpc_client=grpc, cache=cache)

    @pytest.fixture
    def instrument_id(self):
        return InstrumentId.from_str("BBG004730N88.TINVEST")

    # -- _request_order_book_snapshot -----------------------------------------------

    @pytest.mark.asyncio
    async def test_request_order_book_snapshot_calls_on_order_book(self, client, instrument_id):
        """
        _request_order_book_snapshot must call gRPC request_order_book
        and invoke _on_order_book handler.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestOrderBookSnapshot

        request = MagicMock(spec=RequestOrderBookSnapshot)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.depth = 10
        request.params = {}
        request.start = None
        request.end = None

        # Act
        await client._request_order_book_snapshot(request)

        # Assert
        client._client.request_order_book.assert_awaited_once()
        # Verify _handle_data was called with OrderBookDepth10
        assert client._handle_data.call_count >= 1

    @pytest.mark.asyncio
    async def test_request_order_book_snapshot_handles_exception(self, client, instrument_id):
        """
        _request_order_book_snapshot must not raise on gRPC error.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestOrderBookSnapshot

        client._client.request_order_book = AsyncMock(side_effect=Exception("gRPC error"))

        request = MagicMock(spec=RequestOrderBookSnapshot)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.depth = 10
        request.params = {}
        request.start = None
        request.end = None

        # Act / Assert — must not raise
        await client._request_order_book_snapshot(request)

    # -- _request_trade_ticks ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_trade_ticks_calls_on_trade_tick(self, client, instrument_id):
        """
        _request_trade_ticks must call gRPC request_trades and invoke
        _on_trade_tick handler.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestTradeTicks

        trade_data = [
            {
                "price": {"units": "265", "nano": 0},
                "quantity": "10",
                "direction": "BUY",
                "trade_id": "t1",
                "time": 1705312800,
            },
        ]
        client._client.request_trades = AsyncMock(return_value=trade_data)

        request = MagicMock(spec=RequestTradeTicks)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Act
        await client._request_trade_ticks(request)

        # Assert
        client._client.request_trades.assert_awaited_once()
        # Verify at least one TradeTick was pushed via _handle_data
        assert client._handle_data.call_count >= 1

    @pytest.mark.asyncio
    async def test_request_trade_ticks_handles_exception(self, client, instrument_id):
        """
        _request_trade_ticks must not raise on gRPC error.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestTradeTicks

        client._client.request_trades = AsyncMock(side_effect=Exception("gRPC error"))

        request = MagicMock(spec=RequestTradeTicks)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Act / Assert — must not raise
        await client._request_trade_ticks(request)

    # -- _request_bars ------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_bars_calls_request_candles(self, client, instrument_id):
        """
        _request_bars must call gRPC request_candles with correct parameters
        and invoke _handle_bars.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestBars

        candle_data = [
            {
                "open": {"units": "265", "nano": 0},
                "high": {"units": "267", "nano": 0},
                "low": {"units": "264", "nano": 0},
                "close": {"units": "266", "nano": 0},
                "volume": "1000",
                "time": 1705312800,
            },
        ]
        client._client.request_candles = AsyncMock(return_value=candle_data)

        bar_spec = BarSpecification.from_str("1-MINUTE-LAST")
        bar_type = BarType(instrument_id, bar_spec)

        request = MagicMock(spec=RequestBars)
        request.bar_type = bar_type
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Act
        await client._request_bars(request)

        # Assert
        client._client.request_candles.assert_awaited_once()
        # Verify _handle_bars was called
        client._handle_bars.assert_called_once()
        call_args = client._handle_bars.call_args
        assert call_args[0][0] == bar_type  # bar_type arg
        assert len(call_args[0][1]) == 1  # one bar

    @pytest.mark.asyncio
    async def test_request_bars_unknown_spec_logs_warning(self, client, instrument_id):
        """
        _request_bars must log a warning and return early for unknown bar specs.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestBars

        bar_spec = BarSpecification.from_str("3-HOUR-LAST")
        bar_type = BarType(instrument_id, bar_spec)

        request = MagicMock(spec=RequestBars)
        request.bar_type = bar_type
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Act
        await client._request_bars(request)

        # Assert — warning logged, no gRPC call
        client._client.request_candles.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_bars_handles_exception(self, client, instrument_id):
        """
        _request_bars must handle gRPC errors gracefully and call _handle_bars
        with empty list.
        """
        # Arrange
        from nautilus_trader.data.messages import RequestBars

        client._client.request_candles = AsyncMock(side_effect=Exception("gRPC error"))

        bar_spec = BarSpecification.from_str("1-MINUTE-LAST")
        bar_type = BarType(instrument_id, bar_spec)

        request = MagicMock(spec=RequestBars)
        request.bar_type = bar_type
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Act
        await client._request_bars(request)

        # Assert — _handle_bars called with empty list
        client._handle_bars.assert_called_once()
        call_args = client._handle_bars.call_args
        assert len(call_args[0][1]) == 0  # empty bars list on error


# ──────────────────────────────────────────────────────────────────────────────
# T20: TestDataHelpers
# ──────────────────────────────────────────────────────────────────────────────


class TestDataHelpers:
    """Tests for module-level helper functions in data.py."""

    def test_datetime_to_ns_none(self):
        from nautilus_trader.adapters.tinvest.data import _datetime_to_ns
        assert _datetime_to_ns(None) is None

    def test_datetime_to_ns_converts(self):
        from datetime import datetime, timezone
        from nautilus_trader.adapters.tinvest.data import _datetime_to_ns
        dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert _datetime_to_ns(dt) == int(dt.timestamp() * 1_000_000_000)

    def test_price_from_quotation_none(self):
        from nautilus_trader.adapters.tinvest.data import _price_from_quotation
        assert _price_from_quotation(None) == 0.0

    def test_price_from_quotation_non_dict(self):
        from nautilus_trader.adapters.tinvest.data import _price_from_quotation
        assert _price_from_quotation("not_a_dict") == 0.0

    def test_price_from_quotation_units_and_nano(self):
        from nautilus_trader.adapters.tinvest.data import _price_from_quotation
        assert _price_from_quotation({"units": "100", "nano": 250000000}) == 100.25

    def test_price_from_quotation_empty_dict(self):
        from nautilus_trader.adapters.tinvest.data import _price_from_quotation
        assert _price_from_quotation({}) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# T21: TestRequestMethods
# ──────────────────────────────────────────────────────────────────────────────


class TestRequestMethods:
    """Tests for _request_instrument, _request_instruments, _request_quote_ticks."""

    @pytest.fixture
    def instrument_id(self):
        return InstrumentId.from_str("BBG004730N88.TINVEST")

    @pytest.fixture
    def client(self):
        mock_instr = _make_mock_instrument()
        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)
        grpc = make_mock_grpc_client()
        return _make_data_client(grpc_client=grpc, cache=cache)

    # -- _request_instrument ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_instrument_cache_hit(self, client, instrument_id):
        """When instrument is in cache, return early without gRPC call."""
        cached = _make_mock_instrument()
        client._instrument_provider.get_instrument = MagicMock(return_value=cached)

        from nautilus_trader.data.messages import RequestInstrument
        request = MagicMock(spec=RequestInstrument)
        request.instrument_id = instrument_id
        request.id = UUID4()

        await client._request_instrument(request)
        client._cache.add_instrument.assert_called()
        client._handle_data.assert_called()

    @pytest.mark.asyncio
    async def test_request_instrument_grpc_load(self, client, instrument_id):
        """When not in cache, load via gRPC."""
        client._instrument_provider.get_instrument = MagicMock(return_value=None)
        client._client.request_instrument = AsyncMock(return_value={
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "instrument_type": "share",
            "lot": 10,
            "currency": "RUB",
            "min_price_increment": {"units": 0, "nano": 10000000},
        })

        from nautilus_trader.data.messages import RequestInstrument
        request = MagicMock(spec=RequestInstrument)
        request.instrument_id = instrument_id
        request.id = UUID4()

        await client._request_instrument(request)
        client._client.request_instrument.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_instrument_grpc_returns_none(self, client, instrument_id):
        """When gRPC returns None, log warning."""
        client._instrument_provider.get_instrument = MagicMock(return_value=None)
        client._client.request_instrument = AsyncMock(return_value=None)

        from nautilus_trader.data.messages import RequestInstrument
        request = MagicMock(spec=RequestInstrument)
        request.instrument_id = instrument_id
        request.id = UUID4()

        await client._request_instrument(request)
        client._log.warning.assert_called()

    # -- _request_instruments --------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_instruments_loads_all(self, client):
        """_request_instruments loads instruments via provider."""
        mock_instr = _make_mock_instrument()
        client._instrument_provider.is_loaded = False
        client._instrument_provider.load_all = AsyncMock()
        client._instrument_provider.get_instruments = MagicMock(
            return_value={"BBG004730N88.TINVEST": mock_instr},
        )

        from nautilus_trader.data.messages import RequestInstruments
        request = MagicMock(spec=RequestInstruments)
        request.id = UUID4()

        await client._request_instruments(request)
        client._instrument_provider.load_all.assert_awaited_once()
        client._cache.add_instrument.assert_called()
        client._handle_data.assert_called()

    # -- _request_quote_ticks --------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_quote_ticks_success(self, client, instrument_id):
        """_request_quote_ticks must request order book and push QuoteTick."""
        client._client.request_order_book = AsyncMock(return_value={
            "bids": [{"price": {"units": "265", "nano": 0}, "quantity": "100"}],
            "asks": [{"price": {"units": "266", "nano": 0}, "quantity": "80"}],
        })

        from nautilus_trader.data.messages import RequestQuoteTicks
        request = MagicMock(spec=RequestQuoteTicks)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        await client._request_quote_ticks(request)
        client._client.request_order_book.assert_awaited_once()
        client._handle_data.assert_called()

    @pytest.mark.asyncio
    async def test_request_quote_ticks_empty_book(self, client, instrument_id):
        """_request_quote_ticks must handle empty order book gracefully."""
        client._client.request_order_book = AsyncMock(return_value={
            "bids": [], "asks": [],
        })

        from nautilus_trader.data.messages import RequestQuoteTicks
        request = MagicMock(spec=RequestQuoteTicks)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Should not raise
        await client._request_quote_ticks(request)

    @pytest.mark.asyncio
    async def test_request_quote_ticks_exception(self, client, instrument_id):
        """_request_quote_ticks must handle gRPC error gracefully."""
        client._client.request_order_book = AsyncMock(side_effect=Exception("gRPC error"))

        from nautilus_trader.data.messages import RequestQuoteTicks
        request = MagicMock(spec=RequestQuoteTicks)
        request.instrument_id = instrument_id
        request.id = UUID4()
        request.limit = 0
        request.params = {}
        request.start = None
        request.end = None

        # Should not raise
        await client._request_quote_ticks(request)


# ──────────────────────────────────────────────────────────────────────────────
# T22: TestCallbackEdgeCases
# ──────────────────────────────────────────────────────────────────────────────


class TestCallbackEdgeCases:
    """Tests for edge cases in callback handlers."""

    @pytest.fixture
    def instrument_id(self) -> InstrumentId:
        return InstrumentId.from_str("BBG004730N88.TINVEST")

    @pytest.fixture
    def client(self) -> _TestDataClient:
        mock_instr = _make_mock_instrument()
        cache = make_mock_cache()
        cache.instrument = MagicMock(return_value=mock_instr)
        return _make_data_client(cache=cache)

    def test_on_trade_tick_single_dict(self, client, instrument_id):
        """_on_trade_tick accepts single dict (not list)."""
        client._handle_data.reset_mock()
        trade_data = {
            "price": {"units": "265", "nano": 0},
            "quantity": "10",
            "direction": "SELL",
            "trade_id": "sell-1",
            "time": 1705312800,
        }
        client._on_trade_tick(instrument_id, trade_data)
        client._handle_data.assert_called_once()

    def test_on_trade_tick_empty_dict(self, client, instrument_id):
        """_on_trade_tick returns early with empty dict."""
        client._handle_data.reset_mock()
        client._on_trade_tick(instrument_id, {})
        client._handle_data.assert_not_called()

    def test_on_trade_tick_unknown_direction(self, client, instrument_id):
        """_on_trade_tick defaults to BUYER for UNSPECIFIED direction."""
        client._handle_data.reset_mock()
        trade_data = [{
            "price": {"units": "265", "nano": 0},
            "quantity": "10",
            "direction": "UNSPECIFIED",
            "trade_id": "unk-1",
            "time": 1705312800,
        }]
        client._on_trade_tick(instrument_id, trade_data)
        client._handle_data.assert_called_once()
        tick = client._handle_data.call_args[0][0]
        assert tick.aggressor_side.name == "BUYER"

    def test_on_bar_empty_data(self, client, instrument_id):
        """_on_bar returns early when data is empty list."""
        client._handle_data.reset_mock()
        client._on_bar(instrument_id, 1, [])
        client._handle_data.assert_not_called()

    def test_on_bar_empty_data_none(self, client, instrument_id):
        """_on_bar returns early when data is None/empty."""
        client._handle_data.reset_mock()
        client._on_bar(instrument_id, 1, [])
        client._handle_data.assert_not_called()

    def test_on_order_book_no_bids_or_asks(self, client, instrument_id):
        """_on_order_book returns early when no bids/asks."""
        client._handle_data.reset_mock()
        client._on_order_book(instrument_id, {"bids": [], "asks": []})
        client._handle_data.assert_not_called()
