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

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig


# ──────────────────────────────────────────────────────────────────────────────
# PyO3 availability detection
# ──────────────────────────────────────────────────────────────────────────────

try:
    from nautilus_trader.core import nautilus_pyo3

    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False
    nautilus_pyo3 = None  # type: ignore


# ──────────────────────────────────────────────────────────────────────────────
# Factory: TInvestClientConfig
# ──────────────────────────────────────────────────────────────────────────────


def make_tinvest_client_config(
    *,
    token: str = "test-token",
    target: str = "",
    sandbox: bool = False,
    connection_timeout_ms: int = 5_000,
    keepalive_ms: int = 10_000,
    max_message_size: int = 64 * 1024 * 1024,
    max_retries: int = 3,
    retry_wait_ms: int = 1_000,
    ca_cert_path: str | None = None,
) -> TInvestClientConfig:
    """
    Return a TInvestClientConfig with default test values.
    """
    return TInvestClientConfig(
        token=token,
        target=target,
        sandbox=sandbox,
        connection_timeout_ms=connection_timeout_ms,
        keepalive_ms=keepalive_ms,
        max_message_size=max_message_size,
        max_retries=max_retries,
        retry_wait_ms=retry_wait_ms,
        ca_cert_path=ca_cert_path,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Factory: mock TInvestGrpcClient
# ──────────────────────────────────────────────────────────────────────────────


def make_mock_grpc_client() -> MagicMock:
    """
    Return a MagicMock standing in for TInvestGrpcClient.

    All async methods return AsyncMock so they can be awaited.
    """
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.request_instruments = AsyncMock(return_value=[])
    client.request_order_book = AsyncMock(return_value=[])
    client.request_trades = AsyncMock(return_value=[])
    client.request_candles = AsyncMock(return_value=[])
    client.post_order = AsyncMock(return_value={})
    client.post_order_async = AsyncMock(return_value={})
    client.cancel_order = AsyncMock(return_value={})
    client.get_orders = AsyncMock(return_value=[])
    client.get_positions = AsyncMock(return_value=[])
    client.get_portfolio = AsyncMock(return_value={})
    client._has_native_client = False
    client._has_native_stream = False
    return client


# ──────────────────────────────────────────────────────────────────────────────
# Factory: mock Cache
# ──────────────────────────────────────────────────────────────────────────────


def make_mock_cache() -> MagicMock:
    """
    Return a MagicMock standing in for Cache.
    """
    cache = MagicMock()
    cache.instrument = MagicMock(return_value=None)
    cache.add_instrument = MagicMock()
    return cache


# ──────────────────────────────────────────────────────────────────────────────
# Factory: mock MessageBus
# ──────────────────────────────────────────────────────────────────────────────


def make_mock_message_bus() -> MagicMock:
    """
    Return a MagicMock standing in for MessageBus.
    """
    msgbus = MagicMock()
    msgbus.send = MagicMock()
    msgbus.register = MagicMock()
    msgbus.deregister = MagicMock()
    return msgbus


# ──────────────────────────────────────────────────────────────────────────────
# Factory: mock LiveClock
# ──────────────────────────────────────────────────────────────────────────────


def make_mock_clock() -> MagicMock:
    """
    Return a MagicMock standing in for LiveClock.

    timestamp_ns returns 0 (fixed) for deterministic test behaviour.
    """
    clock = MagicMock()
    clock.timestamp_ns = MagicMock(return_value=0)
    return clock


# ──────────────────────────────────────────────────────────────────────────────
# Factory: mock InstrumentProvider
# ──────────────────────────────────────────────────────────────────────────────


def make_mock_instrument_provider() -> MagicMock:
    """
    Return a MagicMock standing in for TInvestInstrumentProvider.
    """
    provider = MagicMock()
    provider.load_all = AsyncMock()
    provider.load_ids = AsyncMock()
    provider.find_instrument_by_figi = MagicMock(return_value=None)
    provider.find_instrument_by_ticker = MagicMock(return_value=None)
    provider.get_instruments = MagicMock(return_value={})
    return provider


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_tinvest_config() -> TInvestClientConfig:
    """Return a sample TInvestClientConfig with a test token."""
    return make_tinvest_client_config()


@pytest.fixture
def mock_grpc_client() -> MagicMock:
    """Return a fully mocked TInvestGrpcClient."""
    return make_mock_grpc_client()


@pytest.fixture
def mock_cache() -> MagicMock:
    """Return a mocked Cache."""
    return make_mock_cache()


@pytest.fixture
def mock_message_bus() -> MagicMock:
    """Return a mocked MessageBus."""
    return make_mock_message_bus()


@pytest.fixture
def mock_clock() -> MagicMock:
    """Return a mocked LiveClock."""
    return make_mock_clock()


@pytest.fixture
def sample_instrument_dict() -> dict:
    """Return a minimal T-Invest instrument dict (share)."""
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
        "nominal": {"units": "3", "nano": 0},
    }


@pytest.fixture
def sample_order_book_dict() -> dict:
    """Return a minimal T-Invest order book dict."""
    return {
        "figi": "BBG004730N88",
        "depth": 2,
        "is_consistent": True,
        "bids": [
            {"price": {"units": "265", "nano": 0}, "quantity": "100"},
            {"price": {"units": "264", "nano": 0}, "quantity": "50"},
        ],
        "asks": [
            {"price": {"units": "266", "nano": 0}, "quantity": "80"},
            {"price": {"units": "267", "nano": 0}, "quantity": "30"},
        ],
        "time": "2024-01-15T10:00:00Z",
        "limit_up": {"units": "300", "nano": 0},
        "limit_down": {"units": "200", "nano": 0},
    }
