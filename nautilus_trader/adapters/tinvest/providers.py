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

import logging
import time
from typing import Any

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.constants import _DEFAULT_PRICE_INCREMENT
from nautilus_trader.adapters.tinvest.constants import _DEFAULT_PRICE_PRECISION
from nautilus_trader.adapters.tinvest.constants import _INSTRUMENT_TYPE_TO_ASSET_CLASS
from nautilus_trader.adapters.tinvest.constants import _MAX_PRECISION
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.instruments import OptionContract
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


logger = logging.getLogger(__name__)


def _compute_price_precision(min_price_increment: dict | None) -> tuple[int, Price]:
    """
    Compute ``price_precision`` and ``price_increment`` from a T-Invest Quotation dict.

    Parameters
    ----------
    min_price_increment : dict | None
        Dictionary with ``units`` (int) and ``nano`` (int) keys, or ``None``.

    Returns
    -------
    tuple[int, Price]
        ``(price_precision, price_increment)``.
        Falls back to ``_DEFAULT_PRICE_PRECISION``, ``_DEFAULT_PRICE_INCREMENT``
        when the input is ``None`` or its numeric value is ≤ 0.
        Precision is clamped to ``_MAX_PRECISION`` (16).
    """
    if min_price_increment is None:
        return _DEFAULT_PRICE_PRECISION, _DEFAULT_PRICE_INCREMENT

    units = int(min_price_increment.get("units", 0)) if isinstance(min_price_increment, dict) else 0
    nano = int(min_price_increment.get("nano", 0)) if isinstance(min_price_increment, dict) else 0
    value = float(units) + float(nano) * 1e-9

    if value <= 0:
        return _DEFAULT_PRICE_PRECISION, _DEFAULT_PRICE_INCREMENT

    # Count decimal places in the increment value
    precision = 0
    increment = value
    while increment < 1 and precision < _MAX_PRECISION:
        increment *= 10
        precision += 1

    # If step is an integer (e.g. 1.0), precision = 0
    if value >= 1 and value == int(value):
        precision = 0

    # Safety clamp: never exceed the Rust FIXED_PRECISION limit
    if precision > _MAX_PRECISION:
        logger.warning(
            "Computed price_precision=%d exceeds max (%d), clamping to %d. "
            "min_price_increment={units=%d, nano=%d}, value=%s",
            precision,
            _MAX_PRECISION,
            _MAX_PRECISION,
            units,
            nano,
            value,
        )
        precision = _MAX_PRECISION

    return precision, Price(value, precision)

def _try_dict_to_instrument(inst: dict[str, Any]) -> Instrument | None:
    """
    Convert a T-Invest instrument dict (from PyO3) to a nautilus ``Instrument``.

    Returns ``None`` if the instrument type is unknown or conversion fails.
    """
    figi: str = inst.get("figi", "") or ""
    ticker: str = inst.get("ticker", "") or ""
    instrument_type: str = inst.get("instrument_type", "") or ""
    lot: int = int(inst.get("lot", 1))
    currency_code: str = (inst.get("currency", "") or "rub").upper()
    isin: str = inst.get("isin", "") or ""
    exchange: str = inst.get("exchange", "") or "MOEX"

    if not figi:
        logger.warning("Skipping instrument without figi: %s", inst)
        return None

    now_ns = time.time_ns()
    instrument_id = InstrumentId(Symbol(figi), TINVEST_VENUE)
    raw_symbol = Symbol(ticker or figi)
    currency = Currency.from_str(currency_code)
    lot_size = Quantity.from_int(lot)

    # Compute price precision and increment dynamically from min_price_increment
    min_price_inc = inst.get("min_price_increment")
    price_precision, price_increment = _compute_price_precision(min_price_inc)

    try:
        if instrument_type == "share" or instrument_type == "etf":
            return Equity(
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
                currency=currency,
                price_precision=price_precision,
                price_increment=price_increment,
                lot_size=lot_size,
                isin=isin if isin else None,
                ts_event=now_ns,
                ts_init=now_ns,
                info=inst,
            )

        elif instrument_type == "bond":
            # Nautilus has no BondInstrument; represent as Equity.
            return Equity(
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
                currency=currency,
                price_precision=price_precision,
                price_increment=price_increment,
                lot_size=lot_size,
                isin=isin if isin else None,
                ts_event=now_ns,
                ts_init=now_ns,
                info=inst,
            )

        elif instrument_type == "future":
            return FuturesContract(
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
                asset_class=_INSTRUMENT_TYPE_TO_ASSET_CLASS.get(
                    instrument_type, "INDEX",
                ),
                currency=currency,
                price_precision=price_precision,
                price_increment=price_increment,
                multiplier=Quantity.from_int(1),
                lot_size=lot_size,
                underlying=ticker,
                activation_ns=0,
                expiration_ns=0,
                exchange=exchange,
                ts_event=now_ns,
                ts_init=now_ns,
                info=inst,
            )

        elif instrument_type == "currency":
            # Currency instruments are not traded directly through the exec client;
            # represent as Equity so they can be cached.
            return Equity(
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
                currency=currency,
                price_precision=price_precision,
                price_increment=price_increment,
                lot_size=lot_size,
                isin=None,
                ts_event=now_ns,
                ts_init=now_ns,
                info=inst,
            )

        elif instrument_type == "option":
            return _option_dict_to_contract(
                inst, instrument_id, raw_symbol, currency,
                price_precision, price_increment, lot_size, exchange, now_ns,
            )

        else:
            logger.warning(
                "Unknown instrument_type=%r for figi=%s, treating as Equity",
                instrument_type,
                figi,
            )
            return Equity(
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
                currency=currency,
                price_precision=price_precision,
                price_increment=price_increment,
                lot_size=lot_size,
                isin=isin if isin else None,
                ts_event=now_ns,
                ts_init=now_ns,
                info=inst,
            )

    except Exception as e:
        logger.warning(
            "Failed to convert instrument figi=%s type=%s: %s",
            figi,
            instrument_type,
            e,
        )
        return None


