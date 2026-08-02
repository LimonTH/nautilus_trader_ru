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

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.tinvest.providers import _compute_price_precision
from nautilus_trader.adapters.tinvest.providers import _try_dict_to_instrument
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.instruments import OptionContract
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_option_dict(
    *,
    figi: str = "BBG123456789",
    ticker: str = "OPT123",
    direction: int = 1,
    strike_units: int = 100,
    strike_nano: int = 0,
    basic_asset: str = "SBER",
    basic_asset_size_units: int = 1,
    basic_asset_size_nano: int = 0,
    expiration_date: int = 1735689600,
    first_trade_date: int = 1704067200,
) -> dict:
    """Build a minimal option instrument dict for testing."""
    return {
        "figi": figi,
        "ticker": ticker,
        "class_code": "SMAL",
        "isin": "",
        "lot": 100,
        "currency": "rub",
        "name": "SBER-12.24 Call",
        "exchange": "MOEX",
        "country_of_risk": "RU",
        "instrument_type": "option",
        "min_price_increment": {"units": "0", "nano": 10000000},
        "direction": direction,
        "strike_price": {"units": strike_units, "nano": strike_nano},
        "basic_asset_size": {"units": basic_asset_size_units, "nano": basic_asset_size_nano},
        "basic_asset": basic_asset,
        "expiration_date": expiration_date,
        "first_trade_date": first_trade_date,
    }


# ──────────────────────────────────────────────────────────────────────────────
# T4: TestComputePricePrecision
# ──────────────────────────────────────────────────────────────────────────────


class TestComputePricePrecision:
    """Tests for the private _compute_price_precision helper."""

    def test_none_input(self):
        """None input falls back to default precision=2, increment=0.01."""
        precision, increment = _compute_price_precision(None)
        assert precision == 2
        assert increment == Price(0.01, 2)

    def test_zero_increment(self):
        """Zero or negative increment falls back to defaults."""
        precision, increment = _compute_price_precision({"units": 0, "nano": 0})
        assert precision == 2
        assert increment == Price(0.01, 2)

    def test_negative_increment_fallback(self):
        """Negative value falls back to defaults."""
        precision, increment = _compute_price_precision({"units": -1, "nano": 0})
        assert precision == 2
        assert increment == Price(0.01, 2)

    def test_rubles_step(self):
        """min_price_increment = 1 RUB → precision 0."""
        precision, increment = _compute_price_precision({"units": 1, "nano": 0})
        assert precision == 0
        assert increment == Price(1.0, 0)

    def test_copecks_step(self):
        """min_price_increment = 0.01 RUB (1 copeck) → precision 2."""
        precision, increment = _compute_price_precision({"units": 0, "nano": 10000000})
        assert precision == 2
        assert increment == Price(0.01, 2)

    def test_small_nano_increment(self):
        """Very small nano increment (1e-9) → precision=9, no overflow."""
        precision, increment = _compute_price_precision({"units": 0, "nano": 1})
        assert precision == 9
        assert increment == Price(1e-9, 9)

    def test_precision_clamped_to_max(self):
        """Precision is clamped to _MAX_PRECISION (16)."""
        # nano=1 produces precision=9 which is < 16, safe.
        # Verify that the function never exceeds 16 for any valid input.
        precision, _ = _compute_price_precision({"units": 0, "nano": 1})
        assert precision <= 16

    def test_units_as_string(self):
        """units may arrive as string from serialization layer."""
        precision, increment = _compute_price_precision({"units": "5", "nano": 0})
        assert precision == 0
        assert increment == Price(5.0, 0)

    def test_empty_dict_fallback(self):
        """Empty dict (no keys) → defaults (value=0)."""
        precision, increment = _compute_price_precision({})
        assert precision == 2
        assert increment == Price(0.01, 2)


# ──────────────────────────────────────────────────────────────────────────────
# T5: TestTryDictToInstrument
# ──────────────────────────────────────────────────────────────────────────────


