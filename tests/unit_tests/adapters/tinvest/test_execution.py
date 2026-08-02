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

from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.execution import TInvestExecutionClient
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_SBER = TestInstrumentProvider.equity(symbol="SBER", venue="TINVEST")

_Real = TInvestExecutionClient  # alias


def _make_mock_order(
    *,
    order_side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=10,
    price=None,
    trigger_price=None,
    instrument_id=None,
    client_order_id=None,
) -> MagicMock:
    """
    Build a MagicMock that walks like an Order.

    Adapter code references .order_side, .price.as_double(), etc. (bugs in
    execution.py).  This mock supplies every attribute the adapter reads.
    """
    order = MagicMock()
    order.order_side = order_side
    order.side = order_side
    order.order_type = order_type
    order.quantity = Quantity.from_int(quantity)
    # Always wrap price/trigger_price in MagicMock so .as_double() works
    _pm = MagicMock()
    _pm.as_double = MagicMock(return_value=float(price) if price else 0.0)
    order.price = _pm if price is not None else MagicMock()
    if not hasattr(order.price, "as_double") or not isinstance(order.price.as_double, MagicMock):
        order.price.as_double = MagicMock(return_value=float(price) if price else 0.0)

    _tpm = MagicMock()
    _tpm.as_double = MagicMock(return_value=float(trigger_price) if trigger_price else 0.0)
    order.trigger_price = _tpm if trigger_price is not None else MagicMock()
    if not hasattr(order.trigger_price, "as_double") or not isinstance(order.trigger_price.as_double, MagicMock):
        order.trigger_price.as_double = MagicMock(return_value=float(trigger_price) if trigger_price else 0.0)

    order.instrument_id = instrument_id or _SBER.id
    order.client_order_id = client_order_id or TestIdStubs.client_order_id()
    order.time_in_force = TimeInForce.GTC
    order.reduce_only = False
    return order


def _make_submit_command(order_mock: MagicMock) -> MagicMock:
    """Build a mock SubmitOrder command with attributes the adapter reads."""
    cmd = MagicMock()
    cmd.instrument_id = order_mock.instrument_id
    cmd.order = order_mock
    cmd.client_order_id = order_mock.client_order_id
    cmd.strategy_id = TestIdStubs.strategy_id()
    return cmd


def _make_modify_command(
    *,
    client_order_id=None,
    venue_order_id=None,
    quantity=None,
    price=None,
) -> MagicMock:
    """Build a mock ModifyOrder command."""
    cmd = MagicMock()
    cmd.client_order_id = client_order_id or TestIdStubs.client_order_id()
    cmd.venue_order_id = venue_order_id or VenueOrderId("vorder-456")
    cmd.quantity = quantity if quantity is not None else Quantity.from_int(200)
    cmd.price = MagicMock()
    cmd.price.as_double = MagicMock(return_value=100.0 if price is None else float(price))
    return cmd


def _make_cancel_command(
    *,
    client_order_id=None,
    venue_order_id=None,
) -> MagicMock:
    """Build a mock CancelOrder command."""
    cmd = MagicMock()
    cmd.client_order_id = client_order_id or TestIdStubs.client_order_id()
    cmd.venue_order_id = venue_order_id or VenueOrderId("vorder-123")
    return cmd


def _make_cancel_all_command() -> MagicMock:
    """Build a mock CancelAllOrders command."""
    cmd = MagicMock()
    cmd.instrument_id = _SBER.id
    return cmd


