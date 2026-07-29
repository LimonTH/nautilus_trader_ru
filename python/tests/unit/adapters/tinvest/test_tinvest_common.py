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
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import Venue


class TestTInvestCommon:
    def test_tinvest_string_constant(self):
        # Arrange, Act, Assert
        assert TINVEST == "TINVEST"
        assert isinstance(TINVEST, str)

    def test_tinvest_venue_constant(self):
        # Arrange, Act, Assert
        assert TINVEST_VENUE == Venue("TINVEST")

    def test_tinvest_venue_value(self):
        # Arrange, Act, Assert
        assert TINVEST_VENUE.value == "TINVEST"

    def test_tinvest_client_id_constant(self):
        # Arrange, Act, Assert
        assert TINVEST_CLIENT_ID == ClientId("TINVEST")

    def test_tinvest_client_id_value(self):
        # Arrange, Act, Assert
        assert TINVEST_CLIENT_ID.value == "TINVEST"

    def test_tinvest_venue_is_unique(self):
        # Arrange
        v1 = Venue("TINVEST")
        v2 = Venue("BYBIT")
        # Act, Assert
        assert TINVEST_VENUE == v1
        assert TINVEST_VENUE != v2
