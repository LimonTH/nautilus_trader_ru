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

from nautilus_trader.adapters.tinvest.factories import (
    get_cached_tinvest_grpc_client,
    get_cached_tinvest_instrument_provider,
    TInvestLiveDataClientFactory,
    TInvestLiveExecClientFactory,
)
from nautilus_trader.adapters.tinvest.config import (
    TInvestClientConfig,
    TInvestDataClientConfig,
    TInvestExecClientConfig,
)


class TestTInvestFactories:
    def test_get_cached_grpc_client_returns_same_instance(self):
        # Arrange
        # Act
        client1 = get_cached_tinvest_grpc_client(
            token="test_token",
            sandbox=True,
        )
        client2 = get_cached_tinvest_grpc_client(
            token="test_token",
            sandbox=True,
        )
        # Assert
        assert client1 is client2

    def test_factory_names(self):
        # Arrange, Act, Assert
        assert TInvestLiveDataClientFactory.name() == "TINVEST"
        assert TInvestLiveExecClientFactory.name() == "TINVEST"
