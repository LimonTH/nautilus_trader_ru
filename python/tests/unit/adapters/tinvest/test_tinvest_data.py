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

from nautilus_trader.adapters.tinvest.data import (
    _BAR_SPEC_TO_INTERVAL,
    _CANDLE_INTERVAL_MAP,
    _price_from_quotation,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue


class TestPriceFromQuotation:
    def test_none_returns_zero(self):
        # Arrange, Act
        result = _price_from_quotation(None)
        # Assert
        assert result == 0.0

    def test_empty_dict_returns_zero(self):
        # Arrange, Act
        result = _price_from_quotation({})
        # Assert
        assert result == 0.0

    def test_units_only(self):
        # Arrange
        quot = {"units": 150, "nano": 0}
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == 150.0

    def test_nano_only(self):
        # Arrange
        quot = {"units": 0, "nano": 500_000_000}  # 0.5
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == 0.5

    def test_units_and_nano(self):
        # Arrange
        quot = {"units": 100, "nano": 250_000_000}  # 100.25
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == 100.25

    def test_negative_units(self):
        # Arrange
        quot = {"units": -50, "nano": 0}
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == -50.0

    def test_non_dict_returns_zero(self):
        # Arrange, Act
        result = _price_from_quotation("not a dict")
        # Assert
        assert result == 0.0

    def test_missing_units_defaults_to_zero(self):
        # Arrange
        quot = {"nano": 500_000_000}
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == 0.5

    def test_missing_nano_defaults_to_zero(self):
        # Arrange
        quot = {"units": 42}
        # Act
        result = _price_from_quotation(quot)
        # Assert
        assert result == 42.0


class TestCandleIntervalMaps:
    def test_candle_interval_map_contains_all_intervals(self):
        # Assert
        assert _CANDLE_INTERVAL_MAP[1] == "1-MINUTE"
        assert _CANDLE_INTERVAL_MAP[2] == "5-MINUTE"
        assert _CANDLE_INTERVAL_MAP[3] == "15-MINUTE"
        assert _CANDLE_INTERVAL_MAP[4] == "1-HOUR"
        assert _CANDLE_INTERVAL_MAP[5] == "1-DAY"
        assert _CANDLE_INTERVAL_MAP[6] == "2-MINUTE"
        assert _CANDLE_INTERVAL_MAP[7] == "3-MINUTE"
        assert _CANDLE_INTERVAL_MAP[8] == "10-MINUTE"
        assert _CANDLE_INTERVAL_MAP[9] == "30-MINUTE"
        assert _CANDLE_INTERVAL_MAP[10] == "2-HOUR"
        assert _CANDLE_INTERVAL_MAP[11] == "4-HOUR"
        assert _CANDLE_INTERVAL_MAP[12] == "1-WEEK"
        assert _CANDLE_INTERVAL_MAP[13] == "1-MONTH"

    def test_bar_spec_to_interval_is_reverse(self):
        # BarSpec → interval map is the reverse of interval → BarSpec
        assert _BAR_SPEC_TO_INTERVAL["1-MINUTE"] == 1
        assert _BAR_SPEC_TO_INTERVAL["5-MINUTE"] == 2
        assert _BAR_SPEC_TO_INTERVAL["1-HOUR"] == 4
        assert _BAR_SPEC_TO_INTERVAL["1-DAY"] == 5
        assert _BAR_SPEC_TO_INTERVAL["1-MONTH"] == 13


class TestTInvestDataClientMock:
    """Tests for TInvestDataClient using mocked gRPC client."""

    def _make_data_client(self):
        """Helper to create a TInvestDataClient with mocked dependencies."""
        from nautilus_trader.adapters.tinvest.data import TInvestDataClient
        from nautilus_trader.adapters.tinvest.config import (
            TInvestClientConfig,
            TInvestDataClientConfig,
        )
        from nautilus_trader.common.component import LiveClock, MessageBus
        from nautilus_trader.model.identifiers import TraderId

        loop = asyncio.get_event_loop()
        trader_id = TraderId("TESTER-001")
        clock = LiveClock()

        mock_client = MagicMock()
        mock_client._has_native_streaming.return_value = False
        mock_client._native = None

        mock_provider = MagicMock()
        mock_provider.is_loaded = True
        mock_provider.get_instruments.return_value = {}
        mock_provider.count = 0

        msgbus = MessageBus(trader_id, clock)
        cache = MagicMock()

        config = TInvestDataClientConfig(
            tinvest=TInvestClientConfig(token="test"),
        )

        data_client = TInvestDataClient(
            loop=loop,
            client=mock_client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=mock_provider,
            config=config,
            name="TINVEST",
        )
        return data_client, mock_client, mock_provider

    def test_initialization(self):
        # Arrange, Act
        data_client, mock_client, _ = self._make_data_client()
        # Assert
        assert data_client is not None
        assert data_client._client is mock_client

    @pytest.mark.asyncio
    async def test_subscribe_order_book_snapshot_polling_path(self):
        # Arrange
        data_client, mock_client, _ = self._make_data_client()
        instrument_id = InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        data_client._market_data_stream = None  # Force polling path

        # Act
        await data_client._subscribe_order_book_snapshot(instrument_id)
        # Assert - Polling subscribe_order_book was called
        mock_client.subscribe_order_book.assert_called_once()
        call_args = mock_client.subscribe_order_book.call_args
        assert call_args.kwargs["figi"] == "BBG004730N88"
        assert call_args.kwargs["depth"] == 10

    @pytest.mark.asyncio
    async def test_unsubscribe_order_book_snapshot_polling_path(self):
        # Arrange
        data_client, mock_client, _ = self._make_data_client()
        instrument_id = InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        data_client._market_data_stream = None

        # Act
        await data_client._unsubscribe_order_book_snapshot(instrument_id)
        # Assert
        mock_client.unsubscribe_order_book.assert_called_once_with(
            "BBG004730N88", depth=10,
        )

    @pytest.mark.asyncio
    async def test_subscribe_quote_ticks_polling_path(self):
        # Arrange
        data_client, mock_client, _ = self._make_data_client()
        instrument_id = InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        data_client._market_data_stream = None

        # Act
        await data_client._subscribe_quote_ticks(instrument_id)
        # Assert
        mock_client.subscribe_order_book.assert_called_once()
        call_args = mock_client.subscribe_order_book.call_args
        assert call_args.kwargs["figi"] == "BBG004730N88"
        assert call_args.kwargs["depth"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_trade_ticks_polling_path(self):
        # Arrange
        data_client, mock_client, _ = self._make_data_client()
        instrument_id = InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        data_client._market_data_stream = None

        # Act
        await data_client._subscribe_trade_ticks(instrument_id)
        # Assert
        mock_client.subscribe_trades.assert_called_once()
        call_args = mock_client.subscribe_trades.call_args
        assert call_args.kwargs["figi"] == "BBG004730N88"

    @pytest.mark.asyncio
    async def test_unsubscribe_trade_ticks_polling_path(self):
        # Arrange
        data_client, mock_client, _ = self._make_data_client()
        instrument_id = InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        data_client._market_data_stream = None

        # Act
        await data_client._unsubscribe_trade_ticks(instrument_id)
        # Assert
        mock_client.unsubscribe_trades.assert_called_once_with("BBG004730N88")