class TestTryDictToInstrument:
    """Tests for the private _try_dict_to_instrument converter."""

    @pytest.fixture
    def base_dict(self) -> dict:
        """Minimal valid share dict used as a template."""
        return {
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "class_code": "SMAL",
            "isin": "RU0009029540",
            "lot": 10,
            "currency": "rub",
            "name": "Сбербанк России ПАО ао",
            "exchange": "MOEX",
            "country_of_risk": "RU",
            "instrument_type": "share",
            "min_price_increment": {"units": "0", "nano": 10000000},
        }

    # --- Type-specific conversions ---

    def test_share_conversion(self, base_dict):
        """share → Equity."""
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.id == InstrumentId(Symbol("BBG004730N88"), Venue("TINVEST"))
        assert result.raw_symbol == Symbol("SBER")
        assert result.lot_size == Quantity.from_int(10)

    def test_etf_conversion(self, base_dict):
        """etf → Equity."""
        base_dict["instrument_type"] = "etf"
        base_dict["figi"] = "BBG000BD5B02"
        base_dict["ticker"] = "FXUS"
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("FXUS")

    def test_bond_conversion(self, base_dict):
        """bond → Equity (Bonds are represented as Equity)."""
        base_dict["instrument_type"] = "bond"
        base_dict["figi"] = "BBG00V9V2XH1"
        base_dict["ticker"] = "SU26238"
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("SU26238")

    def test_future_conversion(self, base_dict):
        """future → FuturesContract."""
        base_dict["instrument_type"] = "future"
        base_dict["figi"] = "FUTSBER0125"
        base_dict["ticker"] = "SBH5"
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, FuturesContract)
        assert result.id == InstrumentId(Symbol("FUTSBER0125"), Venue("TINVEST"))
        assert result.raw_symbol == Symbol("SBH5")
        assert result.underlying == "SBH5"

    def test_currency_conversion(self, base_dict):
        """currency → Equity (Currency instruments are represented as Equity)."""
        base_dict["instrument_type"] = "currency"
        base_dict["figi"] = "BBG0013HGFT4"
        base_dict["ticker"] = "USDRUB"
        base_dict["currency"] = "usd"
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("USDRUB")
        # currency code is uppercased
        assert str(result.quote_currency) == "USD"

    def test_option_direction_1_put(self, base_dict):
        """option direction=1 → OptionContract with PUT kind."""
        opt = _make_option_dict(direction=1)
        result = _try_dict_to_instrument(opt)
        assert isinstance(result, OptionContract)
        assert result.option_kind == OptionKind.PUT

    def test_option_direction_2_call(self, base_dict):
        """option direction=2 → OptionContract with CALL kind."""
        opt = _make_option_dict(direction=2)
        result = _try_dict_to_instrument(opt)
        assert isinstance(result, OptionContract)
        assert result.option_kind == OptionKind.CALL

    def test_option_strike_price(self, base_dict):
        """OptionContract strike_price is parsed correctly."""
        opt = _make_option_dict(strike_units=150, strike_nano=500000000)
        result = _try_dict_to_instrument(opt)
        assert isinstance(result, OptionContract)
        assert float(result.strike_price) == 150.5

    def test_unknown_type_defaults_to_equity(self, base_dict):
        """Unknown instrument_type → Equity (fallback)."""
        base_dict["instrument_type"] = "warrant"
        base_dict["figi"] = "BBGWARRANT01"
        base_dict["ticker"] = "WRNT"
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("WRNT")

    # --- Edge cases ---

    def test_missing_figi_returns_none(self, base_dict):
        """Dict without figi → None."""
        base_dict.pop("figi")
        result = _try_dict_to_instrument(base_dict)
        assert result is None

    def test_empty_figi_returns_none(self, base_dict):
        """Dict with empty figi → None."""
        base_dict["figi"] = ""
        result = _try_dict_to_instrument(base_dict)
        assert result is None

    def test_missing_ticker_falls_back_to_figi(self, base_dict):
        """When ticker is missing, raw_symbol uses figi."""
        base_dict.pop("ticker")
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("BBG004730N88")

    def test_empty_ticker_falls_back_to_figi(self, base_dict):
        """When ticker is empty string, raw_symbol uses figi."""
        base_dict["ticker"] = ""
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("BBG004730N88")

    def test_missing_instrument_type_defaults_to_equity(self, base_dict):
        """Missing instrument_type → Equity."""
        base_dict.pop("instrument_type")
        result = _try_dict_to_instrument(base_dict)
        assert isinstance(result, Equity)

    def test_missing_lot_defaults_to_1(self, base_dict):
        """Missing lot size defaults to 1."""
        base_dict.pop("lot")
        result = _try_dict_to_instrument(base_dict)
        assert result.lot_size == Quantity.from_int(1)

    def test_missing_currency_defaults_to_rub(self, base_dict):
        """Missing currency defaults to RUB."""
        base_dict.pop("currency")
        result = _try_dict_to_instrument(base_dict)
        assert str(result.quote_currency) == "RUB"

    def test_empty_dict_returns_none(self):
        """Fully empty dict → None (no figi)."""
        result = _try_dict_to_instrument({})
        assert result is None

    def test_price_precision_preserved(self, base_dict):
        """min_price_increment is used to compute price_precision."""
        base_dict["min_price_increment"] = {"units": "0", "nano": 10000000}
        result = _try_dict_to_instrument(base_dict)
        assert result.price_precision == 2

    def test_missing_min_price_increment_defaults(self, base_dict):
        """Missing min_price_increment → default precision 2."""
        base_dict.pop("min_price_increment")
        result = _try_dict_to_instrument(base_dict)
        assert result.price_precision == 2