def _option_dict_to_contract(
    inst: dict[str, Any],
    instrument_id: InstrumentId,
    raw_symbol: Symbol,
    currency: Currency,
    price_precision: int,
    price_increment: Price,
    lot_size: Quantity,
    exchange: str,
    now_ns: int,
) -> OptionContract | None:
    """
    Convert an option dict (from a detailed Option proto) to an ``OptionContract``.

    Parameters
    ----------
    inst : dict[str, Any]
        The raw option instrument dict.
    instrument_id : InstrumentId
        The instrument ID.
    raw_symbol : Symbol
        The raw symbol.
    currency : Currency
        The currency.
    price_precision : int
        The price precision.
    price_increment : Price
        The price increment.
    lot_size : Quantity
        The lot size.
    exchange : str
        The exchange name.
    now_ns : int
        Current timestamp in nanoseconds.

    Returns
    -------
    OptionContract or None

    """
    try:
        # --- Option kind from direction ---
        # OptionDirection: OPTION_DIRECTION_PUT = 1, OPTION_DIRECTION_CALL = 2
        direction = int(inst.get("direction", 0))
        if direction == 1:
            option_kind = OptionKind.PUT
        elif direction == 2:
            option_kind = OptionKind.CALL
        else:
            logger.warning(
                "Unknown option direction %r for %s, defaulting to CALL",
                direction,
                instrument_id,
            )
            option_kind = OptionKind.CALL

        # --- Strike price from MoneyValue dict ---
        strike_price_dict = inst.get("strike_price")
        if strike_price_dict is not None and isinstance(strike_price_dict, dict):
            strike_units = float(strike_price_dict.get("units", 0))
            strike_nano = float(strike_price_dict.get("nano", 0))
            strike_value = strike_units + strike_nano * 1e-9
        else:
            strike_value = 0.0
        strike_price = Price(strike_value, price_precision)

        # --- Multiplier from basic_asset_size Quotation ---
        basic_asset_size = inst.get("basic_asset_size")
        if basic_asset_size is not None and isinstance(basic_asset_size, dict):
            bas_units = float(basic_asset_size.get("units", 0))
            bas_nano = float(basic_asset_size.get("nano", 0))
            multiplier_value = bas_units + bas_nano * 1e-9
        else:
            multiplier_value = 1.0
        multiplier = Quantity.from_str(str(multiplier_value))

        # --- Underlying asset ---
        underlying_str = inst.get("basic_asset", "") or raw_symbol.to_string()
        underlying = underlying_str

        # --- Expiration ---
        expiration_seconds = int(inst.get("expiration_date", 0) or 0)
        expiration_ns = expiration_seconds * 1_000_000_000 if expiration_seconds else 0

        # --- Activation ---
        first_trade_seconds = int(inst.get("first_trade_date", 0) or 0)
        activation_ns = first_trade_seconds * 1_000_000_000 if first_trade_seconds else 0

        return OptionContract(
            instrument_id=instrument_id,
            raw_symbol=raw_symbol,
            asset_class=AssetClass.EQUITY,
            exchange=exchange if exchange else None,
            underlying=underlying,
            option_kind=option_kind,
            strike_price=strike_price,
            currency=currency,
            activation_ns=activation_ns,
            expiration_ns=expiration_ns,
            price_precision=price_precision,
            price_increment=price_increment,
            multiplier=multiplier,
            lot_size=lot_size,
            ts_event=now_ns,
            ts_init=now_ns,
            info=inst,
        )
    except Exception as e:
        logger.warning(
            "Failed to convert option dict to OptionContract for %s: %s",
            inst.get("uid", inst.get("figi", "unknown")),
            e,
        )
        return None


