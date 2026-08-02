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
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.factories import TInvestLiveDataClientFactory
from nautilus_trader.adapters.tinvest.factories import TInvestLiveExecClientFactory
from nautilus_trader.adapters.tinvest.factories import get_shared_grpc_client
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.model.identifiers import AccountId


# ──────────────────────────────────────────────────────────────────────────────
# Fixture: reset module-level singleton before every test
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Ensure _shared_grpc_client starts as None for every test."""
    monkeypatch.setattr(
        "nautilus_trader.adapters.tinvest.factories._shared_grpc_client",
        None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_tinvest_config() -> TInvestClientConfig:
    return TInvestClientConfig(token="test-token")


def _make_data_config() -> TInvestDataClientConfig:
    return TInvestDataClientConfig(tinvest=_make_tinvest_config())


def _make_exec_config(*, account_id: str | None = None) -> TInvestExecClientConfig:
    return TInvestExecClientConfig(
        tinvest=_make_tinvest_config(),
        account_id=account_id,
    )


def _make_mocks():
    """Return a dict of standard mocks for factory.create()."""
    return {
        "loop": MagicMock(spec=asyncio.AbstractEventLoop),
        "msgbus": MagicMock(),
        "cache": MagicMock(),
        "clock": MagicMock(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# get_shared_grpc_client
# ──────────────────────────────────────────────────────────────────────────────


class TestGetSharedGrpcClient:
    def test_singleton_returns_same_instance(self):
        """Two calls to get_shared_grpc_client return the same object."""
        config = _make_tinvest_config()

        client1 = get_shared_grpc_client(config)
        client2 = get_shared_grpc_client(config)

        assert client1 is client2

    def test_creates_client_on_first_call(self):
        """get_shared_grpc_client creates a TInvestGrpcClient."""
        config = _make_tinvest_config()

        client = get_shared_grpc_client(config)

        assert isinstance(client, TInvestGrpcClient)

    def test_singleton_reset(self, monkeypatch):
        """After resetting _shared_grpc_client=None, a new instance is created."""
        config = _make_tinvest_config()

        client1 = get_shared_grpc_client(config)

        # Simulate reset of module-level singleton
        monkeypatch.setattr(
            "nautilus_trader.adapters.tinvest.factories._shared_grpc_client",
            None,
        )

        client2 = get_shared_grpc_client(config)

        assert client1 is not client2


# ──────────────────────────────────────────────────────────────────────────────
# TInvestLiveDataClientFactory
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestLiveDataClientFactory:
    def test_create_returns_data_client(self):
        """factory.create returns a TInvestDataClient and calls get_shared_grpc_client."""
        # Import here to avoid top-level PyO3 import issues
        from nautilus_trader.adapters.tinvest.data import TInvestDataClient

        config = _make_data_config()
        mocks = _make_mocks()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.get_shared_grpc_client",
        ) as mock_get_shared:
            mock_grpc = MagicMock()
            mock_get_shared.return_value = mock_grpc

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestDataClient",
                ) as mock_data_cls:
                    mock_data = MagicMock(spec=TInvestDataClient)
                    mock_data_cls.return_value = mock_data

                    result = TInvestLiveDataClientFactory.create(
                        loop=mocks["loop"],
                        name="test-data-client",
                        config=config,
                        msgbus=mocks["msgbus"],
                        cache=mocks["cache"],
                        clock=mocks["clock"],
                    )

        # Verify get_shared_grpc_client was called with config.tinvest
        mock_get_shared.assert_called_once_with(config.tinvest)
        # Verify TInvestInstrumentProvider was constructed
        mock_provider_cls.assert_called_once()
        # Verify TInvestDataClient was constructed
        mock_data_cls.assert_called_once()
        # Result is the mocked data client
        assert result is mock_data

    def test_create_passes_correct_args_to_data_client(self):
        """Factory passes all expected arguments to TInvestDataClient constructor."""
        config = _make_data_config()
        mocks = _make_mocks()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.get_shared_grpc_client",
        ) as mock_get_shared:
            mock_grpc = MagicMock()
            mock_get_shared.return_value = mock_grpc

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestDataClient",
                ) as mock_data_cls:
                    TInvestLiveDataClientFactory.create(
                        loop=mocks["loop"],
                        name="test-data-client",
                        config=config,
                        msgbus=mocks["msgbus"],
                        cache=mocks["cache"],
                        clock=mocks["clock"],
                    )

        # Verify TInvestDataClient was called with expected kwargs
        _, kwargs = mock_data_cls.call_args
        assert kwargs["loop"] is mocks["loop"]
        assert kwargs["client"] is mock_grpc
        assert kwargs["msgbus"] is mocks["msgbus"]
        assert kwargs["cache"] is mocks["cache"]
        assert kwargs["clock"] is mocks["clock"]
        assert kwargs["instrument_provider"] is mock_provider
        assert kwargs["config"] is config
        assert kwargs["name"] == "test-data-client"


# ──────────────────────────────────────────────────────────────────────────────
# TInvestLiveExecClientFactory
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestLiveExecClientFactory:
    def test_create_returns_exec_client(self):
        """factory.create returns a TInvestExecutionClient and calls get_shared_grpc_client."""
        from nautilus_trader.adapters.tinvest.execution import TInvestExecutionClient

        config = _make_exec_config(account_id="ACC-123")
        mocks = _make_mocks()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.get_shared_grpc_client",
        ) as mock_get_shared:
            mock_grpc = MagicMock()
            mock_get_shared.return_value = mock_grpc

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestExecutionClient",
                ) as mock_exec_cls:
                    mock_exec = MagicMock(spec=TInvestExecutionClient)
                    mock_exec_cls.return_value = mock_exec

                    result = TInvestLiveExecClientFactory.create(
                        loop=mocks["loop"],
                        name="test-exec-client",
                        config=config,
                        msgbus=mocks["msgbus"],
                        cache=mocks["cache"],
                        clock=mocks["clock"],
                    )

        mock_get_shared.assert_called_once_with(config.tinvest)
        mock_exec_cls.assert_called_once()
        assert result is mock_exec

    def test_create_with_default_account_id(self):
        """Without account_id → AccountId('TINVEST-0000000000')."""
        config = _make_exec_config(account_id=None)  # No account_id
        mocks = _make_mocks()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.get_shared_grpc_client",
        ) as mock_get_shared:
            mock_grpc = MagicMock()
            mock_get_shared.return_value = mock_grpc

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestExecutionClient",
                ) as mock_exec_cls:
                    TInvestLiveExecClientFactory.create(
                        loop=mocks["loop"],
                        name="test-exec-client",
                        config=config,
                        msgbus=mocks["msgbus"],
                        cache=mocks["cache"],
                        clock=mocks["clock"],
                    )

        # Verify the account_id passed to TInvestExecutionClient
        _, kwargs = mock_exec_cls.call_args
        assert kwargs["account_id"] == AccountId("TINVEST-0000000000")

    def test_create_with_explicit_account_id(self):
        """With explicit account_id → AccountId(that value)."""
        config = _make_exec_config(account_id="CUSTOM-ACC-42")
        mocks = _make_mocks()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.get_shared_grpc_client",
        ) as mock_get_shared:
            mock_grpc = MagicMock()
            mock_get_shared.return_value = mock_grpc

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider_cls.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestExecutionClient",
                ) as mock_exec_cls:
                    TInvestLiveExecClientFactory.create(
                        loop=mocks["loop"],
                        name="test-exec-client",
                        config=config,
                        msgbus=mocks["msgbus"],
                        cache=mocks["cache"],
                        clock=mocks["clock"],
                    )

        _, kwargs = mock_exec_cls.call_args
        assert kwargs["account_id"] == AccountId("CUSTOM-ACC-42")
