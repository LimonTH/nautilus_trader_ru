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
from typing import Any

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Money

# Native gRPC execution streaming (PyO3)
try:
    from nautilus_trader.core.nautilus_pyo3.tinvest import (
        TInvestOrderStateStream,
        TInvestPortfolioStream,
        TInvestPositionsStream,
    )

    _HAS_NATIVE_STREAMS = True
except ImportError:
    TInvestOrderStateStream = None  # type: ignore
    TInvestPortfolioStream = None  # type: ignore
    TInvestPositionsStream = None  # type: ignore
    _HAS_NATIVE_STREAMS = False
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import CancelAllOrders
from nautilus_trader.execution.messages import CancelOrder
from nautilus_trader.execution.messages import ModifyOrder
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.execution.messages import SubmitOrderList
from nautilus_trader.execution.reports import ExecutionMassStatus
from nautilus_trader.execution.reports import FillReport
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import LiquiditySide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.objects import Quantity as ModelQuantity
from nautilus_trader.model.objects import Price as ModelPrice
from nautilus_trader.model.objects import Money as ModelMoney


# Map T-Invest direction to nautilus OrderSide
_TINVEST_DIRECTION_TO_SIDE = {
    1: OrderSide.BUY,
    2: OrderSide.SELL,
}

# Map T-Invest execution_report_status to nautilus OrderStatus
_TINVEST_STATUS_TO_ORDER_STATUS = {
    0: OrderStatus.INITIALIZED,
    1: OrderStatus.FILLED,
    2: OrderStatus.REJECTED,
    3: OrderStatus.CANCELED,
    4: OrderStatus.ACCEPTED,
    5: OrderStatus.PARTIALLY_FILLED,
    6: OrderStatus.PENDING_CANCEL,
    7: OrderStatus.EXPIRED,
}

# Map T-Invest order_type to nautilus OrderType
# ORDER_TYPE_BESTPRICE (3) has no direct Nautilus equivalent; it behaves like
# a market order (aggressive fill at the best available price).
_TINVEST_ORDER_TYPE = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.MARKET,
}

# Nautilus order types that are routed to T-Invest PostStopOrder (F3)
_STOP_ORDER_TYPES = {
    OrderType.STOP_MARKET,
    OrderType.STOP_LIMIT,
    OrderType.MARKET_IF_TOUCHED,
    OrderType.LIMIT_IF_TOUCHED,
}


def _safe_extract_price(raw, default_precision: int = 2) -> "ModelPrice":
    """
    Extract a ``ModelPrice`` from a T-Invest price dict or proto-object.

    Parameters
    ----------
    raw : dict | object | None
        Raw price value, which may be a dict with ``units``/``nano`` keys,
        a proto-object with ``.units``/``.nano`` attributes, or ``None``.
    default_precision : int
        Price precision to use when the value is zero or unavailable.

    Returns
    -------
    ModelPrice
    """
    if raw is None:
        return ModelPrice(0.0, default_precision)

    if isinstance(raw, dict):
        units = float(raw.get("units", 0))
        nano = float(raw.get("nano", 0))
    elif hasattr(raw, 'units'):
        units = float(getattr(raw, 'units', 0))
        nano = float(getattr(raw, 'nano', 0))
    else:
        return ModelPrice(0.0, default_precision)

    return ModelPrice(units + nano * 1e-9, default_precision)


