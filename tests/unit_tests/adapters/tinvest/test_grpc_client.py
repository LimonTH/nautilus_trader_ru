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
import logging
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_config(**kwargs) -> TInvestClientConfig:
    defaults = {"token": "test-token"}
    defaults.update(kwargs)
    return TInvestClientConfig(**defaults)


def _make_native_mock(**method_overrides):
    """
    Return a MagicMock simulating the PyO3 native client.

    All async methods return sensible defaults. Use method_overrides
    to customize specific return values.
    """
    native = MagicMock()
    native.connect = AsyncMock()
    native.disconnect = AsyncMock()
    native.is_connected = False
    native.has_native_streaming = False
    native.request_instruments = AsyncMock(return_value=[])
    native.request_instrument = AsyncMock(return_value=None)
    native.request_order_book = AsyncMock(return_value={
        "figi": "TEST_FIGI",
        "depth": 10,
        "bids": [],
        "asks": [],
    })
    native.request_trades = AsyncMock(return_value=[])
    native.request_candles = AsyncMock(return_value=[])
    native.post_order = AsyncMock(return_value={
        "order_id": "order-001",
        "execution_report_status": 4,
    })
    native.post_order_async = AsyncMock(return_value={
        "order_request_id": "req-001",
    })
    native.cancel_order = AsyncMock(return_value={"success": True})
    native.get_orders = AsyncMock(return_value=[])
    native.get_positions = AsyncMock(return_value={
        "securities": [],
        "futures": [],
        "currencies": [],
    })
    native.get_portfolio = AsyncMock(return_value={
        "total_amount_shares": {},
        "total_amount_bonds": {},
    })

    # Apply overrides
    for attr, value in method_overrides.items():
        setattr(native, attr, value)

    return native


def _make_client_without_native(**config_kwargs) -> TInvestGrpcClient:
    """Create a TInvestGrpcClient and force _native = None."""
    config = _make_config(**config_kwargs)
    client = TInvestGrpcClient(config)
    client._native = None
    return client


# ──────────────────────────────────────────────────────────────────────────────
# TInvestGrpcClient — Initialization
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestGrpcClientInit:
    def test_create_with_config(self):
        """Client can be created with a TInvestClientConfig."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        assert client._config is config
        assert client._polling_tasks == {}
        assert client._subscription_callbacks == {}
        # _native may be None (no PyO3) or a real native client (PyO3 available)
        # _native_streaming reflects actual native streaming availability

    def test_native_streaming_detection_when_native_present(self):
        """When native client has has_native_streaming=True, it is detected."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        # Manually inject native mock with streaming support
        native_mock = _make_native_mock(has_native_streaming=True)
        client._native = native_mock
        client._native_streaming = client._detect_native_streaming()

        assert client._native_streaming is True
        assert client._has_native_streaming() is True

    def test_native_streaming_detection_when_native_absent(self):
        """When _native is forced to None, streaming is not available."""
        client = _make_client_without_native()
        # Re-detect after forcing _native = None (overrides __init__ detection)
        client._native_streaming = client._detect_native_streaming()

        assert client._native is None
        assert client._native_streaming is False
        assert client._has_native_streaming() is False

    def test_native_streaming_detection_no_attribute(self):
        """When native exists but lacks has_native_streaming, returns False."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        # Mock without has_native_streaming attribute
        native_mock = MagicMock(spec=["connect", "disconnect"])
        native_mock.connect = AsyncMock()
        native_mock.disconnect = AsyncMock()
        client._native = native_mock
        client._native_streaming = client._detect_native_streaming()

        assert client._native_streaming is False


# ──────────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────────


class TestConnection:
    @pytest.mark.asyncio
    async def test_connect_with_native_client(self):
        """connect() calls _native.connect() when native is available."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        native_mock = _make_native_mock(is_connected=False)
        client._native = native_mock

        await client.connect()

        native_mock.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_without_native_client_logs_warning(self, caplog):
        """connect() logs warning when native client is not available, does not crash."""
        client = _make_client_without_native()

        with caplog.at_level(logging.WARNING):
            await client.connect()

        assert "T-Invest gRPC client not available" in caplog.text

    @pytest.mark.asyncio
    async def test_disconnect_cancels_polling_tasks(self):
        """disconnect() cancels all active polling tasks and clears state."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        # Inject mock native so disconnect doesn't crash
        native_mock = _make_native_mock()
        client._native = native_mock

        # Manually add a polling task
        async def _dummy_poll():
            while True:
                await asyncio.sleep(0.1)

        task = asyncio.ensure_future(_dummy_poll())
        client._polling_tasks["test_key"] = task
        client._subscription_callbacks["test_key"] = lambda x: x

        await client.disconnect()

        # Task should be cancelled
        assert task.cancelled() or task.done()
        # State should be cleared
        assert client._polling_tasks == {}
        assert client._subscription_callbacks == {}

    @pytest.mark.asyncio
    async def test_disconnect_without_native(self):
        """disconnect() works even without native client (no crash)."""
        client = _make_client_without_native()

        await client.disconnect()

        # Should not raise; polling state is empty
        assert client._polling_tasks == {}

    def test_is_connected_with_native(self):
        """is_connected() delegates to native.is_connected when available."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        native_mock = _make_native_mock(is_connected=True)
        client._native = native_mock

        assert client.is_connected() is True

    def test_is_connected_without_native(self):
        """is_connected() returns False when native is None."""
        client = _make_client_without_native()

        assert client.is_connected() is False


