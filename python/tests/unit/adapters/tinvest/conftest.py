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

"""
Local conftest for T-Invest unit tests.

Provides mock PyO3 modules so tests can run without building the Rust extension.
"""

import sys
from unittest.mock import MagicMock, Mock

import pytest

# -----------------------------------------------------------------------------
# Pre-import mocking: inject mock _libnautilus before nautilus_trader is loaded
# -----------------------------------------------------------------------------


class _MockModule:
    """A generic mock module that returns MagicMock for any attribute access."""

    def __init__(self, name: str):
        self.__name__ = name

    def __getattr__(self, name: str):
        obj = MagicMock()
        setattr(self, name, obj)
        return obj

    def __repr__(self):
        return f"<MockModule {self.__name__}>"


# Build the mock module hierarchy before nautilus_trader is imported
_mock_common = _MockModule("nautilus_trader._libnautilus.common")
_mock_model = _MockModule("nautilus_trader._libnautilus.model")
_mock_core = _MockModule("nautilus_trader._libnautilus.core")
_mock_backtest = _MockModule("nautilus_trader._libnautilus.backtest")
_mock_persistence = _MockModule("nautilus_trader._libnautilus.persistence")

# Create a mock _libnautilus package
_mock_libnautilus = _MockModule("nautilus_trader._libnautilus")
_mock_libnautilus.common = _mock_common
_mock_libnautilus.model = _mock_model
_mock_libnautilus.core = _mock_core
_mock_libnautilus.backtest = _mock_backtest
_mock_libnautilus.persistence = _mock_persistence

sys.modules["nautilus_trader._libnautilus"] = _mock_libnautilus
sys.modules["nautilus_trader._libnautilus.common"] = _mock_common
sys.modules["nautilus_trader._libnautilus.model"] = _mock_model
sys.modules["nautilus_trader._libnautilus.core"] = _mock_core
sys.modules["nautilus_trader._libnautilus.backtest"] = _mock_backtest
sys.modules["nautilus_trader._libnautilus.persistence"] = _mock_persistence

# Provide mock T-Invest PyO3 classes
_mock_tinvest_pyo3 = _MockModule("nautilus_trader.core.nautilus_pyo3.tinvest")
sys.modules["nautilus_trader.core.nautilus_pyo3"] = _MockModule(
    "nautilus_trader.core.nautilus_pyo3",
)
# Set up tinvest submodule on the already-registered mock
_tinvest_submod = _MockModule("nautilus_trader.core.nautilus_pyo3.tinvest")
sys.modules["nautilus_trader.core.nautilus_pyo3.tinvest"] = _tinvest_submod


import inspect


def pytest_pycollect_makeitem(collector, name, obj):
    """
    Prevent pytest from collecting Rust/PyO3 utility classes as test classes.
    """
    if inspect.isclass(obj) and name.startswith("Test"):
        module = getattr(obj, "__module__", "")
        if (
            module.startswith("nautilus_trader.")
            and ".tests" not in module
            and not module.startswith("tests.")
        ):
            return []


@pytest.fixture(autouse=True)
def _reset_mock_state():
    """Reset mock side effects between tests."""
    yield