class TInvestExecutionClient(LiveExecutionClient):
    """
    Provides an execution client for the T-Invest (MOEX) API.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    client : TInvestGrpcClient
        The T-Invest gRPC client wrapper.
    account_id : AccountId
        The account ID for the client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : TInvestInstrumentProvider
        The instrument provider.
    config : TInvestExecClientConfig
        The configuration for the client.
    name : str, optional
        The custom client ID.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: TInvestGrpcClient,
        account_id: AccountId,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: TInvestInstrumentProvider,
        config: TInvestExecClientConfig,
        name: str | None,
    ):
        super().__init__(
            loop=loop,
            client_id=ClientId(name or TINVEST_VENUE.value),
            venue=TINVEST_VENUE,
            account_type=1,  # AccountType.CASH
            oms_type=2,  # OmsType.NETTING
            base_currency=Currency.from_str("RUB"),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
        )

        self._client = client
        self._config = config
        self._account_str = str(account_id)
        self._account_id = account_id
        self._instrument_provider = instrument_provider

        # Native gRPC streaming state
        self._order_state_stream = None
        self._portfolio_stream = None
        self._positions_stream = None
        self._native_stream_tasks: list[asyncio.Task] = []

        self._log.info(f"T-Invest ExecutionClient initialized", LogColor.BLUE)
        self._log.info(f"Account: {account_id}", LogColor.BLUE)

    # -- Connection -------------------------------------------------------------------------------

    async def _connect(self) -> None:
        self._log.info("Connecting T-Invest execution client...", LogColor.BLUE)

        # Connect gRPC client
        await self._client.connect()

        # Auto-resolve account_id if not provided or placeholder
        await self._resolve_account_id()

        # Load instruments (like Bybit does)
        await self._instrument_provider.load_all()
        self._cache_instruments()

        # Get account info and register account
        await self._update_account_state()

        # Start native gRPC streaming if available
        if self._client._has_native_streaming() and _HAS_NATIVE_STREAMS:
            native_client = self._client._native
            if native_client is not None:
                await self._start_native_streams(native_client)

        self._log.info("T-Invest execution client connected", LogColor.GREEN)

    async def _disconnect(self) -> None:
        self._log.info("Disconnecting T-Invest execution client...", LogColor.BLUE)

        # Stop native streaming tasks
        await self._stop_native_streams()

        await self._client.disconnect()
        self._log.info("T-Invest execution client disconnected", LogColor.GREEN)

    def _cache_instruments(self) -> None:
        """Cache instruments from provider."""
        for instrument_id, instrument in self._instrument_provider.get_instruments().items():
            self._cache.add_instrument(instrument)

    async def _update_account_state(self) -> None:
        """Get portfolio and positions to generate account state."""
        try:
            # Ensure Cython account_id is set before generating account state
            # (the parent ExecutionClient._set_account_id may have been skipped
            # if the issuer condition check failed in a prior call)
            if self.account_id is None:
                if self._account_id is not None:
                    # Try to set from Python attribute (may still fail if issuer mismatch)
                    try:
                        self._set_account_id(self._account_id)
                    except Exception as ex:
                        self._log.warning(
                            f"Cannot set account_id for account state: {ex}",
                        )
                if self.account_id is None:
                    self._log.warning(
                        "Skipping account state emission: account_id not set",
                    )
                    return

            portfolio = await self._client.get_portfolio(self._account_str)
            if portfolio is not None:
                total_amount = portfolio.get("total_amount_portfolio")
                if total_amount:
                    # Defensive: total_amount may be a dict (PyO3 money_value_to_dict)
                    # or a proto-object when PyO3 conversion falls through.
                    if isinstance(total_amount, dict):
                        currency_raw = total_amount.get("currency", "RUB")
                        if isinstance(currency_raw, dict):
                            currency_str = currency_raw.get("currency", "RUB")
                        elif not isinstance(currency_raw, str):
                            currency_str = str(currency_raw)
                        else:
                            currency_str = currency_raw
                        total_units = int(total_amount.get("units", 0))
                        total_nano = int(total_amount.get("nano", 0))
                    elif hasattr(total_amount, 'currency'):
                        # Proto object (e.g. MoneyValue) – extract attributes directly
                        currency_str = str(total_amount.currency)
                        total_units = int(getattr(total_amount, 'units', 0))
                        total_nano = int(getattr(total_amount, 'nano', 0))
                    else:
                        self._log.warning(
                            f"Unexpected total_amount type: {type(total_amount)}, skipping",
                        )
                        return
                    currency = Currency.from_str(currency_str)
                    total_f64 = float(total_units) + float(total_nano) * 1e-9

                    total_money = ModelMoney(total_f64, currency)
                    free_money = ModelMoney(total_f64, currency)
                    locked_money = ModelMoney(0.0, currency)

                    balances = [
                        AccountBalance(
                            total=total_money,
                            locked=locked_money,
                            free=free_money,
                        ),
                    ]
                    margins = []

                    self.generate_account_state(
                        balances=balances,
                        margins=margins,
                        reported=False,
                        ts_event=self._clock.timestamp_ns(),
                    )
                    self._log.info(
                        f"Account state emitted: {currency}={total_f64}",
                        LogColor.GREEN,
                    )

                positions_data = await self._client.get_positions(self._account_str)
                if positions_data is not None:
                    securities = positions_data.get("securities", [])
                    futures = positions_data.get("futures", [])
                    currencies = positions_data.get("currencies", [])
                    self._log.info(
                        f"Positions: {len(securities)} securities, {len(futures)} futures, "
                        f"{len(currencies)} currencies",
                        LogColor.BLUE,
                    )
        except Exception as e:
            self._log.warning(f"Failed to update account state: {e}")

    # -- Report Generation ------------------------------------------------------------------------

    async def generate_order_status_report(
        self,
        command: object,
    ) -> OrderStatusReport | None:
        try:
            venue_order_id = getattr(command, "venue_order_id", None)
            order_id = str(venue_order_id) if venue_order_id else ""

            if not order_id:
                self._log.warning("No venue_order_id provided for order status report")
                return None

            result = await self._client.get_order_state(self._account_str, order_id)
            if result is None:
                return None

            return self._order_state_to_report(result)
        except Exception as e:
            self._log.warning(f"generate_order_status_report failed: {e}")
            return None

    async def generate_order_status_reports(
        self,
        command: object,
    ) -> list[OrderStatusReport]:
        try:
            results = await self._client.get_orders(self._account_str)
            return [self._order_state_to_report(r) for r in results]
        except Exception as e:
            self._log.warning(f"generate_order_status_reports failed: {e}")
            return []

    async def generate_fill_reports(
        self,
        command: object,
    ) -> list[FillReport]:
        """
        Generate fill reports for the account.

        Uses T-Invest GetOperationsByCursor to retrieve historical fills.
        """
        try:
            from_ts = getattr(command, "from_ts", None)
            to_ts = getattr(command, "to_ts", None)
            instrument_id = getattr(command, "instrument_id", None)

            figi_filter = None
            if instrument_id is not None:
                figi_filter = str(instrument_id.symbol)

            # Get operations from T-Invest API
            result = await self._client.get_operations(
                account_id=self._account_str,
                figi=figi_filter,
                from_ts=from_ts,
                to_ts=to_ts,
            )
            if result is None:
                return []

            reports: list[FillReport] = []
            ts_init = self._clock.timestamp_ns()

            for item in result.get("items", []):
                fills = self._operation_item_to_fill_reports(item, ts_init)
                reports.extend(fills)

            self._log.info(
                f"Generated {len(reports)} fill reports",
                LogColor.BLUE,
            )
            return reports
        except Exception as e:
            self._log.warning(f"generate_fill_reports failed: {e}")
            return []

    async def generate_position_status_reports(
        self,
        command: object,
    ) -> list[PositionStatusReport]:
        try:
            result = await self._client.get_positions(self._account_str)
            if result is None:
                return []

            reports: list[PositionStatusReport] = []
            ts_init = self._clock.timestamp_ns()

            # Securities
            for sec in result.get("securities", []):
                figi = sec.get("figi", "")
                balance = float(sec.get("balance", 0))
                side = PositionSide.LONG if balance > 0 else PositionSide.SHORT if balance < 0 else PositionSide.FLAT

                report = PositionStatusReport(
                    account_id=self._account_id,
                    instrument_id=self._parse_instrument_id(figi),
                    position_side=side,
                    quantity=ModelQuantity(abs(balance), 0),
                    ts_init=ts_init,
                    ts_last=ts_init,
                )
                reports.append(report)

            # Futures
            for fut in result.get("futures", []):
                figi = fut.get("figi", "")
                balance = float(fut.get("balance", 0))
                side = PositionSide.LONG if balance > 0 else PositionSide.SHORT if balance < 0 else PositionSide.FLAT

                report = PositionStatusReport(
                    account_id=self._account_id,
                    instrument_id=self._parse_instrument_id(figi),
                    position_side=side,
                    quantity=ModelQuantity(abs(balance), 0),
                    ts_init=ts_init,
                    ts_last=ts_init,
                )
                reports.append(report)

            return reports
        except Exception as e:
            self._log.warning(f"generate_position_status_reports failed: {e}")
            return []

    async def generate_mass_status(
        self,
        lookback_mins: int | None = None,
    ) -> ExecutionMassStatus | None:
        try:
            # Generate all reports
            order_reports = await self.generate_order_status_reports(None)
            fill_reports = await self.generate_fill_reports(None)
            position_reports = await self.generate_position_status_reports(None)

            ts_init = self._clock.timestamp_ns()
            mass_status = ExecutionMassStatus(
                client_id=self.id,
                account_id=self._account_id,
                venue=TINVEST_VENUE,
                report_id=UUID4(),
                ts_init=ts_init,
            )

            if order_reports:
                mass_status.add_order_reports(order_reports)
            if fill_reports:
                mass_status.add_fill_reports(fill_reports)
            if position_reports:
                mass_status.add_position_reports(position_reports)

            return mass_status
        except Exception as e:
            self._log.warning(f"generate_mass_status failed: {e}")
            return None

    # -- Command Handlers -------------------------------------------------------------------------

    async def _submit_order(self, command: SubmitOrder) -> None:
        figi = str(command.instrument_id.symbol)
        side = command.order.order_side
        qty = command.order.quantity
        order_type = command.order.order_type
        client_order_id = command.client_order_id

        # Map side to T-Invest direction
        direction = 1 if side == OrderSide.BUY else 2

        # F3: stop-orders are routed to T-Invest PostStopOrder
        if order_type in _STOP_ORDER_TYPES:
            await self._submit_stop_order(
                command=command,
                figi=figi,
                direction=direction,
                qty=qty,
            )
            return

        # Map order type to T-Invest type (1=Limit, 2=Market, 3=BestPrice)
        tinvest_type = self._map_order_type(order_type, command.instrument_id)
        price = None
        if order_type == OrderType.LIMIT and command.order.price is not None:
            price = float(command.order.price.as_f64())

        self._log.info(
            f"Submitting order: figi={figi}, side={side}, qty={qty}, "
            f"type={order_type}, tinvest_type={tinvest_type}, "
            f"async={self._config.use_async_orders}",
        )

        try:
            if self._config.use_async_orders:
                # F2: fire-and-forget submission — no blocking wait for the
                # exchange response; order state arrives via stream/polling.
                result = await self._client.post_order_async(
                    account_id=self._account_str,
                    figi=figi,
                    quantity=int(float(qty)),
                    price=price,
                    direction=direction,
                    order_type=tinvest_type,
                    order_id=str(client_order_id),
                )
            else:
                result = await self._client.post_order(
                    account_id=self._account_str,
                    figi=figi,
                    quantity=int(float(qty)),
                    price=price,
                    direction=direction,
                    order_type=tinvest_type,
                    order_id=str(client_order_id),
                )

            if result is not None:
                # Async responses carry order_request_id (idempotency key)
                # instead of a venue order_id until the order is accepted.
                venue_order_id = result.get("order_id", "") or result.get(
                    "order_request_id", "",
                )
                exec_status = result.get("execution_report_status")
                self._log.info(
                    f"Order submitted: venue_order_id={venue_order_id}, "
                    f"status={exec_status}",
                    LogColor.GREEN,
                )

                # Generate event for order submitted
                self.generate_order_submitted(
                    client_order_id=client_order_id,
                    ts_event=self._clock.timestamp_ns(),
                )

                # Generate order accepted
                self.generate_order_accepted(
                    client_order_id=client_order_id,
                    venue_order_id=VenueOrderId(venue_order_id),
                    ts_event=self._clock.timestamp_ns(),
                )

                # If order is already filled (e.g. market order), generate fill
                if exec_status == 1:  # FILLED
                    lots_executed = result.get("lots_executed", 0)
                    self.generate_order_filled(
                        client_order_id=client_order_id,
                        venue_order_id=VenueOrderId(venue_order_id),
                        venue_position_id=None,
                        fill_quantity=ModelQuantity(float(lots_executed), 0),
                        fill_price=_safe_extract_price(result.get("initial_security_price"), 2),
                        ts_event=self._clock.timestamp_ns(),
                    )
            else:
                self._log.warning("Order submission returned no result")
        except Exception as e:
            self._log.error(f"Failed to submit order: {e}")
            self.generate_order_rejected(
                client_order_id=client_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )

    def _map_order_type(self, order_type: OrderType, instrument_id: object) -> int:
        """Map a Nautilus OrderType to a T-Invest order type integer.

        T-Invest order types: 1=Limit, 2=Market, 3=BestPrice.

        Options only support limit orders — any other type is forced to limit
        (F1 validation).

        Returns
        -------
        int
            The T-Invest order type integer.

        """
        # Options: only limit orders are allowed (F1 validation)
        instrument = self._cache.instrument(instrument_id)
        if instrument is not None and self._is_option_instrument(instrument):
            self._log.warning(
                f"Options only support limit orders; forcing LIMIT for {instrument_id}",
            )
            return 1

        if order_type == OrderType.LIMIT:
            return 1
        if order_type == OrderType.MARKET:
            return 3 if self._config.use_bestprice_orders else 2
        # Default to market for unsupported types
        return 2

    @staticmethod
    def _is_option_instrument(instrument: object) -> bool:
        """Return True if the cached instrument is an option contract."""
        from nautilus_trader.model.instruments import OptionContract

        return isinstance(instrument, OptionContract)

    async def _submit_stop_order(
        self,
        command: SubmitOrder,
        figi: str,
        direction: int,
        qty,
    ) -> None:
        """Submit a stop-order via T-Invest PostStopOrder (F3).

        Maps Nautilus stop order types to T-Invest stop-order parameters:

        - ``STOP_MARKET``        → StopLoss (Market child order)
        - ``STOP_LIMIT``         → StopLimit (Limit child order)
        - ``MARKET_IF_TOUCHED``  → TakeProfit (Market child order)
        - ``LIMIT_IF_TOUCHED``   → TakeProfit (Limit child order)

        Emits ``rejected``/``submitted``/``accepted`` events accordingly.

        """
        order = command.order
        order_type = order.order_type
        client_order_id = command.client_order_id

        trigger_price = (
            float(order.trigger_price.as_f64()) if order.trigger_price is not None else None
        )
        limit_price = (
            float(order.price.as_f64()) if order.price is not None else None
        )

        # Map Nautilus stop type → T-Invest (stop_order_type, exchange_order_type)
        if order_type == OrderType.STOP_MARKET:
            stop_order_type = 2  # STOP_LOSS
            exchange_order_type = 1  # MARKET
            price = None
            stop_price = trigger_price
        elif order_type == OrderType.STOP_LIMIT:
            stop_order_type = 3  # STOP_LIMIT
            exchange_order_type = 2  # LIMIT
            price = limit_price
            stop_price = trigger_price
        elif order_type == OrderType.MARKET_IF_TOUCHED:
            stop_order_type = 1  # TAKE_PROFIT
            exchange_order_type = 1  # MARKET
            price = None
            stop_price = trigger_price
        elif order_type == OrderType.LIMIT_IF_TOUCHED:
            stop_order_type = 1  # TAKE_PROFIT
            exchange_order_type = 2  # LIMIT
            price = limit_price
            stop_price = trigger_price
        else:
            self.generate_order_rejected(
                client_order_id=client_order_id,
                reason=f"Unsupported stop order type: {order_type}",
                ts_event=self._clock.timestamp_ns(),
            )
            return

        self._log.info(
            f"Submitting stop-order: figi={figi}, direction={direction}, "
            f"qty={qty}, stop_order_type={stop_order_type}, "
            f"exchange_order_type={exchange_order_type}, trigger={stop_price}",
        )

        try:
            result = await self._client.post_stop_order(
                account_id=self._account_str,
                figi=figi,
                quantity=int(float(qty)),
                order_id=str(client_order_id),
                price=price,
                stop_price=stop_price,
                direction=direction,
                expiration_type=1,  # GOOD_TILL_CANCEL
                stop_order_type=stop_order_type,
                exchange_order_type=exchange_order_type,
                take_profit_type=1 if stop_order_type == 1 else 0,
            )

            if result is not None:
                stop_order_id = result.get("stop_order_id", "")
                self._log.info(
                    f"Stop-order submitted: stop_order_id={stop_order_id}",
                    LogColor.GREEN,
                )

                self.generate_order_submitted(
                    client_order_id=client_order_id,
                    ts_event=self._clock.timestamp_ns(),
                )

                self.generate_order_accepted(
                    client_order_id=client_order_id,
                    venue_order_id=VenueOrderId(stop_order_id),
                    ts_event=self._clock.timestamp_ns(),
                )
            else:
                self._log.warning("Stop-order submission returned no result")
        except Exception as e:
            self._log.error(f"Failed to submit stop-order: {e}")
            self.generate_order_rejected(
                client_order_id=client_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )

    async def _submit_order_list(self, command: SubmitOrderList) -> None:
        self._log.info(
            f"Submitting order list with {len(command.orders)} orders",
        )
        for order in command.orders:
            try:
                await self._submit_order(order)
            except Exception as e:
                self._log.error(f"Failed to submit order in list: {e}")

    async def _modify_order(self, command: ModifyOrder) -> None:
        venue_order_id = str(command.venue_order_id) if command.venue_order_id else "unknown"
        self._log.info(f"Modifying order: venue_order_id={venue_order_id}")

        try:
            # Build idempotency key from client_order_id
            idempotency_key = str(command.client_order_id)

            quantity = int(command.quantity) if command.quantity else 0
            price = float(command.price.as_f64()) if command.price else None

            if quantity <= 0:
                self._log.warning(
                    f"Cannot modify order {venue_order_id}: quantity must be positive",
                )
                return

            result = await self._client.replace_order(
                account_id=self._account_str,
                order_id=venue_order_id,
                idempotency_key=idempotency_key,
                quantity=quantity,
                price=price,
            )

            if result is not None:
                new_order_id = result.get("order_id", "")
                exec_status = result.get("execution_report_status")
                self._log.info(
                    f"Order modified: {venue_order_id} -> {new_order_id}, "
                    f"status={exec_status}",
                    LogColor.GREEN,
                )
                self.generate_order_updated(
                    client_order_id=command.client_order_id,
                    venue_order_id=VenueOrderId(new_order_id),
                    quantity=command.quantity,
                    price=command.price,
                    ts_event=self._clock.timestamp_ns(),
                )
            else:
                self._log.warning(
                    f"Order modification returned no result for {venue_order_id}",
                )
        except Exception as e:
            self._log.error(f"Failed to modify order {venue_order_id}: {e}")

    async def _cancel_order(self, command: CancelOrder) -> None:
        venue_order_id = (
            str(command.venue_order_id)
            if command.venue_order_id
            else str(command.client_order_id)
        )

        self._log.info(f"Cancelling order: venue_order_id={venue_order_id}")

        try:
            result = await self._client.cancel_order(
                account_id=self._account_str,
                order_id=venue_order_id,
            )

            if result is not None and result.get("success"):
                self._log.info(f"Order cancelled: {venue_order_id}", LogColor.GREEN)
                self.generate_order_canceled(
                    client_order_id=command.client_order_id,
                    venue_order_id=VenueOrderId(venue_order_id),
                    ts_event=self._clock.timestamp_ns(),
                )
            else:
                error_msg = (result or {}).get("error", "Unknown error")
                self._log.warning(
                    f"Order cancellation failed: {venue_order_id}: {error_msg}",
                )
                self.generate_order_cancel_rejected(
                    client_order_id=command.client_order_id,
                    venue_order_id=VenueOrderId(venue_order_id),
                    reason=error_msg,
                    ts_event=self._clock.timestamp_ns(),
                )
        except Exception as e:
            self._log.error(f"Failed to cancel order {venue_order_id}: {e}")

    async def _cancel_all_orders(self, command: CancelAllOrders) -> None:
        self._log.info("Cancelling all orders")
        try:
            orders = await self._client.get_orders(self._account_str)
            cancelled_count = 0
            for order in orders:
                order_id = order.get("order_id", "")
                if order_id:
                    try:
                        await self._client.cancel_order(self._account_str, order_id)
                        cancelled_count += 1
                    except Exception as e:
                        self._log.warning(
                            f"Failed to cancel order {order_id}: {e}",
                        )
            self._log.info(
                f"Cancelled {cancelled_count}/{len(orders)} orders",
                LogColor.GREEN,
            )
        except Exception as e:
            self._log.error(f"Failed to cancel all orders: {e}")

    async def _query_account(self, command: object) -> None:
        self._log.info(f"query_account called")
        await self._update_account_state()

    # -- Native Stream Management ------------------------------------------------------------------

    async def _start_native_streams(self, native_client) -> None:
        """Initialize and start native gRPC execution streams."""
        self._log.info("Starting native gRPC execution streams", LogColor.BLUE)

        loop = asyncio.get_running_loop()
        accounts = [self._account_str]

        # Create streams
        self._order_state_stream = TInvestOrderStateStream(native_client, loop)
        self._portfolio_stream = TInvestPortfolioStream(native_client, loop)
        self._positions_stream = TInvestPositionsStream(native_client, loop)

        # Start streams
        self._order_state_stream.start(native_client, accounts)
        self._portfolio_stream.start(native_client, accounts)
        self._positions_stream.start(native_client, accounts)

        # Create background tasks for reading from queues
        self._native_stream_tasks = [
            asyncio.create_task(self._process_order_state_stream()),
            asyncio.create_task(self._process_portfolio_stream()),
            asyncio.create_task(self._process_positions_stream()),
        ]

        self._log.info(
            f"Native gRPC execution streams started for accounts: {accounts}",
            LogColor.GREEN,
        )

    async def _stop_native_streams(self) -> None:
        """Stop native gRPC execution streams and cancel tasks."""
        # Cancel all background tasks
        for task in self._native_stream_tasks:
            if not task.done():
                task.cancel()
        self._native_stream_tasks.clear()

        # Stop streams
        for stream in (
            self._order_state_stream,
            self._portfolio_stream,
            self._positions_stream,
        ):
            if stream is not None:
                try:
                    stream.stop()
                except Exception as e:
                    self._log.warning(f"Error stopping native stream: {e}")

        self._order_state_stream = None
        self._portfolio_stream = None
        self._positions_stream = None

        self._log.info("Native gRPC execution streams stopped", LogColor.GREEN)

    # -- Stream Processing Methods ----------------------------------------------------------------

    async def _process_order_state_stream(self) -> None:
        """Read from OrderStateStream queue and emit OrderStatusReport events."""
        self._log.info("Order state stream processing started", LogColor.BLUE)
        while True:
            try:
                data = await self._order_state_stream.queue.get()
                payload_type = data.get("payload_type", "")

                if payload_type == "order_state":
                    report = self._parse_order_status_report(data)
                    if report is not None:
                        self._send_order_status_report(report)
                elif payload_type == "ping":
                    # Ping - stream health check, no action needed
                    pass
            except asyncio.CancelledError:
                self._log.info("Order state stream processing cancelled")
                break
            except Exception as e:
                self._log.warning(f"Error processing order state stream: {e}")

    async def _process_portfolio_stream(self) -> None:
        """Read from PortfolioStream queue and emit AccountState events."""
        self._log.info("Portfolio stream processing started", LogColor.BLUE)
        while True:
            try:
                data = await self._portfolio_stream.queue.get()
                payload_type = data.get("payload_type", "")

                if payload_type == "portfolio":
                    balances, margins = self._parse_account_balances(data)
                    if balances:
                        self.generate_account_state(
                            balances=balances,
                            margins=margins,
                            reported=False,
                            ts_event=self._clock.timestamp_ns(),
                        )
                elif payload_type == "ping":
                    # Ping - stream health check, no action needed
                    pass
            except asyncio.CancelledError:
                self._log.info("Portfolio stream processing cancelled")
                break
            except Exception as e:
                self._log.warning(f"Error processing portfolio stream: {e}")

    async def _process_positions_stream(self) -> None:
        """Read from PositionsStream queue and emit PositionStatusReport events."""
        self._log.info("Positions stream processing started", LogColor.BLUE)
        while True:
            try:
                data = await self._positions_stream.queue.get()
                payload_type = data.get("payload_type", "")

                if payload_type == "position":
                    reports = self._parse_position_status_reports(data)
                    for report in reports:
                        self._send_position_status_report(report)
                elif payload_type == "initial_positions":
                    # Initial positions snapshot
                    reports = self._parse_position_status_reports(data)
                    for report in reports:
                        self._send_position_status_report(report)
                elif payload_type == "ping":
                    # Ping - stream health check, no action needed
                    pass
            except asyncio.CancelledError:
                self._log.info("Positions stream processing cancelled")
                break
            except Exception as e:
                self._log.warning(f"Error processing positions stream: {e}")

    # -- Stream Data Parsers ----------------------------------------------------------------------

    def _parse_order_status_report(self, data: dict) -> OrderStatusReport | None:
        """Parse order state stream dict to OrderStatusReport."""
        try:
            order_id = data.get("order_id", "")
            direction = data.get("direction", 1)
            order_type_val = data.get("order_type", 2)
            status_val = data.get("execution_report_status", 4)
            ticker = data.get("ticker", "")
            lot_size = data.get("lot_size", 0)

            order_side = _TINVEST_DIRECTION_TO_SIDE.get(direction, OrderSide.BUY)
            order_type = _TINVEST_ORDER_TYPE.get(order_type_val, OrderType.MARKET)
            order_status = _TINVEST_STATUS_TO_ORDER_STATUS.get(status_val, OrderStatus.ACCEPTED)

            # Extract quantity from lot_size (stream field)
            lots_requested = int(lot_size)

            ts_init = self._clock.timestamp_ns()

            # Build instrument_id from ticker
            from nautilus_trader.model.identifiers import InstrumentId, Symbol

            instrument_id = InstrumentId(Symbol(ticker), TINVEST_VENUE)

            return OrderStatusReport(
                account_id=self._account_id,
                instrument_id=instrument_id,
                client_order_id=None,
                venue_order_id=VenueOrderId(order_id),
                order_side=order_side,
                order_type=order_type,
                time_in_force=TimeInForce.GTC,
                order_status=order_status,
                quantity=ModelQuantity(lots_requested, 0),
                filled_qty=ModelQuantity(0, 0),
                ts_init=ts_init,
                ts_last=ts_init,
            )
        except Exception as e:
            self._log.warning(f"Failed to parse order status report: {e}")
            return None

    def _parse_account_balances(
        self,
        data: dict,
    ) -> tuple[list[dict], list[dict]]:
        """Parse portfolio stream dict to balances and margins lists.

        Returns
        -------
        tuple[list[dict], list[dict]]
            (balances, margins) suitable for ``generate_account_state()``.

        """
        balances: list[dict] = []
        margins: list[dict] = []

        try:
            total_amount = data.get("total_amount_portfolio")
            if total_amount is None:
                return balances, margins

            if isinstance(total_amount, dict):
                currency_str = total_amount.get("currency", "RUB")
                if isinstance(currency_str, dict):
                    currency_str = currency_str.get("currency", "RUB")
                total_units = int(total_amount.get("units", 0))
                total_nano = int(total_amount.get("nano", 0))
            elif hasattr(total_amount, 'currency'):
                currency_str = str(total_amount.currency)
                total_units = int(getattr(total_amount, 'units', 0))
                total_nano = int(getattr(total_amount, 'nano', 0))
            else:
                return balances, margins

            currency = Currency.from_str(currency_str)
            total_f64 = float(total_units) + float(total_nano) * 1e-9

            total_money = Money(total_f64, currency)
            free_money = Money(total_f64, currency)
            locked_money = Money(0.0, currency)

            balances = [
                AccountBalance(
                    total=total_money,
                    locked=locked_money,
                    free=free_money,
                ),
            ]
        except Exception as e:
            self._log.warning(f"Failed to parse account balances from stream: {e}")

        return balances, margins

    def _parse_position_status_reports(self, data: dict) -> list[PositionStatusReport]:
        """Parse positions stream dict to PositionStatusReport list.

        Note: The current PyO3 positions stream converter only passes counts
        (money_count, securities_count, etc.) rather than full position details.
        This parser handles the available data and returns an empty list
        when full position data is not yet available.

        """
        try:
            # The current native stream converter only sends metadata counts
            # Full position parsing will be implemented when the Rust converter
            # is extended to include detailed position arrays.
            payload_type = data.get("payload_type", "")

            if payload_type in ("position", "initial_positions"):
                self._log.debug(
                    f"Positions stream update: "
                    f"money={data.get('money_count', 0)}, "
                    f"securities={data.get('securities_count', 0)}, "
                    f"futures={data.get('futures_count', 0)}, "
                    f"options={data.get('options_count', 0)}",
                )
                # For now, positions stream provides metadata only.
                # Full position data requires extended Rust converter.
                # Trigger a full position refresh via polling as fallback.
                asyncio.create_task(self._update_account_state())
        except Exception as e:
            self._log.warning(f"Failed to parse position status reports: {e}")

        return []

    # -- Helpers ----------------------------------------------------------------------------------

    def _order_state_to_report(self, state: dict) -> OrderStatusReport:
        """Convert T-Invest order state dict to nautilus OrderStatusReport."""
        figi = state.get("figi", "")
        direction = state.get("direction", 1)
        order_type_val = state.get("order_type", 2)
        status_val = state.get("execution_report_status", 4)

        order_side = _TINVEST_DIRECTION_TO_SIDE.get(direction, OrderSide.BUY)
        order_type = _TINVEST_ORDER_TYPE.get(order_type_val, OrderType.MARKET)
        order_status = _TINVEST_STATUS_TO_ORDER_STATUS.get(status_val, OrderStatus.ACCEPTED)

        lots_requested = state.get("lots_requested", 0)
        lots_executed = state.get("lots_executed", 0)
        order_id = state.get("order_id", "")

        ts_init = self._clock.timestamp_ns()

        return OrderStatusReport(
            account_id=self._account_id,
            instrument_id=self._parse_instrument_id(figi),
            client_order_id=None,
            venue_order_id=VenueOrderId(order_id),
            order_side=order_side,
            order_type=order_type,
            time_in_force=TimeInForce.GTC,
            order_status=order_status,
            quantity=ModelQuantity(lots_requested, 0),
            filled_qty=ModelQuantity(lots_executed, 0),
            ts_init=ts_init,
            ts_last=ts_init,
        )

    def _operation_item_to_fill_reports(
        self,
        item: dict,
        ts_init: int,
    ) -> list[FillReport]:
        """Convert an operation item dict to fill reports."""
        reports: list[FillReport] = []

        figi = item.get("figi", "")
        op_id = item.get("id", "")
        quantity = float(item.get("quantity", 0))
        price_data = item.get("price", {})
        payment_data = item.get("payment", {})

        if not figi or not op_id:
            return reports

        # Skip zero-quantity operations (not a fill)
        if quantity <= 0:
            self._log.debug(f"Skipping operation {op_id} with zero quantity")
            return reports

        # Also check trades_info for any zero-quantity trades
        trades_info = item.get("trades_info", {})
        if trades_info:
            trades = trades_info.get("trades", [])
            if trades:
                # Filter out zero-quantity trades
                valid_trades = [t for t in trades if float(t.get("quantity", 0)) > 0]
                if not valid_trades:
                    self._log.debug(f"Skipping operation {op_id}: no trades with positive quantity")
                    return reports

        # Determine side from payment (positive = buy, negative = sell)
        payment_units = payment_data.get("units", 0) if isinstance(payment_data, dict) else 0
        order_side = OrderSide.BUY if payment_units >= 0 else OrderSide.SELL

        # Price (defensive against dict and proto-object)
        fill_price = _safe_extract_price(price_data, 2)

        # Commission (defensive against dict and proto-object)
        commission_data = item.get("commission", {})
        if isinstance(commission_data, dict):
            comm_units = float(commission_data.get("units", 0))
            comm_nano = float(commission_data.get("nano", 0))
            comm_currency_str = commission_data.get("currency", "RUB")
            commission = ModelMoney(
                comm_units + comm_nano * 1e-9,
                Currency.from_str(comm_currency_str),
            )
        elif hasattr(commission_data, 'units'):
            comm_units = float(getattr(commission_data, 'units', 0))
            comm_nano = float(getattr(commission_data, 'nano', 0))
            comm_currency_str = str(getattr(commission_data, 'currency', 'RUB'))
            commission = ModelMoney(
                comm_units + comm_nano * 1e-9,
                Currency.from_str(comm_currency_str),
            )
        else:
            commission = ModelMoney(0.0, Currency.from_str("RUB"))

        fill_qty = ModelQuantity(quantity, 0)
        trade_id = TradeId(op_id)
        venue_order_id = VenueOrderId(op_id)

        report = FillReport(
            account_id=self._account_id,
            instrument_id=self._parse_instrument_id(figi),
            venue_order_id=venue_order_id,
            trade_id=trade_id,
            order_side=order_side,
            last_qty=fill_qty,
            last_px=fill_price,
            commission=commission,
            liquidity_side=LiquiditySide.TAKER,
            report_id=UUID4(),
            ts_event=ts_init,
            ts_init=ts_init,
        )
        reports.append(report)

        return reports

    async def _resolve_account_id(self) -> None:
        """Auto-resolve account_id from T-Invest API if not set or placeholder."""
        account_id_str = str(self._account_id)
        if account_id_str and account_id_str != "TINVEST-1234567890":
            self._log.info(f"Using configured account_id: {account_id_str}")
            return

        try:
            accounts = await self._client.get_accounts()
            if not accounts:
                self._log.warning("No accounts returned from T-Invest API")
                return

            # Prefer a brokerage account (type=2), otherwise take first
            brokerage = [a for a in accounts if a.get("type") == 2]
            selected = brokerage[0] if brokerage else accounts[0]
            real_id = selected.get("id", "")
            if real_id:
                # AccountId requires 'issuer-identifier' format (e.g. "123456-TINVEST")
                # AccountId format: "ISSUER-IDENTIFIER" where get_issuer() returns ISSUER
                # ClientId is "TINVEST", so AccountId must be "TINVEST-{real_id}"
                qualified_id = AccountId(f"{TINVEST_VENUE.value}-{real_id}")
                self._account_str = real_id
                # Use parent's Cython _set_account_id to update the internal field
                self._set_account_id(qualified_id)
                self._account_id = qualified_id
                self._log.info(
                    f"Auto-resolved account_id: {qualified_id} "
                    f"(type={selected.get('type')}, "
                    f"name={selected.get('name', '')})",
                    LogColor.GREEN,
                )
            else:
                self._log.warning("Account ID is empty in API response")
        except Exception as e:
            self._log.warning(f"Failed to resolve account_id: {e}")

    def _parse_instrument_id(self, figi: str) -> object:
        """Parse FIGI string to InstrumentId."""
        from nautilus_trader.model.identifiers import InstrumentId, Symbol

        return InstrumentId(Symbol(figi), TINVEST_VENUE)