class TInvestInstrumentProvider(InstrumentProvider):
    """
    Provides instrument definitions from the T-Invest API.

    Parameters
    ----------
    clock : LiveClock
        The clock for the provider.
    grpc_client : TInvestGrpcClient, optional
        The T-Invest gRPC client for loading instruments.
    config : InstrumentProviderConfig, optional
        The provider configuration.
    """

    def __init__(
        self,
        clock: LiveClock,
        grpc_client: TInvestGrpcClient | None = None,
        config: InstrumentProviderConfig | None = None,
    ):
        self._clock = clock
        self._grpc_client = grpc_client
        self._config = config or InstrumentProviderConfig()
        self._instruments: dict[str, object] = {}
        self._is_loaded = False

    @property
    def count(self) -> int:
        return len(self._instruments)

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    async def load_all(self) -> None:
        """
        Load all instruments from T-Invest API via gRPC.

        Calls the Rust layer's request_instruments() which queries
        Shares, Bonds, Futures, ETFs, and Currencies endpoints.
        Each raw dict is converted to a nautilus ``Instrument`` subclass
        via ``_try_dict_to_instrument``.
        """
        if self._is_loaded:
            logger.info("Instruments already loaded, skipping")
            return

        if self._grpc_client is None:
            logger.warning("No gRPC client available, cannot load instruments")
            self._is_loaded = True
            return

        logger.info("Loading instruments from T-Invest API...")

        try:
            instruments_data = await self._grpc_client.request_instruments()
            logger.info(
                f"Loaded {len(instruments_data)} raw instruments from T-Invest API",
            )

            converted = 0
            skipped = 0
            for inst in instruments_data:
                figi = inst.get("figi", "")
                if not figi:
                    skipped += 1
                    continue

                # Convert dict → nautilus Instrument
                instrument = _try_dict_to_instrument(inst)
                if instrument is None:
                    skipped += 1
                    continue

                instrument_id = str(instrument.id)
                self._instruments[instrument_id] = instrument
                converted += 1

            self._is_loaded = True
            logger.info(
                f"T-Invest instrument provider: "
                f"{converted} converted, {skipped} skipped, "
                f"{len(self._instruments)} total",
            )
        except Exception as e:
            logger.warning(f"Failed to load instruments: {e}")
            self._is_loaded = True  # Mark as loaded to avoid repeated failures

    async def load_ids(self, instrument_ids: list[str]) -> None:
        """
        Load specific instruments by ID.

        Parameters
        ----------
        instrument_ids : list[str]
            List of instrument IDs/FIGIs to load.
        """
        if self._grpc_client is None:
            logger.warning("No gRPC client available, cannot load instruments")
            self._is_loaded = True
            return

        for figi in instrument_ids:
            try:
                result = await self._grpc_client.request_instrument(figi)
                if result is not None:
                    instrument = _try_dict_to_instrument(result)
                    if instrument is not None:
                        instrument_id = str(instrument.id)
                        self._instruments[instrument_id] = instrument
                        logger.info(f"Loaded instrument: {figi}")
                    else:
                        logger.warning(f"Could not convert instrument: {figi}")
                else:
                    logger.warning(f"Instrument not found: {figi}")
            except Exception as e:
                logger.warning(f"Failed to load instrument {figi}: {e}")

        self._is_loaded = True

    def add_instrument(self, instrument_id: str, instrument: object) -> None:
        """Add an instrument to the local cache."""
        self._instruments[instrument_id] = instrument

    def get_instrument(self, instrument_id: str) -> object | None:
        return self._instruments.get(instrument_id)

    def get_instruments(self) -> dict[str, object]:
        return self._instruments

    async def find_instrument(
        self,
        figi: str | None = None,
        ticker: str | None = None,
        instrument_id: str | None = None,
    ) -> object | None:
        """
        Find an instrument by figi, ticker, or instrument_id (F10).

        Uses the T-Invest ``GetInstrumentBy`` endpoint and caches the result.

        Parameters
        ----------
        figi : str, optional
            The instrument FIGI.
        ticker : str, optional
            The instrument ticker.
        instrument_id : str, optional
            The instrument UID / universal identifier.

        Returns
        -------
        object | None
            The nautilus ``Instrument`` or None if not found.

        """
        if self._grpc_client is None:
            logger.warning("No gRPC client available, cannot find instrument")
            return None

        # Determine the lookup key and id_type
        key: str | None = None
        id_type: int | None = None
        if figi:
            key = figi
            id_type = 1  # INSTRUMENT_ID_TYPE_FIGI
        elif instrument_id:
            key = instrument_id
            id_type = 5  # INSTRUMENT_ID_TYPE_ID
        elif ticker:
            key = ticker
            id_type = 2  # INSTRUMENT_ID_TYPE_TICKER

        if not key or id_type is None:
            logger.warning("find_instrument: no figi/ticker/instrument_id provided")
            return None

        try:
            result = await self._grpc_client.get_instrument_by(
                id_type=id_type,
                id=key,
                class_code=None,
            )
            if result is None or not result:
                logger.warning(f"Instrument not found: {key}")
                return None

            instrument = _try_dict_to_instrument(result)
            if instrument is None:
                logger.warning(f"Could not convert instrument: {key}")
                return None

            instrument_id_str = str(instrument.id)
            self._instruments[instrument_id_str] = instrument
            logger.info(f"Found instrument: {instrument_id_str}")
            return instrument
        except Exception as e:
            logger.warning(f"Failed to find instrument {key}: {e}")
            return None
