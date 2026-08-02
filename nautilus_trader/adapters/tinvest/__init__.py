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

from nautilus_trader.adapters.tinvest.common import TINVEST
from nautilus_trader.adapters.tinvest.common import TINVEST_CLIENT_ID
from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestInstrumentProviderConfig
from nautilus_trader.adapters.tinvest.data import TInvestDataClient
from nautilus_trader.adapters.tinvest.execution import TInvestExecutionClient
from nautilus_trader.adapters.tinvest.factories import TInvestLiveDataClientFactory
from nautilus_trader.adapters.tinvest.factories import TInvestLiveExecClientFactory
from nautilus_trader.adapters.tinvest.grpc_client import TInvestGrpcClient
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider


# Native gRPC streaming classes (PyO3)
try:
    from nautilus_trader.core.nautilus_pyo3.tinvest import TInvestMarketDataStream
    from nautilus_trader.core.nautilus_pyo3.tinvest import TInvestOrderStateStream
    from nautilus_trader.core.nautilus_pyo3.tinvest import TInvestPortfolioStream
    from nautilus_trader.core.nautilus_pyo3.tinvest import TInvestPositionsStream
except ImportError:
    TInvestMarketDataStream = None  # type: ignore
    TInvestOrderStateStream = None  # type: ignore
    TInvestPortfolioStream = None  # type: ignore
    TInvestPositionsStream = None  # type: ignore


__all__ = [
    "TINVEST",
    "TINVEST_CLIENT_ID",
    "TINVEST_VENUE",
    "TInvestClientConfig",
    "TInvestDataClient",
    "TInvestDataClientConfig",
    "TInvestExecClientConfig",
    "TInvestExecutionClient",
    "TInvestGrpcClient",
    "TInvestInstrumentProvider",
    "TInvestInstrumentProviderConfig",
    "TInvestLiveDataClientFactory",
    "TInvestLiveExecClientFactory",
    "TInvestMarketDataStream",
    "TInvestOrderStateStream",
    "TInvestPortfolioStream",
    "TInvestPositionsStream",
]
