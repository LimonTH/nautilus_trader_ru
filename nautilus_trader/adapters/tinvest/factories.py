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

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.data import TInvestDataClient
from nautilus_trader.adapters.tinvest.execution import TInvestExecutionClient
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.live.factories import LiveExecClientFactory
from nautilus_trader.model.identifiers import AccountId


# Module-level shared gRPC client singleton.
# TInvestGrpcClient uses Arc<RwLock<...>> internally via PyO3, so it is
# safe and efficient to share a single instance across both the data and
# execution clients (avoids opening two TCP connections to T-Invest).
_shared_grpc_client: TInvestGrpcClient | None = None


def get_shared_grpc_client(config: TInvestClientConfig) -> TInvestGrpcClient:
    """Return the shared TInvestGrpcClient, creating it on first call."""
    global _shared_grpc_client
    if _shared_grpc_client is None:
        _shared_grpc_client = TInvestGrpcClient(config)
    return _shared_grpc_client


class TInvestLiveDataClientFactory(LiveDataClientFactory):
    """
    Provides a T-Invest live data client factory.
    """

    @staticmethod
    def create(  # type: ignore
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: TInvestDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> TInvestDataClient:
        grpc_client = get_shared_grpc_client(config.tinvest)

        provider = TInvestInstrumentProvider(
            clock=clock,
            grpc_client=grpc_client,
            config=config.instrument_provider,
        )

        return TInvestDataClient(
            loop=loop,
            client=grpc_client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )


class TInvestLiveExecClientFactory(LiveExecClientFactory):
    """
    Provides a T-Invest live execution client factory.
    """

    @staticmethod
    def create(  # type: ignore
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: TInvestExecClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> TInvestExecutionClient:
        grpc_client = get_shared_grpc_client(config.tinvest)

        provider = TInvestInstrumentProvider(
            clock=clock,
            grpc_client=grpc_client,
            config=config.instrument_provider,
        )

        account_str = config.account_id or "TINVEST-0000000000"
        account_id = AccountId(account_str)

        return TInvestExecutionClient(
            loop=loop,
            client=grpc_client,
            account_id=account_id,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )
