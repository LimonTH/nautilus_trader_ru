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

from unittest.mock import MagicMock

import pytest

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.test_kit.stubs.events import TestEventStubs


@pytest.fixture
def venue():
    return TINVEST_VENUE


@pytest.fixture
def instrument():
    return TestInstrumentProvider.equity("SBER", "TINVEST")


@pytest.fixture
def account_state():
    return TestEventStubs.cash_account_state(account_id=AccountId("TINVEST-001"))


@pytest.fixture
def grpc_client():
    mock = MagicMock()
    return mock


@pytest.fixture
def instrument_provider(clock):
    return TInvestInstrumentProvider(clock=clock)
