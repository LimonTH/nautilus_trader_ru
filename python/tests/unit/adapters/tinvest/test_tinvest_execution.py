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
from unittest.mock import MagicMock, patch

import pytest

from nautilus_trader.adapters.tinvest.execution import (
    _safe_extract_price,
    _TINVEST_DIRECTION_TO_SIDE,
    _TINVEST_ORDER_TYPE,
    _TINVEST_STATUS_TO_ORDER_STATUS,
)
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.objects import Price as ModelPrice


class TestSafeExtractPrice:
    def test_none_returns_zero_price(self):
        # Arrange, Act
        result = _safe_extract_price(None)
        # Assert
        assert result.as_f64() == 0.0

    def test_none_returns_default_precision(self):
        # Arrange, Act
        result = _safe_extract_price(None, default_precision=4)
        # Assert
        assert result.precision == 4

    def test_dict_units_only(self):
        # Arrange
        raw = {"units": 150, "nano": 0}
        # Act
        result = _safe_extract_price(raw, default_precision=2)
        # Assert
        assert result.as_f64() == 150.0
        assert result.precision == 2

    def test_dict_nano_only(self):
        # Arrange
        raw = {"units": 0, "nano": 500_000_000}  # 0.5
        # Act
        result = _safe_extract_price(raw, default_precision=2)
        # Assert
        assert result.as_f64() == 0.5

    def test_dict_units_and_nano(self):
        # Arrange
        raw = {"units": 100, "nano": 250_000_000}  # 100.25
        # Act
        result = _safe_extract_price(raw, default_precision=2)
        # Assert
        assert result.as_f64() == 100.25

    def test_non_dict_non_object_returns_zero(self):
        # Arrange, Act
        result = _safe_extract_price("not valid", default_precision=2)
        # Assert
        assert result.as_f64() == 0.0

    def test_missing_units_in_dict_defaults_to_zero(self):
        # Arrange
        raw = {"nano": 500_000_000}
        # Act
        result = _safe_extract_price(raw, default_precision=2)
        # Assert
        assert result.as_f64() == 0.5


class TestDirectionMappings:
    def test_direction_1_is_buy(self):
        assert _TINVEST_DIRECTION_TO_SIDE[1] == OrderSide.BUY

    def test_direction_2_is_sell(self):
        assert _TINVEST_DIRECTION_TO_SIDE[2] == OrderSide.SELL


class TestOrderTypeMappings:
    def test_type_1_is_limit(self):
        assert _TINVEST_ORDER_TYPE[1] == OrderType.LIMIT

    def test_type_2_is_market(self):
        assert _TINVEST_ORDER_TYPE[2] == OrderType.MARKET