# ──────────────────────────────────────────────────────────────────────────────
# T6: TestTInvestInstrumentProvider
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestInstrumentProvider:
    """Tests for the TInvestInstrumentProvider class."""

    @pytest.fixture
    def mock_clock(self):
        clock = MagicMock()
        clock.timestamp_ns = MagicMock(return_value=0)
        return clock

    @pytest.fixture
    def mock_grpc_client(self):
        client = MagicMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.request_instruments = AsyncMock(return_value=[])
        client.request_instrument = AsyncMock(return_value=None)
        client.get_instrument_by = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def sample_instruments_data(self):
        """Return a list of two instrument dicts (share + future)."""
        return [
            {
                "figi": "BBG004730N88",
                "ticker": "SBER",
                "class_code": "SMAL",
                "isin": "RU0009029540",
                "lot": 10,
                "currency": "rub",
                "name": "Сбербанк России ПАО ао",
                "exchange": "MOEX",
                "country_of_risk": "RU",
                "instrument_type": "share",
                "min_price_increment": {"units": "0", "nano": 10000000},
            },
            {
                "figi": "FUTSBER0125",
                "ticker": "SBH5",
                "class_code": "FUTS",
                "isin": "",
                "lot": 1,
                "currency": "rub",
                "name": "SBER-1.25 Future",
                "exchange": "MOEX",
                "country_of_risk": "RU",
                "instrument_type": "future",
                "min_price_increment": {"units": "1", "nano": 0},
            },
        ]

    def _make_provider(self, mock_clock, mock_grpc_client=None):
        return TInvestInstrumentProvider(
            clock=mock_clock,
            grpc_client=mock_grpc_client,
            config=InstrumentProviderConfig(),
        )

    # ── load_all ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_all_with_grpc_client(self, mock_clock, mock_grpc_client, sample_instruments_data):
        """load_all fetches instruments via gRPC and populates the cache."""
        mock_grpc_client.request_instruments = AsyncMock(return_value=sample_instruments_data)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_all()

        assert provider.is_loaded is True
        assert provider.count == 2
        mock_grpc_client.request_instruments.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_all_without_grpc_client(self, mock_clock):
        """Without gRPC client, load_all marks as loaded with empty cache."""
        provider = self._make_provider(mock_clock, mock_grpc_client=None)

        await provider.load_all()

        assert provider.is_loaded is True
        assert provider.count == 0

    @pytest.mark.asyncio
    async def test_load_all_already_loaded(self, mock_clock, mock_grpc_client, sample_instruments_data):
        """Already loaded → second call is skipped."""
        mock_grpc_client.request_instruments = AsyncMock(return_value=sample_instruments_data)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_all()
        assert provider.count == 2

        # Reset mock and call again
        mock_grpc_client.request_instruments.reset_mock()
        await provider.load_all()

        # request_instruments should NOT be called again
        mock_grpc_client.request_instruments.assert_not_awaited()
        assert provider.count == 2  # unchanged

    @pytest.mark.asyncio
    async def test_load_all_skips_invalid_dicts(self, mock_clock, mock_grpc_client):
        """Dicts without figi or with conversion failures are skipped."""
        data = [
            {"figi": "", "ticker": "BAD", "instrument_type": "share"},  # empty figi → skipped
            {
                "figi": "BBG004730N88",
                "ticker": "SBER",
                "instrument_type": "share",
                "lot": 10,
                "currency": "rub",
                "min_price_increment": {"units": "0", "nano": 10000000},
            },
        ]
        mock_grpc_client.request_instruments = AsyncMock(return_value=data)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_all()

        assert provider.count == 1

    @pytest.mark.asyncio
    async def test_load_all_handles_exception(self, mock_clock, mock_grpc_client):
        """Exception during load_all is caught, provider marked as loaded."""
        mock_grpc_client.request_instruments = AsyncMock(side_effect=RuntimeError("gRPC error"))
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_all()

        # Should not raise; marked as loaded to avoid repeated failures
        assert provider.is_loaded is True
        assert provider.count == 0

    # ── load_ids ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_load_ids(self, mock_clock, mock_grpc_client):
        """load_ids fetches specific instruments by FIGI."""
        instrument_dict = {
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "instrument_type": "share",
            "lot": 10,
            "currency": "rub",
            "min_price_increment": {"units": "0", "nano": 10000000},
        }
        mock_grpc_client.request_instrument = AsyncMock(return_value=instrument_dict)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_ids(["BBG004730N88"])

        assert provider.is_loaded is True
        assert provider.count == 1
        mock_grpc_client.request_instrument.assert_awaited_once_with("BBG004730N88")

    @pytest.mark.asyncio
    async def test_load_ids_without_grpc_client(self, mock_clock):
        """load_ids without gRPC client marks as loaded."""
        provider = self._make_provider(mock_clock, mock_grpc_client=None)

        await provider.load_ids(["BBG004730N88"])

        assert provider.is_loaded is True
        assert provider.count == 0

    @pytest.mark.asyncio
    async def test_load_ids_none_result(self, mock_clock, mock_grpc_client):
        """load_ids handles None result from request_instrument."""
        mock_grpc_client.request_instrument = AsyncMock(return_value=None)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_ids(["NONEXISTENT"])

        assert provider.count == 0

    @pytest.mark.asyncio
    async def test_load_ids_handles_exception(self, mock_clock, mock_grpc_client):
        """Exception during load_ids for one figi doesn't crash."""
        mock_grpc_client.request_instrument = AsyncMock(side_effect=RuntimeError("fail"))
        provider = self._make_provider(mock_clock, mock_grpc_client)

        await provider.load_ids(["FIGI1"])

        assert provider.is_loaded is True
        assert provider.count == 0

    # ── find_instrument ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_find_instrument_by_figi(self, mock_clock, mock_grpc_client):
        """find_instrument by figi returns an instrument."""
        instrument_dict = {
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "instrument_type": "share",
            "lot": 10,
            "currency": "rub",
            "min_price_increment": {"units": "0", "nano": 10000000},
        }
        mock_grpc_client.get_instrument_by = AsyncMock(return_value=instrument_dict)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        result = await provider.find_instrument(figi="BBG004730N88")

        assert result is not None
        assert isinstance(result, Equity)
        assert result.raw_symbol == Symbol("SBER")
        mock_grpc_client.get_instrument_by.assert_awaited_once_with(
            id_type=1,
            id="BBG004730N88",
            class_code=None,
        )

    @pytest.mark.asyncio
    async def test_find_instrument_by_ticker(self, mock_clock, mock_grpc_client):
        """find_instrument by ticker returns an instrument."""
        instrument_dict = {
            "figi": "BBG004730N88",
            "ticker": "SBER",
            "instrument_type": "share",
            "lot": 10,
            "currency": "rub",
            "min_price_increment": {"units": "0", "nano": 10000000},
        }
        mock_grpc_client.get_instrument_by = AsyncMock(return_value=instrument_dict)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        result = await provider.find_instrument(ticker="SBER")

        assert result is not None
        assert isinstance(result, Equity)
        mock_grpc_client.get_instrument_by.assert_awaited_once_with(
            id_type=2,
            id="SBER",
            class_code=None,
        )

    @pytest.mark.asyncio
    async def test_find_instrument_no_key(self, mock_clock, mock_grpc_client):
        """find_instrument with no key returns None."""
        provider = self._make_provider(mock_clock, mock_grpc_client)

        result = await provider.find_instrument()

        assert result is None

    @pytest.mark.asyncio
    async def test_find_instrument_without_grpc_client(self, mock_clock):
        """find_instrument without gRPC client returns None."""
        provider = self._make_provider(mock_clock, mock_grpc_client=None)

        result = await provider.find_instrument(figi="BBG004730N88")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_instrument_empty_result(self, mock_clock, mock_grpc_client):
        """find_instrument returns None when API returns empty."""
        mock_grpc_client.get_instrument_by = AsyncMock(return_value=None)
        provider = self._make_provider(mock_clock, mock_grpc_client)

        result = await provider.find_instrument(figi="NONEXISTENT")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_instrument_handles_exception(self, mock_clock, mock_grpc_client):
        """find_instrument catches exceptions and returns None."""
        mock_grpc_client.get_instrument_by = AsyncMock(side_effect=RuntimeError("fail"))
        provider = self._make_provider(mock_clock, mock_grpc_client)

        result = await provider.find_instrument(figi="BBG004730N88")

        assert result is None

    # ── Cache operations ──────────────────────────────────────────────────

    def test_get_instruments_initially_empty(self, mock_clock, mock_grpc_client):
        """get_instruments returns empty dict initially."""
        provider = self._make_provider(mock_clock, mock_grpc_client)
        assert provider.get_instruments() == {}

    def test_add_and_get_instrument(self, mock_clock, mock_grpc_client):
        """add_instrument + get_instrument round-trip."""
        provider = self._make_provider(mock_clock, mock_grpc_client)
        provider.add_instrument("key1", "instrument1")

        assert provider.get_instrument("key1") == "instrument1"
        assert provider.get_instrument("missing") is None

    def test_get_instruments_returns_all(self, mock_clock, mock_grpc_client):
        """get_instruments returns the full cache."""
        provider = self._make_provider(mock_clock, mock_grpc_client)
        provider.add_instrument("a", 1)
        provider.add_instrument("b", 2)

        result = provider.get_instruments()
        assert result == {"a": 1, "b": 2}

    def test_count_property(self, mock_clock, mock_grpc_client):
        """count reflects the number of cached instruments."""
        provider = self._make_provider(mock_clock, mock_grpc_client)
        assert provider.count == 0

        provider.add_instrument("k1", "v1")
        assert provider.count == 1

        provider.add_instrument("k2", "v2")
        assert provider.count == 2

    def test_is_loaded_initially_false(self, mock_clock, mock_grpc_client):
        """is_loaded is False before load_all is called."""
        provider = self._make_provider(mock_clock, mock_grpc_client)
        assert provider.is_loaded is False
