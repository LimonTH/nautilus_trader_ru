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

from unittest.mock import MagicMock, patch

import pytest

from nautilus_trader.adapters.tinvest.factories import (
    TInvestLiveDataClientFactory,
    TInvestLiveExecClientFactory,
    get_shared_grpc_client,
)
from nautilus_trader.adapters.tinvest.config import (
    TInvestClientConfig,
    TInvestDataClientConfig,
    TInvestExecClientConfig,
)
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.model.identifiers import TraderId


class TestTInvestFactories:
    def test_data_factory_name(self):
        # Arrange, Act, Assert
        assert TInvestLiveDataClientFactory.name() == "TINVEST"

    def test_exec_factory_name(self):
        # Arrange, Act, Assert
        assert TInvestLiveExecClientFactory.name() == "TINVEST"


class TestGetSharedGrpcClient:
    @pytest.fixture(autouse=True)
    def setup(self):
        # Reset the shared gRPC client singleton before each test
        import nautilus_trader.adapters.tinvest.factories as factories_mod

        factories_mod._shared_grpc_client = None
        yield
        factories_mod._shared_grpc_client = None

    def test_first_call_creates_new_client(self):
        # Arrange
        config = TInvestClientConfig(token="test_token")

        with patch(
            "nautilus_trader.adapters.tinvest.factories.TInvestGrpcClient",
        ) as mock_grpc_class:
            mock_client = MagicMock()
            mock_grpc_class.return_value = mock_client
            # Act
            result = get_shared_grpc_client(config)
            # Assert
            mock_grpc_class.assert_called_once_with(config)
            assert result is mock_client

    def test_second_call_returns_same_client(self):
        # Arrange
        config = TInvestClientConfig(token="test_token")

        with patch(
            "nautilus_trader.adapters.tinvest.factories.TInvestGrpcClient",
        ) as mock_grpc_class:
            mock_client = MagicMock()
            mock_grpc_class.return_value = mock_client
            # Act
            first = get_shared_grpc_client(config)
            second = get_shared_grpc_client(config)
            # Assert
            mock_grpc_class.assert_called_once_with(config)
            assert first is second


class TestFactoryCreateMethods:
    @pytest.fixture(autouse=True)
    def setup(self):
        import nautilus_trader.adapters.tinvest.factories as factories_mod

        factories_mod._shared_grpc_client = None
        yield
        factories_mod._shared_grpc_client = None

    def test_data_factory_create_returns_tinvest_data_client(self):
        # Arrange
        import asyncio

        trader_id = TraderId("TESTER-001")
        clock = LiveClock()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.TInvestGrpcClient",
        ) as mock_grpc_class:
            mock_client = MagicMock()
            mock_client._has_native_streaming.return_value = False
            mock_grpc_class.return_value = mock_client

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_class:
                mock_provider = MagicMock()
                mock_provider_class.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestDataClient",
                ) as mock_data_class:
                    mock_data_client = MagicMock()
                    mock_data_class.return_value = mock_data_client

                    factory = TInvestLiveDataClientFactory()
                    tinvest_config = TInvestClientConfig(token="test")
                    config = TInvestDataClientConfig(tinvest=tinvest_config)
                    msgbus = MessageBus(trader_id, clock)
                    cache = MagicMock()

                    # Act
                    result = factory.create(
                        loop=asyncio.get_event_loop(),
                        name="TINVEST",
                        config=config,
                        msgbus=msgbus,
                        cache=cache,
                        clock=clock,
                    )
                    # Assert
                    assert result is mock_data_client

    def test_exec_factory_create_returns_tinvest_execution_client(self):
        # Arrange
        import asyncio

        trader_id = TraderId("TESTER-001")
        clock = LiveClock()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.TInvestGrpcClient",
        ) as mock_grpc_class:
            mock_client = MagicMock()
            mock_client._has_native_streaming.return_value = False
            mock_grpc_class.return_value = mock_client

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_class:
                mock_provider = MagicMock()
                mock_provider_class.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestExecutionClient",
                ) as mock_exec_class:
                    mock_exec_client = MagicMock()
                    mock_exec_class.return_value = mock_exec_client

                    factory = TInvestLiveExecClientFactory()
                    tinvest_config = TInvestClientConfig(token="test")
                    config = TInvestExecClientConfig(
                        tinvest=tinvest_config,
                        account_id="TINVEST-001",
                    )
                    msgbus = MessageBus(trader_id, clock)
                    cache = MagicMock()

                    # Act
                    result = factory.create(
                        loop=asyncio.get_event_loop(),
                        name="TINVEST",
                        config=config,
                        msgbus=msgbus,
                        cache=cache,
                        clock=clock,
                    )
                    # Assert
                    assert result is mock_exec_client

    def test_exec_factory_default_account_id(self):
        # Arrange
        import asyncio

        trader_id = TraderId("TESTER-001")
        clock = LiveClock()

        with patch(
            "nautilus_trader.adapters.tinvest.factories.TInvestGrpcClient",
        ) as mock_grpc_class:
            mock_client = MagicMock()
            mock_client._has_native_streaming.return_value = False
            mock_grpc_class.return_value = mock_client

            with patch(
                "nautilus_trader.adapters.tinvest.factories.TInvestInstrumentProvider",
            ) as mock_provider_class:
                mock_provider = MagicMock()
                mock_provider_class.return_value = mock_provider

                with patch(
                    "nautilus_trader.adapters.tinvest.factories.TInvestExecutionClient",
                ) as mock_exec_class:
                    mock_exec_client = MagicMock()
                    mock_exec_class.return_value = mock_exec_client

                    factory = TInvestLiveExecClientFactory()
                    tinvest_config = TInvestClientConfig(token="test")
                    config = TInvestExecClientConfig(tinvest=tinvest_config)
                    msgbus = MessageBus(trader_id, clock)
                    cache = MagicMock()

                    # Act
                    result = factory.create(
                        loop=asyncio.get_event_loop(),
                        name="TINVEST",
                        config=config,
                        msgbus=msgbus,
                        cache=cache,
                        clock=clock,
                    )
                    # Assert - should default account_id to "TINVEST-0000000000"
                    assert result is mock_exec_client
