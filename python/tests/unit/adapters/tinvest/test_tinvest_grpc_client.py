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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient


class TestTInvestGrpcClientStub:
    """Tests for TInvestGrpcClient when PyO3 module is NOT available (stub mode)."""

    @pytest.fixture
    def stub_client(self):
        """Create a TInvestGrpcClient in stub mode (no native PyO3)."""
        with patch.object(
            TInvestGrpcClient,
            "_create_native_client",
            return_value=None,
        ):
            config = TInvestClientConfig(token="test_stub_token")
            client = TInvestGrpcClient(config)
            yield client

    def test_is_connected_returns_false_when_no_native(self, stub_client):
        # Arrange, Act, Assert
        assert stub_client.is_connected() is False

    def test_has_native_streaming_returns_false_when_no_native(self, stub_client):
        # Arrange, Act, Assert
        assert stub_client._has_native_streaming() is False

    @pytest.mark.asyncio
    async def test_connect_stub_mode(self, stub_client):
        # Arrange, Act - should not raise
        await stub_client.connect()
        # Assert - still not connected (stub mode)
        assert stub_client.is_connected() is False

    @pytest.mark.asyncio
    async def test_disconnect_stub_mode(self, stub_client):
        # Arrange
        await stub_client.connect()
        # Act - should not raise
        await stub_client.disconnect()
        # Assert
        assert stub_client.is_connected() is False

    @pytest.mark.asyncio
    async def test_request_instruments_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.request_instruments()
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_request_instrument_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.request_instrument("BBG004730N88")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_request_order_book_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.request_order_book("BBG004730N88")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_request_trades_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.request_trades("BBG004730N88")
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_request_candles_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.request_candles("BBG004730N88", interval=1)
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_post_order_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.post_order(
            account_id="test-acc",
            figi="BBG004730N88",
            quantity=10,
        )
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_order_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.cancel_order("test-acc", "order-1")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_order_state_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_order_state("test-acc", "order-1")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_orders_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_orders("test-acc")
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_get_portfolio_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_portfolio("test-acc")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_positions_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_positions("test-acc")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_operations_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_operations("test-acc")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_accounts_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_accounts()
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_replace_order_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.replace_order(
            account_id="test-acc",
            order_id="order-1",
            idempotency_key="uuid-123",
            quantity=5,
            price=250.0,
        )
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_post_stop_order_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.post_stop_order(
            account_id="test-acc",
            figi="BBG004730N88",
            quantity=10,
            order_id="uuid-456",
            stop_price=240.0,
        )
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_stop_order_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.cancel_stop_order("test-acc", "stop-order-1")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_stop_orders_stub_returns_empty(self, stub_client):
        # Arrange, Act
        result = await stub_client.get_stop_orders("test-acc")
        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_open_sandbox_account_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.open_sandbox_account()
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_close_sandbox_account_stub_returns_none(self, stub_client):
        # Arrange, Act
        result = await stub_client.close_sandbox_account("test-acc")
        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_sandbox_pay_in_stub_returns_none(self, stub_client):
        # Arrange
        amount = {"currency": "RUB", "units": 100000, "nano": 0}
        # Act
        result = await stub_client.sandbox_pay_in("test-acc", amount)
        # Assert
        assert result is None


class TestTInvestGrpcClientPolling:
    """Tests for polling-based subscription mechanism."""

    @pytest.fixture
    def polling_client(self):
        """Create a TInvestGrpcClient with stubbed native."""
        with patch.object(
            TInvestGrpcClient,
            "_create_native_client",
            return_value=None,
        ):
            config = TInvestClientConfig(token="test_poll_token")
            client = TInvestGrpcClient(config)
            yield client

    def test_start_polling_registers_task(self, polling_client):
        # Arrange
        callback = MagicMock()
        poll_fn = AsyncMock(return_value={"data": "test"})
        # Act
        polling_client._start_polling(
            key="test:key",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        # Assert
        assert "test:key" in polling_client._polling_tasks
        assert "test:key" in polling_client._subscription_callbacks

    def test_stop_polling_removes_task(self, polling_client):
        # Arrange
        callback = MagicMock()
        poll_fn = AsyncMock(return_value={"data": "test"})
        polling_client._start_polling(
            key="test:key",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        # Act
        polling_client._stop_polling("test:key")
        # Assert
        assert "test:key" not in polling_client._polling_tasks
        assert "test:key" not in polling_client._subscription_callbacks

    def test_start_polling_idempotent(self, polling_client):
        # Arrange
        callback = MagicMock()
        poll_fn = AsyncMock(return_value={"data": "test"})
        # Act
        polling_client._start_polling(
            key="test:key",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        task_count = len(polling_client._polling_tasks)
        polling_client._start_polling(
            key="test:key",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        # Assert - same number of tasks (no duplicate)
        assert len(polling_client._polling_tasks) == task_count

    @pytest.mark.asyncio
    async def test_disconnect_cancels_all_polling_tasks(self, polling_client):
        # Arrange
        callback = MagicMock()
        poll_fn = AsyncMock(return_value={"data": "test"})
        polling_client._start_polling(
            key="order_book:BBG004730N88:10",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        polling_client._start_polling(
            key="trades:BBG004730N88",
            poll_fn=poll_fn,
            interval_ms=100,
            callback=callback,
        )
        # Act
        await polling_client.disconnect()
        # Assert - all tasks cancelled
        assert len(polling_client._polling_tasks) == 0
        assert len(polling_client._subscription_callbacks) == 0

    @pytest.mark.asyncio
    async def test_polling_loop_invokes_callback(self, polling_client):
        """Verify that the polling loop actually invokes the callback."""
        # Arrange
        callback = MagicMock()
        poll_data = {"bids": [], "asks": []}
        poll_fn = AsyncMock(return_value=poll_data)
        # Act
        polling_client._start_polling(
            key="test:poll:cb",
            poll_fn=poll_fn,
            interval_ms=10,  # Fast polling for test
            callback=callback,
        )
        # Wait for a couple of poll cycles
        await asyncio.sleep(0.05)
        # Stop
        polling_client._stop_polling("test:poll:cb")
        # Assert - callback was called at least once
        assert callback.called
