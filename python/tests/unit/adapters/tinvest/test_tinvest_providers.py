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

from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.tinvest.providers import (
    TInvestInstrumentProvider,
    _compute_price_precision,
    _INSTRUMENT_TYPE_TO_ASSET_CLASS,
    _try_dict_to_instrument,
)
from nautilus_trader.common.component import TestClock
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Price


class TestComputePricePrecision:
    def test_none_input_returns_default(self):
        # Arrange, Act
        precision, increment = _compute_price_precision(None)
        # Assert
        assert precision == 2
        assert increment == Price.from_str("0.01")

    def test_empty_dict_returns_default(self):
        # Arrange, Act
        precision, increment = _compute_price_precision({})
        # Assert
        assert precision == 2
        assert increment == Price.from_str("0.01")

    def test_zero_units_zero_nano_returns_default(self):
        # Arrange
        min_inc = {"units": 0, "nano": 0}
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 2
        assert increment == Price.from_str("0.01")

    def test_negative_value_returns_default(self):
        # Arrange
        min_inc = {"units": -1, "nano": 0}
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 2
        assert increment == Price.from_str("0.01")

    def test_one_unit_zero_nano_precision_0(self):
        """min_price_increment = 1.0 → precision 0, increment 1.0"""
        # Arrange
        min_inc = {"units": 1, "nano": 0}
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 0
        assert increment == Price(1.0, 0)

    def test_ten_units_precision_0(self):
        """min_price_increment = 10.0 → precision 0"""
        # Arrange
        min_inc = {"units": 10, "nano": 0}
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 0
        assert increment == Price(10.0, 0)

    def test_one_hundredth_precision_2(self):
        """min_price_increment = 0.01 → precision 2"""
        # Arrange
        min_inc = {"units": 0, "nano": 10_000_000}  # 0.01 = 10_000_000 nano
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 2

    def test_one_thousandth_precision_3(self):
        """min_price_increment = 0.001 → precision 3"""
        # Arrange
        min_inc = {"units": 0, "nano": 1_000_000}  # 0.001 = 1_000_000 nano
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 3

    def test_one_ten_thousandth_precision_4(self):
        """min_price_increment = 0.0001 → precision 4"""
        # Arrange
        min_inc = {"units": 0, "nano": 100_000}  # 0.0001 = 100_000 nano
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 4

    def test_one_millionth_precision_6(self):
        """min_price_increment = 0.000001 → precision 6"""
        # Arrange
        min_inc = {"units": 0, "nano": 1_000}  # 0.000001 = 1000 nano
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 6

    def test_one_billionth_precision_9(self):
        """min_price_increment = 0.000000001 → precision 9"""
        # Arrange
        min_inc = {"units": 0, "nano": 1}  # 0.000000001 = 1 nano
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 9

    def test_non_dict_input_returns_default(self):
        """When min_price_increment is a string (e.g. proto fallback)."""
        # Arrange, Act
        precision, increment = _compute_price_precision("not a dict")  # type: ignore
        # Assert
        assert precision == 2
        assert increment == Price.from_str("0.01")

    def test_units_only_nano_zero(self):
        """min_price_increment = 5 units, 0 nano → precision 0"""
        # Arrange
        min_inc = {"units": 5, "nano": 0}
        # Act
        precision, increment = _compute_price_precision(min_inc)
        # Assert
        assert precision == 0


