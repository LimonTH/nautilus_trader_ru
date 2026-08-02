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


# ──────────────────────────────────────────────────────────────────────────────
# TINVEST constant
# ──────────────────────────────────────────────────────────────────────────────


def test_tinvest_is_correct_string():
    assert TINVEST == "TINVEST"
    assert isinstance(TINVEST, str)


# ──────────────────────────────────────────────────────────────────────────────
# TINVEST_CLIENT_ID constant
# ──────────────────────────────────────────────────────────────────────────────


def test_tinvest_client_id_is_client_id_instance():
    assert isinstance(TINVEST_CLIENT_ID, ClientId)
    assert str(TINVEST_CLIENT_ID) == "TINVEST"
    assert TINVEST_CLIENT_ID.value == "TINVEST"


# ──────────────────────────────────────────────────────────────────────────────
# TINVEST_VENUE constant
# ──────────────────────────────────────────────────────────────────────────────


def test_tinvest_venue_is_venue_instance():
    assert isinstance(TINVEST_VENUE, Venue)
    assert str(TINVEST_VENUE) == "TINVEST"
    assert TINVEST_VENUE.value == "TINVEST"


# ──────────────────────────────────────────────────────────────────────────────
# Consistency between constants
# ──────────────────────────────────────────────────────────────────────────────


def test_constants_are_consistent():
    assert str(TINVEST_CLIENT_ID) == TINVEST
    assert str(TINVEST_VENUE) == TINVEST
    assert TINVEST_CLIENT_ID.value == TINVEST_VENUE.value