class TestStatusMappings:
    def test_status_0_is_initialized(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[0] == OrderStatus.INITIALIZED

    def test_status_1_is_filled(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[1] == OrderStatus.FILLED

    def test_status_2_is_rejected(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[2] == OrderStatus.REJECTED

    def test_status_3_is_canceled(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[3] == OrderStatus.CANCELED

    def test_status_4_is_accepted(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[4] == OrderStatus.ACCEPTED

    def test_status_5_is_partially_filled(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[5] == OrderStatus.PARTIALLY_FILLED

    def test_status_6_is_pending_cancel(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[6] == OrderStatus.PENDING_CANCEL

    def test_status_7_is_expired(self):
        assert _TINVEST_STATUS_TO_ORDER_STATUS[7] == OrderStatus.EXPIRED


class TestTInvestExecutionClientMock:
    """Tests for TInvestExecutionClient using mocked gRPC client."""

    def _make_exec_client(self, account_id: str = "TINVEST-001"):
        """Helper to create a TInvestExecutionClient with mocked dependencies."""
        from nautilus_trader.adapters.tinvest.execution import TInvestExecutionClient
        from nautilus_trader.adapters.tinvest.config import (
            TInvestClientConfig,
            TInvestExecClientConfig,
        )
        from nautilus_trader.common.component import LiveClock, MessageBus
        from nautilus_trader.model.identifiers import AccountId, TraderId

        loop = asyncio.get_event_loop()
        trader_id = TraderId("TESTER-001")
        clock = LiveClock()

        mock_client = MagicMock()
        mock_client._has_native_streaming.return_value = False
        mock_client._native = None

        mock_provider = MagicMock()
        mock_provider.is_loaded = False
        mock_provider.get_instruments.return_value = {}
        mock_provider.count = 0

        msgbus = MessageBus(trader_id, clock)
        cache = MagicMock()

        config = TInvestExecClientConfig(
            tinvest=TInvestClientConfig(token="test"),
            account_id=account_id,
        )

        exec_client = TInvestExecutionClient(
            loop=loop,
            client=mock_client,
            account_id=AccountId(account_id),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=mock_provider,
            config=config,
            name="TINVEST",
        )
        return exec_client, mock_client, mock_provider

    def test_initialization(self):
        # Arrange, Act
        exec_client, mock_client, _ = self._make_exec_client()
        # Assert
        assert exec_client is not None
        assert exec_client._client is mock_client

    def test_parse_instrument_id(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        # Act
        result = exec_client._parse_instrument_id("BBG004730N88")
        # Assert
        assert result.symbol.value == "BBG004730N88"
        assert result.venue.value == "TINVEST"

    def test_order_state_to_report(self):
        # Arrange
        exec_client, mock_client, _ = self._make_exec_client()
        state = {
            "figi": "BBG004730N88",
            "direction": 1,
            "order_type": 1,
            "execution_report_status": 4,
            "lots_requested": 10,
            "lots_executed": 0,
            "order_id": "test-order-123",
        }
        # Act
        report = exec_client._order_state_to_report(state)
        # Assert
        assert report.venue_order_id.value == "test-order-123"
        assert report.order_side == OrderSide.BUY
        assert report.order_type == OrderType.LIMIT
        assert report.order_status == OrderStatus.ACCEPTED
        assert report.quantity.as_double() == 10.0

    def test_parse_order_status_report(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        data = {
            "order_id": "order-456",
            "direction": 2,
            "order_type": 1,
            "execution_report_status": 1,
            "ticker": "SBER",
            "lot_size": 5,
        }
        # Act
        report = exec_client._parse_order_status_report(data)
        # Assert
        assert report is not None
        assert report.venue_order_id.value == "order-456"
        assert report.order_side == OrderSide.SELL
        assert report.order_status == OrderStatus.FILLED
        assert report.quantity.as_double() == 5.0

    def test_parse_account_balances_from_dict(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        data = {
            "payload_type": "portfolio",
            "total_amount_portfolio": {
                "currency": "RUB",
                "units": 500000,
                "nano": 0,
            },
        }
        # Act
        balances, margins = exec_client._parse_account_balances(data)
        # Assert
        assert len(balances) == 1
        assert balances[0].total.as_f64() == 500000.0

    def test_parse_account_balances_empty(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        data = {"payload_type": "portfolio"}
        # Act
        balances, margins = exec_client._parse_account_balances(data)
        # Assert
        assert len(balances) == 0
        assert len(margins) == 0

    def test_parse_position_status_reports_returns_empty_for_metadata(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        data = {
            "payload_type": "position",
            "money_count": 1,
            "securities_count": 3,
            "futures_count": 0,
            "options_count": 0,
        }
        # Act
        reports = exec_client._parse_position_status_reports(data)
        # Assert
        assert len(reports) == 0

    @pytest.mark.asyncio
    async def test_update_account_state_with_mocked_portfolio(self):
        # Arrange
        exec_client, mock_client, _ = self._make_exec_client()
        mock_client.get_portfolio.return_value = {
            "total_amount_portfolio": {
                "currency": "RUB",
                "units": 100000,
                "nano": 0,
            },
        }
        mock_client.get_positions.return_value = {
            "securities": [],
            "futures": [],
            "currencies": [],
        }

        # Ensure account_id is set
        exec_client._set_account_id = MagicMock()

        # Act
        await exec_client._update_account_state()
        # Assert
        mock_client.get_portfolio.assert_called_once_with("TINVEST-001")
        mock_client.get_positions.assert_called_once_with("TINVEST-001")

    def test_operation_item_to_fill_reports(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        item = {
            "id": "op-123",
            "figi": "BBG004730N88",
            "quantity": 10,
            "price": {"units": 250, "nano": 0},
            "payment": {"units": 2500, "nano": 0},
            "commission": {"units": 5, "nano": 0, "currency": "RUB"},
        }
        # Act
        reports = exec_client._operation_item_to_fill_reports(item, ts_init=1234567890)
        # Assert
        assert len(reports) == 1
        report = reports[0]
        assert report.trade_id.value == "op-123"
        assert report.order_side == OrderSide.BUY  # positive payment = buy
        assert report.last_qty.as_double() == 10.0
        assert report.last_px.as_f64() == 250.0

    def test_operation_item_to_fill_reports_sell_side(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        item = {
            "id": "op-456",
            "figi": "BBG004730N88",
            "quantity": 5,
            "price": {"units": 240, "nano": 0},
            "payment": {"units": -1200, "nano": 0},  # negative = sell
            "commission": {"units": 3, "nano": 0, "currency": "RUB"},
        }
        # Act
        reports = exec_client._operation_item_to_fill_reports(item, ts_init=1234567890)
        # Assert
        assert len(reports) == 1
        assert reports[0].order_side == OrderSide.SELL

    def test_operation_item_zero_quantity_skipped(self):
        # Arrange
        exec_client, _, _ = self._make_exec_client()
        item = {
            "id": "op-zero",
            "figi": "BBG004730N88",
            "quantity": 0,
            "price": {"units": 250, "nano": 0},
            "payment": {"units": 0, "nano": 0},
        }
        # Act
        reports = exec_client._operation_item_to_fill_reports(item, ts_init=1234567890)
        # Assert
        assert len(reports) == 0