# ──────────────────────────────────────────────────────────────────────────────
# Data Methods
# ──────────────────────────────────────────────────────────────────────────────


class TestDataMethods:
    @pytest.mark.asyncio
    async def test_request_instruments_returns_list(self):
        """request_instruments returns a list from native client."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = [{"figi": "F1", "ticker": "SBER"}, {"figi": "F2", "ticker": "GAZP"}]
        native_mock = _make_native_mock(request_instruments=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.request_instruments()

        assert result == expected
        native_mock.request_instruments.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_instruments_without_native(self):
        """request_instruments returns [] when native is not available."""
        client = _make_client_without_native()

        result = await client.request_instruments()

        assert result == []

    @pytest.mark.asyncio
    async def test_request_order_book(self):
        """request_order_book returns the order book dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"figi": "F1", "depth": 10, "bids": [], "asks": []}
        native_mock = _make_native_mock(request_order_book=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.request_order_book("F1", depth=10)

        assert result == expected
        native_mock.request_order_book.assert_awaited_once_with("F1", 10)

    @pytest.mark.asyncio
    async def test_request_order_book_without_native(self):
        """request_order_book returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.request_order_book("F1")

        assert result is None

    @pytest.mark.asyncio
    async def test_request_trades(self):
        """request_trades returns a list of trade dicts."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = [{"price": 100.0, "quantity": 10, "direction": 1}]
        native_mock = _make_native_mock(request_trades=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.request_trades("F1", from_ts=0, to_ts=1000)

        assert result == expected
        native_mock.request_trades.assert_awaited_once_with("F1", 0, 1000)

    @pytest.mark.asyncio
    async def test_request_trades_without_native(self):
        """request_trades returns [] when native is not available."""
        client = _make_client_without_native()

        result = await client.request_trades("F1")

        assert result == []

    @pytest.mark.asyncio
    async def test_request_candles(self):
        """request_candles returns a list of candle dicts."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = [{"open": 100, "close": 105, "time": 1234567890}]
        native_mock = _make_native_mock(request_candles=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.request_candles("F1", interval=1)

        assert result == expected

    @pytest.mark.asyncio
    async def test_request_candles_without_native(self):
        """request_candles returns [] when native is not available."""
        client = _make_client_without_native()

        result = await client.request_candles("F1", interval=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_request_instrument_not_found(self):
        """request_instrument returns None when not found."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        native_mock = _make_native_mock(
            request_instrument=AsyncMock(side_effect=Exception("NOT_FOUND")),
        )
        client._native = native_mock

        result = await client.request_instrument("UNKNOWN_FIGI")

        assert result is None

    @pytest.mark.asyncio
    async def test_request_instrument_returns_dict(self):
        """request_instrument returns a dict when found."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"figi": "F1", "ticker": "SBER", "name": "Sberbank"}
        native_mock = _make_native_mock(request_instrument=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.request_instrument("F1")

        assert result == expected

    @pytest.mark.asyncio
    async def test_request_instrument_without_native(self):
        """request_instrument returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.request_instrument("F1")

        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Polling
# ──────────────────────────────────────────────────────────────────────────────


class TestPolling:
    @pytest.mark.asyncio
    async def test_start_polling_creates_task(self):
        """_start_polling creates an asyncio Task."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        poll_fn = AsyncMock(return_value={"data": "test"})
        callback = MagicMock()

        client._start_polling(
            key="test_poll",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )

        assert "test_poll" in client._polling_tasks
        task = client._polling_tasks["test_poll"]
        assert isinstance(task, asyncio.Task)

        # Clean up
        client._stop_polling("test_poll")
        # Wait a tick for cancellation to propagate
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_polling_cancels_task(self):
        """_stop_polling cancels the task and removes it from state."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        async def _never_returns():
            await asyncio.Event().wait()

        task = asyncio.ensure_future(_never_returns())
        client._polling_tasks["test_key"] = task
        client._subscription_callbacks["test_key"] = lambda x: x

        client._stop_polling("test_key")

        # Wait for cancellation to propagate
        await asyncio.sleep(0.02)

        assert "test_key" not in client._polling_tasks
        assert "test_key" not in client._subscription_callbacks
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_duplicate_polling_prevented(self):
        """Calling _start_polling with the same key twice does not create a second task."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        poll_fn = AsyncMock(return_value={})
        callback = MagicMock()

        client._start_polling("dup_key", poll_fn, 100, callback)
        first_task = client._polling_tasks["dup_key"]

        client._start_polling("dup_key", poll_fn, 100, callback)

        # Second call should not overwrite
        assert client._polling_tasks["dup_key"] is first_task

        # Cleanup
        client._stop_polling("dup_key")
        await asyncio.sleep(0.05)


# ──────────────────────────────────────────────────────────────────────────────
# Subscriptions
# ──────────────────────────────────────────────────────────────────────────────


class TestSubscriptions:
    @pytest.mark.asyncio
    async def test_subscribe_order_book_polling(self):
        """subscribe_order_book starts polling when native is available."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        callback = MagicMock()

        await client.subscribe_order_book("F1", depth=10, callback=callback)

        key = "order_book:F1:10"
        assert key in client._polling_tasks
        assert client._subscription_callbacks[key] is callback

        # Cleanup
        client._stop_polling(key)
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_unsubscribe_order_book(self):
        """unsubscribe_order_book stops polling for the given figi."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        async def _dummy():
            await asyncio.Event().wait()

        key = "order_book:F1:5"
        task = asyncio.ensure_future(_dummy())
        client._polling_tasks[key] = task

        await client.unsubscribe_order_book("F1", depth=5)

        assert key not in client._polling_tasks

    @pytest.mark.asyncio
    async def test_subscribe_trades_polling(self):
        """subscribe_trades starts polling when native is available."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        callback = MagicMock()

        await client.subscribe_trades("F1", callback=callback)

        key = "trades:F1"
        assert key in client._polling_tasks
        assert client._subscription_callbacks[key] is callback

        # Cleanup
        client._stop_polling(key)
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_subscribe_candles_polling(self):
        """subscribe_candles starts polling when native is available."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        callback = MagicMock()

        await client.subscribe_candles("F1", interval=1, callback=callback)

        key = "candles:F1:1"
        assert key in client._polling_tasks
        assert client._subscription_callbacks[key] is callback

        # Cleanup
        client._stop_polling(key)
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_subscribe_no_callback_warning(self, caplog):
        """Subscribe without callback logs a warning and returns early."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        with caplog.at_level(logging.WARNING):
            await client.subscribe_order_book("F1", callback=None)

        assert "no callback provided" in caplog.text
        assert "order_book:F1:10" not in client._polling_tasks

    @pytest.mark.asyncio
    async def test_subscribe_trades_no_callback_warning(self, caplog):
        """subscribe_trades without callback logs a warning."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        with caplog.at_level(logging.WARNING):
            await client.subscribe_trades("F1", callback=None)

        assert "no callback provided" in caplog.text

    @pytest.mark.asyncio
    async def test_subscribe_candles_no_callback_warning(self, caplog):
        """subscribe_candles without callback logs a warning."""
        config = _make_config()
        client = TInvestGrpcClient(config)
        client._native = _make_native_mock()

        with caplog.at_level(logging.WARNING):
            await client.subscribe_candles("F1", callback=None)

        assert "no callback provided" in caplog.text

    @pytest.mark.asyncio
    async def test_subscribe_order_book_without_native(self, caplog):
        """subscribe_order_book logs warning when native is not available."""
        client = _make_client_without_native()

        with caplog.at_level(logging.WARNING):
            await client.subscribe_order_book("F1", callback=MagicMock())

        assert "native client not available" in caplog.text


# ──────────────────────────────────────────────────────────────────────────────
# Execution Methods
# ──────────────────────────────────────────────────────────────────────────────


class TestExecutionMethods:
    @pytest.mark.asyncio
    async def test_post_order(self):
        """post_order returns the order response dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"order_id": "ord-123", "execution_report_status": 4}
        native_mock = _make_native_mock(post_order=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.post_order(
            account_id="ACC-1",
            figi="F1",
            quantity=10,
            price=100.0,
            direction=1,
            order_type=2,
            order_id="client-ord-1",
        )

        assert result == expected
        native_mock.post_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_order_without_native(self):
        """post_order returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.post_order(
            account_id="ACC-1",
            figi="F1",
            quantity=10,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_post_order_async(self):
        """post_order_async returns the async response dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"order_request_id": "req-456"}
        native_mock = _make_native_mock(post_order_async=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.post_order_async(
            account_id="ACC-1",
            figi="F1",
            quantity=10,
        )

        assert result == expected
        native_mock.post_order_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_order_async_without_native(self):
        """post_order_async returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.post_order_async(
            account_id="ACC-1",
            figi="F1",
            quantity=10,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """cancel_order returns the cancel response dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"success": True}
        native_mock = _make_native_mock(cancel_order=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.cancel_order("ACC-1", "order-123")

        assert result == expected
        native_mock.cancel_order.assert_awaited_once_with("ACC-1", "order-123")

    @pytest.mark.asyncio
    async def test_cancel_order_without_native(self):
        """cancel_order returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.cancel_order("ACC-1", "order-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_orders(self):
        """get_orders returns a list of order dicts."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = [{"order_id": "ord-1"}, {"order_id": "ord-2"}]
        native_mock = _make_native_mock(get_orders=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.get_orders("ACC-1")

        assert result == expected
        native_mock.get_orders.assert_awaited_once_with("ACC-1")

    @pytest.mark.asyncio
    async def test_get_orders_without_native(self):
        """get_orders returns [] when native is not available."""
        client = _make_client_without_native()

        result = await client.get_orders("ACC-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_positions(self):
        """get_positions returns the positions dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"securities": [], "futures": [], "currencies": []}
        native_mock = _make_native_mock(get_positions=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.get_positions("ACC-1")

        assert result == expected
        native_mock.get_positions.assert_awaited_once_with("ACC-1")

    @pytest.mark.asyncio
    async def test_get_positions_without_native(self):
        """get_positions returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.get_positions("ACC-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_portfolio(self):
        """get_portfolio returns the portfolio dict."""
        config = _make_config()
        client = TInvestGrpcClient(config)

        expected = {"total_amount_shares": {}, "total_amount_bonds": {}}
        native_mock = _make_native_mock(get_portfolio=AsyncMock(return_value=expected))
        client._native = native_mock

        result = await client.get_portfolio("ACC-1")

        assert result == expected
        native_mock.get_portfolio.assert_awaited_once_with("ACC-1")

    @pytest.mark.asyncio
    async def test_get_portfolio_without_native(self):
        """get_portfolio returns None when native is not available."""
        client = _make_client_without_native()

        result = await client.get_portfolio("ACC-1")

        assert result is None