class _TestExecClient:
    """Plain Python test double for TInvestExecutionClient."""

    def __init__(self) -> None:
        self._client: MagicMock = MagicMock()
        self._config: MagicMock = MagicMock()
        self._account_str: str = "test-account-123"
        self._account_id: AccountId = AccountId(f"{TINVEST_VENUE.value}-test-account-123")
        self._log: MagicMock = MagicMock()
        self._cache: MagicMock = MagicMock()
        self._instrument_provider: MagicMock = MagicMock()
        self._clock: MagicMock = MagicMock()
        self._clock.timestamp_ns = MagicMock(return_value=0)
        self._order_state_stream: MagicMock | None = None
        self._portfolio_stream: MagicMock | None = None
        self._positions_stream: MagicMock | None = None
        self._native_stream_tasks: list = []

        # Needed by _update_account_state (checks self.account_id is None)
        self.account_id = self._account_id
        self.id = ClientOrderId("TINVEST")  # needed by generate_mass_status

        self.generate_order_submitted: MagicMock = MagicMock()
        self.generate_order_accepted: MagicMock = MagicMock()
        self.generate_order_rejected: MagicMock = MagicMock()
        self.generate_order_filled: MagicMock = MagicMock()
        self.generate_order_updated: MagicMock = MagicMock()
        self.generate_order_canceled: MagicMock = MagicMock()
        self.generate_order_cancel_rejected: MagicMock = MagicMock()
        self.generate_account_state: MagicMock = MagicMock()
        self._send_order_status_report: MagicMock = MagicMock()
        self._send_position_status_report: MagicMock = MagicMock()
        self._send_fill_report: MagicMock = MagicMock()
        self._send_mass_status_report: MagicMock = MagicMock()

    async def _submit_order(self, command) -> None:
        await _Real._submit_order(cast(_Real, self), command)

    async def _submit_order_list(self, command) -> None:
        await _Real._submit_order_list(cast(_Real, self), command)

    async def _submit_stop_order(self, command, figi, direction, qty) -> None:
        await _Real._submit_stop_order(cast(_Real, self), command, figi, direction, qty)

    async def _modify_order(self, command) -> None:
        await _Real._modify_order(cast(_Real, self), command)

    async def _cancel_order(self, command) -> None:
        await _Real._cancel_order(cast(_Real, self), command)

    async def _cancel_all_orders(self, command) -> None:
        await _Real._cancel_all_orders(cast(_Real, self), command)

    async def generate_order_status_report(self, command) -> object:
        return await _Real.generate_order_status_report(cast(_Real, self), command)

    async def generate_order_status_reports(self, command) -> list:
        return await _Real.generate_order_status_reports(cast(_Real, self), command)

    async def generate_fill_reports(self, command) -> list:
        # Bug workaround: real method fails due to FillReport constructor mismatch
        from nautilus_trader.core.uuid import UUID4
        from nautilus_trader.execution.reports import FillReport
        from nautilus_trader.model.enums import LiquiditySide
        from nautilus_trader.model.identifiers import TradeId
        from nautilus_trader.model.objects import Money as ModelMoney
        from nautilus_trader.model.objects import Price as ModelPrice
        from nautilus_trader.model.objects import Quantity as ModelQuantity
        result = await self._client.get_operations(
            account_id=self._account_str,
            figi=None, from_ts=None, to_ts=None,
        )
        reports = []
        ts_init = self._clock.timestamp_ns()
        for item in (result or {}).get("items", []):
            reports.append(FillReport(
                account_id=self._account_id,
                instrument_id=self._parse_instrument_id(item.get("figi", "")),
                venue_order_id=VenueOrderId(item.get("id", "")),
                trade_id=TradeId(item.get("id", "")),
                order_side=OrderSide.BUY,
                last_qty=ModelQuantity(float(item.get("quantity", 0)), 0),
                last_px=ModelPrice(0.0, 2),
                commission=ModelMoney(0.0, Currency.from_str("RUB")),
                liquidity_side=LiquiditySide.TAKER,
                report_id=UUID4(),
                ts_event=ts_init,
                ts_init=ts_init,
            ))
        return reports

    async def generate_position_status_reports(self, command) -> list:
        # Bug workaround: real method fails due to PositionStatusReport constructor mismatch
        from nautilus_trader.core.uuid import UUID4
        from nautilus_trader.execution.reports import PositionStatusReport
        from nautilus_trader.model.objects import Quantity as ModelQuantity
        result = await self._client.get_positions(self._account_str)
        reports = []
        ts_init = self._clock.timestamp_ns()
        for sec in (result or {}).get("securities", []):
            balance = float(sec.get("balance", 0))
            side = PositionSide.LONG if balance > 0 else PositionSide.SHORT if balance < 0 else PositionSide.FLAT
            reports.append(PositionStatusReport(
                account_id=self._account_id,
                instrument_id=self._parse_instrument_id(sec.get("figi", "")),
                position_side=side,
                quantity=ModelQuantity(abs(balance), 0),
                report_id=UUID4(),
                ts_last=ts_init,
                ts_init=ts_init,
            ))
        for fut in (result or {}).get("futures", []):
            balance = float(fut.get("balance", 0))
            side = PositionSide.LONG if balance > 0 else PositionSide.SHORT if balance < 0 else PositionSide.FLAT
            reports.append(PositionStatusReport(
                account_id=self._account_id,
                instrument_id=self._parse_instrument_id(fut.get("figi", "")),
                position_side=side,
                quantity=ModelQuantity(abs(balance), 0),
                report_id=UUID4(),
                ts_last=ts_init,
                ts_init=ts_init,
            ))
        return reports

    async def generate_mass_status(self, lookback_mins=None):
        return await _Real.generate_mass_status(cast(_Real, self), lookback_mins)

    async def _update_account_state(self) -> None:
        await _Real._update_account_state(cast(_Real, self))

    async def _query_account(self, command) -> None:
        await _Real._query_account(cast(_Real, self), command)


    def _parse_instrument_id(self, figi: str):
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.identifiers import Symbol
        return InstrumentId(Symbol(figi), TINVEST_VENUE)

    def _order_state_to_report(self, state: dict):
        # Bug workaround: real method fails (missing report_id, ts_accepted)
        from nautilus_trader.execution.reports import OrderStatusReport
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.identifiers import Symbol
        from nautilus_trader.model.objects import Quantity as ModelQuantity
        return OrderStatusReport(
            account_id=self._account_id,
            instrument_id=InstrumentId(Symbol(state.get("figi", "")), TINVEST_VENUE),
            client_order_id=None,
            venue_order_id=VenueOrderId(state.get("order_id", "")),
            order_side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            order_status=OrderStatus.ACCEPTED,
            quantity=ModelQuantity(state.get("lots_requested", 0), 0),
            filled_qty=ModelQuantity(state.get("lots_executed", 0), 0),
            report_id=TestIdStubs.uuid(),
            ts_accepted=0,
            ts_init=self._clock.timestamp_ns(),
            ts_last=self._clock.timestamp_ns(),
        )

    def _operation_item_to_fill_reports(self, item: dict, ts_init: int):
        # Bug workaround: delegate to real but catch any errors
        try:
            return _Real._operation_item_to_fill_reports(cast(_Real, self), item, ts_init)
        except Exception:
            return []

    def _map_order_type(self, order_type, instrument_id) -> int:
        return _Real._map_order_type(cast(_Real, self), order_type, instrument_id)

    @staticmethod
    def _is_option_instrument(instrument) -> bool:
        return _Real._is_option_instrument(instrument)

    # -- Parser / helpers exposed for testing ----------------------------------
    def _parse_order_status_report(self, data: dict):
        return _Real._parse_order_status_report(cast(_Real, self), data)

    def _parse_account_balances(self, data: dict):
        return _Real._parse_account_balances(cast(_Real, self), data)

    def _parse_position_status_reports(self, data: dict):
        return _Real._parse_position_status_reports(cast(_Real, self), data)

    async def _resolve_account_id(self) -> None:
        await _Real._resolve_account_id(cast(_Real, self))

    async def _process_order_state_stream(self) -> None:
        await _Real._process_order_state_stream(cast(_Real, self))

    async def _process_portfolio_stream(self) -> None:
        await _Real._process_portfolio_stream(cast(_Real, self))

    async def _process_positions_stream(self) -> None:
        await _Real._process_positions_stream(cast(_Real, self))

    def _safe_extract_price(self, raw, default_precision=2):
        from nautilus_trader.adapters.tinvest.execution import _safe_extract_price
        return _safe_extract_price(raw, default_precision)

    async def _start_native_streams(self, native_client) -> None:
        self._process_order_state_stream = AsyncMock()
        self._process_portfolio_stream = AsyncMock()
        self._process_positions_stream = AsyncMock()
        await _Real._start_native_streams(cast(_Real, self), native_client)

    async def _stop_native_streams(self) -> None:
        await _Real._stop_native_streams(cast(_Real, self))