class TestInstrumentTypeMapping:
    def test_share_maps_to_equity(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["share"] == AssetClass.EQUITY

    def test_bond_maps_to_debt(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["bond"] == AssetClass.DEBT

    def test_etf_maps_to_equity(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["etf"] == AssetClass.EQUITY

    def test_future_maps_to_index(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["future"] == AssetClass.INDEX

    def test_option_maps_to_equity(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["option"] == AssetClass.EQUITY

    def test_currency_maps_to_fx(self):
        assert _INSTRUMENT_TYPE_TO_ASSET_CLASS["currency"] == AssetClass.FX


class TestTryDictToInstrument:
    def test_no_figi_returns_none(self):
        # Arrange
        inst = {"ticker": "SBER", "instrument_type": "share"}
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is None

    def test_share_conversion(self):
        # Arrange
        inst = {
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "instrument_type": "share",
            "lot": 10,
            "currency": "RUB",
            "isin": "RU0009029540",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},  # 0.01
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.id == InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        assert result.raw_symbol == Symbol("SBER")
        assert result.price_precision == 2
        assert result.price_increment == Price(0.01, 2)
        assert result.lot_size.as_double() == 10.0
        assert result.isin == "RU0009029540"

    def test_etf_conversion(self):
        # Arrange
        inst = {
            "figi": "BBG000000001",
            "ticker": "FXGD",
            "instrument_type": "etf",
            "lot": 1,
            "currency": "RUB",
            "isin": "",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.raw_symbol == Symbol("FXGD")

    def test_bond_conversion(self):
        # Arrange
        inst = {
            "figi": "BBG000000002",
            "ticker": "SU26222RMFS8",
            "instrument_type": "bond",
            "lot": 1,
            "currency": "RUB",
            "isin": "RU000A0JXR79",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.raw_symbol == Symbol("SU26222RMFS8")

    def test_future_conversion(self):
        # Arrange
        inst = {
            "figi": "FUTSI032F0",
            "ticker": "SIU5",
            "instrument_type": "future",
            "lot": 1,
            "currency": "RUB",
            "isin": "",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.raw_symbol == Symbol("SIU5")

    def test_currency_conversion(self):
        # Arrange
        inst = {
            "figi": "BBG0013HGFT4",
            "ticker": "USD000UTSTOM",
            "instrument_type": "currency",
            "lot": 1000,
            "currency": "RUB",
            "isin": "",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.raw_symbol == Symbol("USD000UTSTOM")

    def test_option_conversion_call(self):
        # Arrange
        inst = {
            "figi": "OPT12345CALL0",
            "ticker": "SBER-250",
            "instrument_type": "option",
            "lot": 10,
            "currency": "RUB",
            "isin": "",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
            "direction": 2,  # CALL
            "strike_price": {"units": 250, "nano": 0},
            "basic_asset_size": {"units": 1, "nano": 0},
            "basic_asset": "SBER",
            "expiration_date": 1735689600,
            "first_trade_date": 1704067200,
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        from nautilus_trader.model.enums import OptionKind

        assert result.option_kind == OptionKind.CALL
        assert result.strike_price == Price(250.0, 2)
        assert result.underlying == Symbol("SBER")
        assert result.expiration_ns == 1735689600 * 1_000_000_000
        assert result.activation_ns == 1704067200 * 1_000_000_000

    def test_option_conversion_put(self):
        # Arrange
        inst = {
            "figi": "OPT12345PUT0",
            "ticker": "SBER-240",
            "instrument_type": "option",
            "lot": 10,
            "currency": "RUB",
            "isin": "",
            "exchange": "MOEX",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
            "direction": 1,  # PUT
            "strike_price": {"units": 240, "nano": 0},
            "basic_asset_size": {"units": 1, "nano": 0},
            "basic_asset": "SBER",
            "expiration_date": 1735689600,
            "first_trade_date": 1704067200,
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        from nautilus_trader.model.enums import OptionKind

        assert result.option_kind == OptionKind.PUT

    def test_unknown_type_falls_back_to_equity(self):
        # Arrange
        inst = {
            "figi": "UNKNOWN123",
            "ticker": "WEIRD",
            "instrument_type": "weird_type",
            "lot": 1,
            "currency": "RUB",
            "min_price_increment": {"units": 1, "nano": 0},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        # Falls back to Equity for unknown types

    def test_missing_ticker_uses_figi(self):
        # Arrange
        inst = {
            "figi": "BBG004730N88",
            "instrument_type": "share",
            "lot": 10,
            "currency": "RUB",
            "min_price_increment": {"units": 0, "nano": 10_000_000},
        }
        # Act
        result = _try_dict_to_instrument(inst)
        # Assert
        assert result is not None
        assert result.raw_symbol == Symbol("BBG004730N88")


class TestTInvestInstrumentProvider:
    def test_not_loaded_initially(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        # Act, Assert
        assert provider.is_loaded is False
        assert provider.count == 0

    def test_add_and_get_instrument(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        instrument = MagicMock()
        instrument_id = InstrumentId(Symbol("SBER"), Venue("TINVEST"))
        instrument.id = instrument_id
        # Act
        provider.add_instrument(str(instrument_id), instrument)
        # Assert
        assert provider.count == 1
        assert provider.get_instrument(str(instrument_id)) is instrument

    def test_get_missing_returns_none(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        instrument_id = InstrumentId(Symbol("NONEXISTENT"), Venue("TINVEST"))
        # Act
        result = provider.get_instrument(str(instrument_id))
        # Assert
        assert result is None

    def test_get_instruments_returns_dict(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        instrument = MagicMock()
        instrument_id = InstrumentId(Symbol("SBER"), Venue("TINVEST"))
        instrument.id = instrument_id
        provider.add_instrument(str(instrument_id), instrument)
        # Act
        result = provider.get_instruments()
        # Assert
        assert isinstance(result, dict)
        assert str(instrument_id) in result

    @pytest.mark.asyncio
    async def test_load_all_sets_loaded(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        # Act
        await provider.load_all()
        # Assert - loads successfully even without grpc_client (graceful no-op)
        assert provider.is_loaded is True

    @pytest.mark.asyncio
    async def test_load_all_is_idempotent(self):
        # Arrange
        clock = TestClock()
        provider = TInvestInstrumentProvider(clock=clock)
        # Act
        await provider.load_all()
        await provider.load_all()  # Second call should not raise
        # Assert
        assert provider.is_loaded is True