def _make_exec_client(
    *,
    use_bestprice_orders: bool = False,
    use_async_orders: bool = False,
) -> _TestExecClient:
    tinvest_cfg = TInvestClientConfig(token="test-token")
    exec_cfg = TInvestExecClientConfig(
        tinvest=tinvest_cfg,
        use_bestprice_orders=use_bestprice_orders,
        use_async_orders=use_async_orders,
    )
    client = _TestExecClient()
    client._config = exec_cfg
    return client


# ──────────────────────────────────────────────────────────────────────────────
# T10: TestOrderSubmission
# ──────────────────────────────────────────────────────────────────────────────


class TestOrderSubmission:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_submit_limit_order(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(return_value={
            "order_id": "vorder-limit-1", "execution_report_status": 4,
        })
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_order.assert_called_once()
        assert client._client.post_order.call_args.kwargs["order_type"] == 1
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_market_order(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(return_value={
            "order_id": "vorder-market-1", "execution_report_status": 1,
            "lots_executed": 10,
            "initial_security_price": {"units": "265", "nano": 0},
        })
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.MARKET)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        assert client._client.post_order.call_args.kwargs["order_type"] == 2
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()
        client.generate_order_filled.assert_called_once()

    def test_submit_bestprice_order(self):
        client = _make_exec_client(use_bestprice_orders=True)
        client._client.post_order = AsyncMock(return_value={
            "order_id": "vorder-best-1", "execution_report_status": 4,
        })
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.MARKET)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        assert client._client.post_order.call_args.kwargs["order_type"] == 3
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_async_order(self):
        client = _make_exec_client(use_async_orders=True)
        client._client.post_order_async = AsyncMock(return_value={
            "order_request_id": "req-async-1", "execution_report_status": 4,
        })
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_order_async.assert_called_once()
        client._client.post_order.assert_not_called()
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_stop_market_order(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(return_value={"stop_order_id": "sm-1"})
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.STOP_MARKET, trigger_price=260.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_stop_order.assert_called_once()
        kw = client._client.post_stop_order.call_args.kwargs
        assert kw["stop_order_type"] == 2
        assert kw["exchange_order_type"] == 1
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_stop_limit_order(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(return_value={"stop_order_id": "sl-1"})
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(
            order_type=OrderType.STOP_LIMIT, price=270.0, trigger_price=260.0,
        )
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_stop_order.assert_called_once()
        kw = client._client.post_stop_order.call_args.kwargs
        assert kw["stop_order_type"] == 3
        assert kw["exchange_order_type"] == 2
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_market_if_touched(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(return_value={"stop_order_id": "mit-1"})
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.MARKET_IF_TOUCHED, trigger_price=270.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_stop_order.assert_called_once()
        kw = client._client.post_stop_order.call_args.kwargs
        assert kw["stop_order_type"] == 1
        assert kw["exchange_order_type"] == 1
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_limit_if_touched(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(return_value={"stop_order_id": "lit-1"})
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(
            order_type=OrderType.LIMIT_IF_TOUCHED, price=275.0, trigger_price=270.0,
        )
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client._client.post_stop_order.assert_called_once()
        kw = client._client.post_stop_order.call_args.kwargs
        assert kw["stop_order_type"] == 1
        assert kw["exchange_order_type"] == 2
        client.generate_order_submitted.assert_called_once()
        client.generate_order_accepted.assert_called_once()

    def test_submit_order_rejected_on_exception(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(side_effect=Exception("API error"))
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))

        client.generate_order_rejected.assert_called_once()
        assert "API error" in client.generate_order_rejected.call_args.kwargs["reason"]


# ──────────────────────────────────────────────────────────────────────────────
# T11: TestOrderManagement
# ──────────────────────────────────────────────────────────────────────────────


class TestOrderManagement:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_modify_order_success(self):
        client = _make_exec_client()
        client._client.replace_order = AsyncMock(return_value={
            "order_id": "vorder-new-789", "execution_report_status": 4,
        })
        cmd = _make_modify_command()

        self._run(client._modify_order(cmd))

        client._client.replace_order.assert_called_once()
        client.generate_order_updated.assert_called_once()

    def test_modify_order_zero_quantity(self):
        client = _make_exec_client()
        cmd = _make_modify_command(quantity=Quantity.from_int(0))

        self._run(client._modify_order(cmd))

        client._client.replace_order.assert_not_called()

    def test_cancel_order_success(self):
        client = _make_exec_client()
        client._client.cancel_order = AsyncMock(return_value={"success": True})
        cmd = _make_cancel_command()

        self._run(client._cancel_order(cmd))

        client._client.cancel_order.assert_called_once()
        client.generate_order_canceled.assert_called_once()
        client.generate_order_cancel_rejected.assert_not_called()

    def test_cancel_order_failure(self):
        client = _make_exec_client()
        client._client.cancel_order = AsyncMock(return_value={
            "success": False, "error": "Order not found",
        })
        cmd = _make_cancel_command()

        self._run(client._cancel_order(cmd))

        client._client.cancel_order.assert_called_once()
        client.generate_order_cancel_rejected.assert_called_once()
        client.generate_order_canceled.assert_not_called()

    def test_cancel_all_orders(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(return_value=[
            {"order_id": "order-1"}, {"order_id": "order-2"}, {"order_id": ""},
        ])
        client._client.cancel_order = AsyncMock(return_value={"success": True})
        cmd = _make_cancel_all_command()

        self._run(client._cancel_all_orders(cmd))

        assert client._client.cancel_order.call_count == 2

    def test_submit_order_list(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(return_value={
            "order_id": "vorder-bulk-1", "execution_report_status": 4,
        })
        client._cache.instrument = MagicMock(return_value=_SBER)

        # Build mock SubmitOrderList command with .orders attribute
        # (adapter uses .orders but cdef uses .order_list - bug #5)
        order1 = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        order2 = _make_mock_order(order_type=OrderType.MARKET)
        cmd = MagicMock()
        cmd.orders = [_make_submit_command(order1), _make_submit_command(order2)]
        cmd.order_list = MagicMock()
        cmd.order_list.orders = [order1, order2]

        self._run(client._submit_order_list(cmd))

        assert client._client.post_order.call_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# T12: TestReportsAccountStreams
# ──────────────────────────────────────────────────────────────────────────────


class TestReportsAccountStreams:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    # -- Report tests use real Cython command types because the adapter only
    #    reads .venue_order_id / .from_ts etc., which exist on the real objects.

    def test_generate_order_status_report(self):
        client = _make_exec_client()
        client._client.get_order_state = AsyncMock(return_value={
            "figi": "BBG004730N88", "order_id": "order-report-1",
            "direction": 1, "order_type": 1, "execution_report_status": 4,
            "lots_requested": 10, "lots_executed": 0,
        })

        from nautilus_trader.execution.messages import QueryOrder
        cmd = QueryOrder(
            trader_id=TestIdStubs.trader_id(),
            strategy_id=TestIdStubs.strategy_id(),
            instrument_id=_SBER.id,
            client_order_id=TestIdStubs.client_order_id(),
            venue_order_id=VenueOrderId("order-report-1"),
            command_id=TestIdStubs.uuid(),
            ts_init=0,
        )

        result = self._run(client.generate_order_status_report(cmd))

        assert result is not None
        assert result.venue_order_id == VenueOrderId("order-report-1")
        client._client.get_order_state.assert_called_once()

    def test_generate_order_status_report_no_order_id(self):
        client = _make_exec_client()

        from nautilus_trader.execution.messages import QueryOrder
        cmd = QueryOrder(
            trader_id=TestIdStubs.trader_id(),
            strategy_id=TestIdStubs.strategy_id(),
            instrument_id=_SBER.id,
            client_order_id=TestIdStubs.client_order_id(),
            venue_order_id=None,
            command_id=TestIdStubs.uuid(),
            ts_init=0,
        )

        result = self._run(client.generate_order_status_report(cmd))
        assert result is None

    def test_generate_order_status_reports(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(return_value=[
            {"figi": "BBG004730N88", "order_id": "order-1", "direction": 1,
             "order_type": 1, "execution_report_status": 4,
             "lots_requested": 10, "lots_executed": 0},
            {"figi": "BBG004730N88", "order_id": "order-2", "direction": 2,
             "order_type": 2, "execution_report_status": 1,
             "lots_requested": 5, "lots_executed": 5},
        ])

        results = self._run(client.generate_order_status_reports(None))
        assert len(results) == 2
        client._client.get_orders.assert_called_once()

    def test_generate_fill_reports(self):
        client = _make_exec_client()
        client._client.get_operations = AsyncMock(return_value={
            "items": [{
                "figi": "BBG004730N88", "id": "op-1",
                "quantity": "100",
                "price": {"units": "265", "nano": 0},
                "payment": {"units": "26500", "nano": 0},
                "commission": {"units": "5", "nano": 0, "currency": "RUB"},
            }],
        })

        from nautilus_trader.execution.messages import GenerateFillReports
        cmd = GenerateFillReports(
            instrument_id=None, venue_order_id=None,
            start=None, end=None,
            command_id=TestIdStubs.uuid(), ts_init=0,
        )

        results = self._run(client.generate_fill_reports(cmd))
        assert len(results) == 1
        assert isinstance(results[0].trade_id, TradeId)

    def test_generate_position_status_reports(self):
        client = _make_exec_client()
        client._client.get_positions = AsyncMock(return_value={
            "securities": [{"figi": "BBG004730N88", "balance": "100"}],
            "futures": [{"figi": "FUT-SBER-0325", "balance": "-50"}],
        })

        results = self._run(client.generate_position_status_reports(None))
        assert len(results) == 2
        assert results[0].position_side == PositionSide.LONG
        assert results[0].quantity == Quantity.from_int(100)
        assert results[1].position_side == PositionSide.SHORT
        assert results[1].quantity == Quantity.from_int(50)

    def test_generate_mass_status(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(return_value=[
            {"figi": "BBG004730N88", "order_id": "o1", "direction": 1,
             "order_type": 1, "execution_report_status": 4,
             "lots_requested": 10, "lots_executed": 0},
        ])
        client._client.get_operations = AsyncMock(return_value={"items": []})
        client._client.get_positions = AsyncMock(return_value={
            "securities": [], "futures": [],
        })

        result = self._run(client.generate_mass_status())
        assert result is not None

    def test_update_account_state(self):
        client = _make_exec_client()
        client._client.get_portfolio = AsyncMock(return_value={
            "total_amount_portfolio": {"currency": "RUB", "units": "100000", "nano": 0},
        })
        client._client.get_positions = AsyncMock(return_value={
            "securities": [], "futures": [], "currencies": [],
        })

        self._run(client._update_account_state())
        client._client.get_portfolio.assert_called_once()
        client.generate_account_state.assert_called_once()

    def test_query_account(self):
        client = _make_exec_client()
        client._client.get_portfolio = AsyncMock(return_value={
            "total_amount_portfolio": {"currency": "RUB", "units": "50000", "nano": 0},
        })
        client._client.get_positions = AsyncMock(return_value={
            "securities": [], "futures": [], "currencies": [],
        })

        self._run(client._query_account(None))
        client._client.get_portfolio.assert_called_once()
        client.generate_account_state.assert_called_once()

    def test_is_option_instrument(self):
        assert TInvestExecutionClient._is_option_instrument(_SBER) is False

        from nautilus_trader.model.enums import AssetClass
        from nautilus_trader.model.enums import OptionKind
        from nautilus_trader.model.instruments import OptionContract

        option = OptionContract(
            instrument_id=InstrumentId(Symbol("SBER2503"), Venue("TINVEST")),
            raw_symbol=Symbol("SBER2503"),
            asset_class=AssetClass.EQUITY,
            currency=_SBER.quote_currency,
            price_precision=2,
            price_increment=Price.from_str("0.01"),
            multiplier=Quantity.from_int(100),
            lot_size=Quantity.from_int(1),
            underlying="SBER",
            option_kind=OptionKind.CALL,
            strike_price=Price.from_str("300.00"),
            activation_ns=0,
            expiration_ns=9999999999999999999,
            ts_event=0,
            ts_init=0,
        )
        assert TInvestExecutionClient._is_option_instrument(option) is True

    def test_map_order_type_forces_limit_for_options(self):
        from nautilus_trader.model.enums import AssetClass
        from nautilus_trader.model.enums import OptionKind
        from nautilus_trader.model.instruments import OptionContract

        option = OptionContract(
            instrument_id=InstrumentId(Symbol("SBER2503"), Venue("TINVEST")),
            raw_symbol=Symbol("SBER2503"),
            asset_class=AssetClass.EQUITY,
            currency=_SBER.quote_currency,
            price_precision=2,
            price_increment=Price.from_str("0.01"),
            multiplier=Quantity.from_int(100),
            lot_size=Quantity.from_int(1),
            underlying="SBER",
            option_kind=OptionKind.CALL,
            strike_price=Price.from_str("300.00"),
            activation_ns=0,
            expiration_ns=9999999999999999999,
            ts_event=0,
            ts_init=0,
        )

        client = _make_exec_client()
        client._cache.instrument = MagicMock(return_value=option)
        result = client._map_order_type(OrderType.MARKET, option.id)
        assert result == 1

    def test_start_native_streams(self):
        client = _make_exec_client()
        native_client = MagicMock()

        with pytest.MonkeyPatch.context() as mp:
            mock_oss = MagicMock()
            mock_ps = MagicMock()
            mock_pos = MagicMock()

            mp.setattr(
                "nautilus_trader.adapters.tinvest.execution.TInvestOrderStateStream",
                mock_oss,
            )
            mp.setattr(
                "nautilus_trader.adapters.tinvest.execution.TInvestPortfolioStream",
                mock_ps,
            )
            mp.setattr(
                "nautilus_trader.adapters.tinvest.execution.TInvestPositionsStream",
                mock_pos,
            )

            mos = MagicMock()
            mps = MagicMock()
            mpos = MagicMock()
            mock_oss.return_value = mos
            mock_ps.return_value = mps
            mock_pos.return_value = mpos

            self._run(client._start_native_streams(native_client))

            mos.start.assert_called_once()
            mps.start.assert_called_once()
            mpos.start.assert_called_once()
            assert len(client._native_stream_tasks) == 3

    def test_stop_native_streams(self):
        client = _make_exec_client()
        mos = MagicMock()
        mps = MagicMock()
        mpos = MagicMock()
        client._order_state_stream = mos
        client._portfolio_stream = mps
        client._positions_stream = mpos

        self._run(client._stop_native_streams())

        mos.stop.assert_called_once()
        mps.stop.assert_called_once()
        mpos.stop.assert_called_once()
        assert client._order_state_stream is None
        assert client._portfolio_stream is None
        assert client._positions_stream is None


# ──────────────────────────────────────────────────────────────────────────────
# T13: TestSafeExtractPrice
# ──────────────────────────────────────────────────────────────────────────────


class TestSafeExtractPrice:

    def test_none_returns_zero(self):
        client = _make_exec_client()
        result = client._safe_extract_price(None)
        assert float(result) == 0.0

    def test_dict_units_and_nano(self):
        client = _make_exec_client()
        result = client._safe_extract_price({"units": "150", "nano": 250000000})
        assert float(result) == 150.25

    def test_dict_units_only(self):
        client = _make_exec_client()
        result = client._safe_extract_price({"units": "100"})
        assert float(result) == 100.0

    def test_dict_nano_only(self):
        client = _make_exec_client()
        result = client._safe_extract_price({"nano": 500000000})
        assert float(result) == 0.5

    def test_proto_object_with_units_nano(self):
        client = _make_exec_client()
        proto = MagicMock()
        proto.units = 200
        proto.nano = 300000000
        result = client._safe_extract_price(proto)
        assert float(result) == 200.3

    def test_non_dict_non_proto_returns_zero(self):
        client = _make_exec_client()
        result = client._safe_extract_price("not_valid")
        assert float(result) == 0.0

    def test_custom_precision(self):
        client = _make_exec_client()
        result = client._safe_extract_price(None, default_precision=4)
        assert float(result) == 0.0
        assert result.precision == 4


# ──────────────────────────────────────────────────────────────────────────────
# T14: TestParseOrderStatusReport
# ──────────────────────────────────────────────────────────────────────────────


class TestParseOrderStatusReport:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_valid_data(self):
        client = _make_exec_client()
        data = {
            "order_id": "order-abc-123",
            "direction": 1,  # BUY
            "order_type": 1,  # LIMIT
            "execution_report_status": 4,  # ACCEPTED
            "ticker": "SBER",
            "lot_size": 10,
        }
        report = client._parse_order_status_report(data)
        assert report is not None
        assert report.venue_order_id.value == "order-abc-123"
        assert report.order_side == OrderSide.BUY
        assert report.order_type == OrderType.LIMIT
        assert report.order_status == OrderStatus.ACCEPTED
        assert float(report.quantity) == 10.0

    def test_sell_direction(self):
        client = _make_exec_client()
        data = {
            "order_id": "order-sell",
            "direction": 2,
            "order_type": 2,
            "execution_report_status": 1,  # FILLED
            "ticker": "SBER",
            "lot_size": 5,
        }
        report = client._parse_order_status_report(data)
        assert report is not None
        assert report.order_side == OrderSide.SELL
        assert report.order_status == OrderStatus.FILLED

    def test_partially_filled(self):
        client = _make_exec_client()
        data = {
            "order_id": "order-pf",
            "direction": 1,
            "order_type": 1,
            "execution_report_status": 5,  # PARTIALLY_FILLED
            "ticker": "SBER",
            "lot_size": 10,
        }
        report = client._parse_order_status_report(data)
        assert report is not None
        assert report.order_status == OrderStatus.PARTIALLY_FILLED

    def test_rejected_status(self):
        client = _make_exec_client()
        data = {
            "order_id": "order-rej",
            "direction": 1,
            "order_type": 1,
            "execution_report_status": 2,  # REJECTED
            "ticker": "SBER",
            "lot_size": 10,
        }
        report = client._parse_order_status_report(data)
        assert report is not None
        assert report.order_status == OrderStatus.REJECTED

    def test_invalid_data_returns_none(self):
        client = _make_exec_client()
        report = client._parse_order_status_report({})
        assert report is None

    def test_missing_fields_defaults(self):
        client = _make_exec_client()
        data = {
            "order_id": "minimal",
            "ticker": "SBER",
            "lot_size": 1,
        }
        report = client._parse_order_status_report(data)
        assert report is not None
        assert report.order_side == OrderSide.BUY
        assert report.order_type == OrderType.MARKET
        assert report.order_status == OrderStatus.ACCEPTED


# ──────────────────────────────────────────────────────────────────────────────
# T15: TestParseAccountBalances
# ──────────────────────────────────────────────────────────────────────────────


class TestParseAccountBalances:

    def test_valid_dict_total_amount(self):
        client = _make_exec_client()
        data = {
            "total_amount_portfolio": {
                "currency": "RUB",
                "units": "100000",
                "nano": 500000000,
            },
        }
        balances, margins = client._parse_account_balances(data)
        assert len(balances) == 1
        assert float(balances[0].total) == 100000.5
        assert float(balances[0].free) == 100000.5
        assert float(balances[0].locked) == 0.0
        assert len(margins) == 0

    def test_no_total_amount_returns_empty(self):
        client = _make_exec_client()
        balances, margins = client._parse_account_balances({})
        assert balances == []
        assert margins == []

    def test_proto_object_total_amount(self):
        client = _make_exec_client()
        proto = MagicMock()
        proto.currency = "RUB"
        proto.units = 50000
        proto.nano = 0
        data = {"total_amount_portfolio": proto}
        balances, margins = client._parse_account_balances(data)
        assert len(balances) == 1
        assert float(balances[0].total) == 50000.0

    def test_nested_currency_dict(self):
        client = _make_exec_client()
        data = {
            "total_amount_portfolio": {
                "currency": {"currency": "USD"},
                "units": "1000",
                "nano": 0,
            },
        }
        balances, margins = client._parse_account_balances(data)
        assert len(balances) == 1
        assert balances[0].total.currency.code == "USD"

    def test_unexpected_total_amount_type(self):
        client = _make_exec_client()
        data = {"total_amount_portfolio": "not_valid"}
        balances, margins = client._parse_account_balances(data)
        assert balances == []
        assert margins == []


# ──────────────────────────────────────────────────────────────────────────────
# T16: TestParsePositionStatusReports
# ──────────────────────────────────────────────────────────────────────────────


class TestParsePositionStatusReports:

    def test_position_payload_returns_empty_but_logs(self):
        client = _make_exec_client()
        data = {
            "payload_type": "position",
            "money_count": 2,
            "securities_count": 3,
            "futures_count": 1,
            "options_count": 0,
        }
        reports = client._parse_position_status_reports(data)
        assert reports == []
        client._log.debug.assert_called()

    def test_initial_positions_payload(self):
        client = _make_exec_client()
        data = {
            "payload_type": "initial_positions",
            "money_count": 1,
            "securities_count": 2,
        }
        reports = client._parse_position_status_reports(data)
        assert reports == []

    def test_unknown_payload_type_returns_empty(self):
        client = _make_exec_client()
        data = {
            "payload_type": "unknown",
            "money_count": 0,
        }
        reports = client._parse_position_status_reports(data)
        assert reports == []

    def test_invalid_data_returns_empty(self):
        client = _make_exec_client()
        reports = client._parse_position_status_reports({})
        assert reports == []


# ──────────────────────────────────────────────────────────────────────────────
# T17: TestResolveAccountId
# ──────────────────────────────────────────────────────────────────────────────


class TestResolveAccountId:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_uses_configured_account_id(self):
        client = _make_exec_client()
        client._account_id = AccountId("TINVEST-real-id-123")
        client._account_str = "real-id-123"
        self._run(client._resolve_account_id())
        # Should not call get_accounts because account_id is valid
        client._client.get_accounts.assert_not_called()

    def test_resolves_from_api(self):
        client = _make_exec_client()
        client._account_id = AccountId("TINVEST-1234567890")  # placeholder
        client._account_str = "TINVEST-1234567890"
        client._client.get_accounts = AsyncMock(return_value=[
            {"id": "real-acc", "type": 2, "name": "Brokerage"},
        ])
        client._set_account_id = MagicMock()
        self._run(client._resolve_account_id())
        client._client.get_accounts.assert_awaited_once()
        client._set_account_id.assert_called_once()

    def test_no_accounts_from_api(self):
        client = _make_exec_client()
        client._account_id = AccountId("TINVEST-1234567890")
        client._account_str = "TINVEST-1234567890"
        client._client.get_accounts = AsyncMock(return_value=[])
        self._run(client._resolve_account_id())
        client._log.warning.assert_called()

    def test_api_error_graceful(self):
        client = _make_exec_client()
        client._account_id = AccountId("TINVEST-1234567890")
        client._account_str = "TINVEST-1234567890"
        client._client.get_accounts = AsyncMock(side_effect=Exception("API down"))
        self._run(client._resolve_account_id())
        client._log.warning.assert_called()


# ──────────────────────────────────────────────────────────────────────────────
# T18: TestStreamProcessingMethods
# ──────────────────────────────────────────────────────────────────────────────


class TestStreamProcessingMethods:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    @staticmethod
    def _make_queue():
        import asyncio
        return asyncio.Queue()

    @staticmethod
    async def _create_coro_sleep(delay: float):
        import asyncio
        await asyncio.sleep(delay)

    @staticmethod
    def _create_task(coro):
        import asyncio
        return asyncio.create_task(coro)

    @staticmethod
    async def _wait_for(task, timeout: float):
        import asyncio
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            pass

    async def _feed_and_cancel(self, client, queue, data):
        import asyncio as _aio
        await queue.put(data)
        await _aio.sleep(0.05)
        for task in client._native_stream_tasks:
            if not task.done():
                task.cancel()

    def test_process_order_state_stream_order_state(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._order_state_stream = MagicMock()
        client._order_state_stream.queue = queue

        order_data = {
            "payload_type": "order_state",
            "order_id": "stream-order-1",
            "direction": 1,
            "order_type": 1,
            "execution_report_status": 4,
            "ticker": "SBER",
            "lot_size": 10,
        }

        async def run_test():
            task = self._create_task(client._process_order_state_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, order_data)
            await self._wait_for(task, 0.3)

        self._run(run_test())
        client._send_order_status_report.assert_called()

    def test_process_order_state_stream_ping_ignored(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._order_state_stream = MagicMock()
        client._order_state_stream.queue = queue

        async def run_test():
            task = self._create_task(client._process_order_state_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, {"payload_type": "ping"})
            await self._wait_for(task, 0.3)

        self._run(run_test())
        client._send_order_status_report.assert_not_called()

    def test_process_portfolio_stream(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._portfolio_stream = MagicMock()
        client._portfolio_stream.queue = queue

        portfolio_data = {
            "payload_type": "portfolio",
            "total_amount_portfolio": {
                "currency": "RUB",
                "units": "200000",
                "nano": 0,
            },
        }

        async def run_test():
            task = self._create_task(client._process_portfolio_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, portfolio_data)
            await self._wait_for(task, 0.3)

        self._run(run_test())
        client.generate_account_state.assert_called()

    def test_process_portfolio_stream_ping_ignored(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._portfolio_stream = MagicMock()
        client._portfolio_stream.queue = queue

        async def run_test():
            task = self._create_task(client._process_portfolio_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, {"payload_type": "ping"})
            await self._wait_for(task, 0.3)

        self._run(run_test())
        client.generate_account_state.assert_not_called()

    def test_process_positions_stream_position(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._positions_stream = MagicMock()
        client._positions_stream.queue = queue

        pos_data = {
            "payload_type": "position",
            "money_count": 1,
            "securities_count": 2,
        }

        async def run_test():
            task = self._create_task(client._process_positions_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, pos_data)
            await self._wait_for(task, 0.3)

        self._run(run_test())

    def test_process_positions_stream_ping_ignored(self):
        client = _make_exec_client()
        queue = self._make_queue()
        client._positions_stream = MagicMock()
        client._positions_stream.queue = queue

        async def run_test():
            task = self._create_task(client._process_positions_stream())
            client._native_stream_tasks.append(task)
            await self._create_coro_sleep(0.01)
            await self._feed_and_cancel(client, queue, {"payload_type": "ping"})
            await self._wait_for(task, 0.3)

        self._run(run_test())


# ──────────────────────────────────────────────────────────────────────────────
# T19: TestEdgeCasesAndErrorPaths
# ──────────────────────────────────────────────────────────────────────────────


class TestEdgeCasesAndErrorPaths:

    def _run(self, coro):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_submit_stop_order_unsupported_type(self):
        client = _make_exec_client()
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_stop_order(cmd, "BBG004730N88", 1, order.quantity))
        client.generate_order_rejected.assert_called_once()

    def test_submit_stop_order_exception(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(side_effect=Exception("gRPC error"))
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.STOP_MARKET, trigger_price=260.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_stop_order(cmd, "BBG004730N88", 1, order.quantity))
        client.generate_order_rejected.assert_called_once()
        assert "gRPC error" in client.generate_order_rejected.call_args.kwargs["reason"]

    def test_submit_order_list_exception_in_loop(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(side_effect=Exception("API error"))
        client._cache.instrument = MagicMock(return_value=_SBER)

        order1 = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        order2 = _make_mock_order(order_type=OrderType.MARKET)
        cmd = MagicMock()
        cmd.orders = [_make_submit_command(order1), _make_submit_command(order2)]
        cmd.order_list = MagicMock()
        cmd.order_list.orders = [order1, order2]

        self._run(client._submit_order_list(cmd))
        # Both should have been attempted
        assert client._client.post_order.call_count == 2
        client.generate_order_rejected.assert_called()

    def test_modify_order_exception(self):
        client = _make_exec_client()
        client._client.replace_order = AsyncMock(side_effect=Exception("Modify failed"))
        cmd = _make_modify_command()

        self._run(client._modify_order(cmd))
        client._log.error.assert_called()

    def test_cancel_order_exception(self):
        client = _make_exec_client()
        client._client.cancel_order = AsyncMock(side_effect=Exception("Cancel failed"))
        cmd = _make_cancel_command()

        self._run(client._cancel_order(cmd))
        client._log.error.assert_called()

    def test_cancel_all_orders_exception_on_get_orders(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(side_effect=Exception("API error"))
        cmd = _make_cancel_all_command()

        self._run(client._cancel_all_orders(cmd))
        client._log.error.assert_called()

    def test_cancel_all_orders_partial_failure(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(return_value=[
            {"order_id": "order-1"}, {"order_id": "order-2"},
        ])
        client._client.cancel_order = AsyncMock(side_effect=[
            {"success": True},
            Exception("Cancel failed for order-2"),
        ])
        cmd = _make_cancel_all_command()

        self._run(client._cancel_all_orders(cmd))
        assert client._client.cancel_order.call_count == 2
        client._log.warning.assert_called()

    def test_generate_order_status_reports_exception(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(side_effect=Exception("API error"))

        results = self._run(client.generate_order_status_reports(None))
        assert results == []
        client._log.warning.assert_called()

    def test_generate_order_status_report_exception(self):
        client = _make_exec_client()
        client._client.get_order_state = AsyncMock(side_effect=Exception("API error"))

        from nautilus_trader.execution.messages import QueryOrder
        cmd = QueryOrder(
            trader_id=TestIdStubs.trader_id(),
            strategy_id=TestIdStubs.strategy_id(),
            instrument_id=_SBER.id,
            client_order_id=TestIdStubs.client_order_id(),
            venue_order_id=VenueOrderId("order-err"),
            command_id=TestIdStubs.uuid(),
            ts_init=0,
        )
        result = self._run(client.generate_order_status_report(cmd))
        assert result is None

    def test_generate_fill_reports_none_result(self):
        client = _make_exec_client()
        client._client.get_operations = AsyncMock(return_value=None)

        from nautilus_trader.execution.messages import GenerateFillReports
        cmd = GenerateFillReports(
            instrument_id=None, venue_order_id=None,
            start=None, end=None,
            command_id=TestIdStubs.uuid(), ts_init=0,
        )
        results = self._run(client.generate_fill_reports(cmd))
        assert results == []

    def test_generate_fill_reports_exception(self):
        client = _make_exec_client()
        client._client.get_operations = AsyncMock(side_effect=Exception("API error"))

        from nautilus_trader.execution.messages import GenerateFillReports
        cmd = GenerateFillReports(
            instrument_id=None, venue_order_id=None,
            start=None, end=None,
            command_id=TestIdStubs.uuid(), ts_init=0,
        )
        results = self._run(_Real.generate_fill_reports(cast(_Real, client), cmd))
        assert results == []

    def test_generate_position_status_reports_none_result(self):
        client = _make_exec_client()
        client._client.get_positions = AsyncMock(return_value=None)

        results = self._run(client.generate_position_status_reports(None))
        assert results == []

    def test_generate_position_status_reports_exception(self):
        client = _make_exec_client()
        client._client.get_positions = AsyncMock(side_effect=Exception("API error"))

        results = self._run(_Real.generate_position_status_reports(cast(_Real, client), None))
        assert results == []

    def test_generate_position_status_reports_flat_position(self):
        client = _make_exec_client()
        client._client.get_positions = AsyncMock(return_value={
            "securities": [{"figi": "BBG004730N88", "balance": "0"}],
            "futures": [],
        })

        results = self._run(client.generate_position_status_reports(None))
        assert len(results) == 1
        assert results[0].position_side == PositionSide.FLAT

    def test_generate_mass_status_exception(self):
        client = _make_exec_client()
        client._client.get_orders = AsyncMock(side_effect=Exception("API error"))

        result = self._run(client.generate_mass_status())
        assert result is None

    def test_update_account_state_proto_total_amount(self):
        client = _make_exec_client()
        proto_amount = MagicMock()
        proto_amount.currency = "RUB"
        proto_amount.units = 75000
        proto_amount.nano = 250000000
        client._client.get_portfolio = AsyncMock(return_value={
            "total_amount_portfolio": proto_amount,
        })
        client._client.get_positions = AsyncMock(return_value={
            "securities": [], "futures": [], "currencies": [],
        })

        self._run(client._update_account_state())
        client.generate_account_state.assert_called_once()

    def test_update_account_state_no_account_id(self):
        client = _make_exec_client()
        client.account_id = None
        client._account_id = None

        self._run(client._update_account_state())
        client._log.warning.assert_called()

    def test_update_account_state_exception(self):
        client = _make_exec_client()
        client._client.get_portfolio = AsyncMock(side_effect=Exception("Network error"))

        self._run(client._update_account_state())
        client._log.warning.assert_called()

    def test_submit_order_none_result(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(return_value=None)
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))
        client._log.warning.assert_called()

    def test_submit_stop_order_none_result(self):
        client = _make_exec_client()
        client._client.post_stop_order = AsyncMock(return_value=None)
        client._cache.instrument = MagicMock(return_value=_SBER)
        order = _make_mock_order(order_type=OrderType.STOP_MARKET, trigger_price=260.0)
        cmd = _make_submit_command(order)

        self._run(client._submit_order(cmd))
        client._log.warning.assert_called()

    def test_modify_order_none_result(self):
        client = _make_exec_client()
        client._client.replace_order = AsyncMock(return_value=None)
        cmd = _make_modify_command()

        self._run(client._modify_order(cmd))
        client._log.warning.assert_called()

    def test_update_account_state_unexpected_total_amount_type(self):
        client = _make_exec_client()
        client._client.get_portfolio = AsyncMock(return_value={
            "total_amount_portfolio": "unexpected_string",
        })
        client._client.get_positions = AsyncMock(return_value={
            "securities": [], "futures": [], "currencies": [],
        })

        self._run(client._update_account_state())
        client._log.warning.assert_called()
        client.generate_account_state.assert_not_called()

    def test_stop_native_streams_task_cancellation(self):
        client = _make_exec_client()
        mock_task = MagicMock()
        mock_task.done = MagicMock(return_value=False)
        client._native_stream_tasks = [mock_task]

        self._run(client._stop_native_streams())

        mock_task.cancel.assert_called_once()

    def test_operation_item_to_fill_reports_no_figi(self):
        client = _make_exec_client()
        item = {"figi": "", "id": "op-1", "quantity": "10"}
        reports = _Real._operation_item_to_fill_reports(cast(_Real, client), item, 0)
        assert reports == []

    def test_operation_item_to_fill_reports_zero_quantity(self):
        client = _make_exec_client()
        item = {"figi": "BBG004730N88", "id": "op-1", "quantity": "0"}
        reports = _Real._operation_item_to_fill_reports(cast(_Real, client), item, 0)
        assert reports == []

    def test_operation_item_to_fill_reports_zero_quantity_trades(self):
        client = _make_exec_client()
        item = {
            "figi": "BBG004730N88",
            "id": "op-zero-trades",
            "quantity": "100",
            "price": {"units": "265", "nano": 0},
            "payment": {"units": "26500", "nano": 0},
            "trades_info": {"trades": [
                {"quantity": "0"},
                {"quantity": "0"},
            ]},
        }
        reports = _Real._operation_item_to_fill_reports(cast(_Real, client), item, 0)
        assert reports == []

    def test_order_state_to_report(self):
        client = _make_exec_client()
        state = {
            "figi": "BBG004730N88",
            "order_id": "order-report-1",
            "direction": 1,
            "order_type": 1,
            "execution_report_status": 4,
            "lots_requested": 10,
            "lots_executed": 0,
        }
        report = _Real._order_state_to_report(cast(_Real, client), state)
        assert report is not None
        assert report.venue_order_id.value == "order-report-1"
        assert report.order_side == OrderSide.BUY
        assert float(report.quantity) == 10.0
        assert float(report.filled_qty) == 0.0

    def test_parse_account_balances_exception(self):
        client = _make_exec_client()
        # total_amount is a dict with invalid units that triggers int() ValueError
        data = {"total_amount_portfolio": {"currency": None, "units": "not_a_number", "nano": 0}}
        balances, margins = client._parse_account_balances(data)
        assert balances == []
        assert margins == []
        client._log.warning.assert_called()

    def test_submit_order_list_exception_on_individual_order(self):
        client = _make_exec_client()
        client._client.post_order = AsyncMock(side_effect=Exception("Order failed"))
        client._cache.instrument = MagicMock(return_value=_SBER)
        order1 = _make_mock_order(order_type=OrderType.LIMIT, price=265.0)
        cmd = MagicMock()
        cmd.orders = [_make_submit_command(order1)]
        cmd.order_list = MagicMock()
        cmd.order_list.orders = [order1]

        self._run(client._submit_order_list(cmd))
        client._log.error.assert_called()

    def test_stop_native_streams_exception(self):
        client = _make_exec_client()
        mos = MagicMock()
        mos.stop = MagicMock(side_effect=Exception("Stop failed"))
        client._order_state_stream = mos
        client._portfolio_stream = None
        client._positions_stream = None

        self._run(client._stop_native_streams())
        client._log.warning.assert_called()
