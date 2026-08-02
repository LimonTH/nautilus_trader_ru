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

from unittest.mock import patch

import pytest

from nautilus_trader.adapters.tinvest.config import TInvestClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest.config import TInvestInstrumentProviderConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import RoutingConfig


# ──────────────────────────────────────────────────────────────────────────────
# TInvestClientConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestClientConfig:
    def test_default_values(self):
        config = TInvestClientConfig(token="test-token")

        assert config.token == "test-token"
        assert config.target == ""
        assert config.sandbox is False
        assert config.connection_timeout_ms == 5_000
        assert config.keepalive_ms == 10_000
        assert config.max_message_size == 64 * 1024 * 1024
        assert config.max_retries == 3
        assert config.retry_wait_ms == 1_000
        assert config.ca_cert_path is None

    def test_default_values_with_custom(self):
        config = TInvestClientConfig(
            token="custom-token",
            connection_timeout_ms=10_000,
            max_retries=5,
            ca_cert_path="/path/to/cert.pem",
        )

        assert config.token == "custom-token"
        assert config.connection_timeout_ms == 10_000
        assert config.max_retries == 5
        assert config.ca_cert_path == "/path/to/cert.pem"
        # Defaults untouched
        assert config.sandbox is False
        assert config.keepalive_ms == 10_000

    def test_effective_target_sandbox(self):
        config = TInvestClientConfig(token="test-token", sandbox=True)

        result = config.effective_target()

        assert result == "sandbox-invest-public-api.tbank.ru:443"

    def test_effective_target_production(self):
        config = TInvestClientConfig(token="test-token", sandbox=False)

        result = config.effective_target()

        assert result == "invest-public-api.tbank.ru:443"

    def test_effective_target_custom_overrides_environment(self):
        config = TInvestClientConfig(
            token="test-token",
            target="custom-endpoint:9999",
            sandbox=True,
        )

        result = config.effective_target()

        assert result == "custom-endpoint:9999"

    def test_to_pyo3_converts_exposed_fields(self):
        # Given
        config = TInvestClientConfig(
            token="pyo3-token",
            target="pyo3-target:443",
            sandbox=True,
            connection_timeout_ms=3_000,
            keepalive_ms=15_000,
            max_message_size=32 * 1024 * 1024,
            max_retries=2,
            retry_wait_ms=500,
            ca_cert_path="/etc/certs/ca.pem",
        )

        # When
        result = config.to_pyo3(
            trader_id="TRADER-001",
            account_id="ACC-123",
        )

        # Then – only check attributes actually exposed by the PyO3 wrapper
        assert result.token == "pyo3-token"
        assert result.target == "pyo3-target:443"
        assert result.sandbox is True
        assert result.connection_timeout_ms == 3_000
        assert result.keepalive_ms == 15_000
        assert result.ca_cert_path == "/etc/certs/ca.pem"

    def test_to_pyo3_passes_kwargs_to_pyo3_constructor(self):
        """
        Verify that to_pyo3() forwards every field to the PyO3 constructor.

        Because not all PyO3 constructor arguments are exposed as readable
        Python attributes (e.g. max_message_size, trader_id), we mock the
        PyO3 class and inspect the call kwargs.
        """
        config = TInvestClientConfig(
            token="pyo3-token",
            target="custom:443",
            sandbox=True,
            connection_timeout_ms=3_000,
            keepalive_ms=15_000,
            max_message_size=32 * 1024 * 1024,
            max_retries=2,
            retry_wait_ms=500,
            ca_cert_path="/etc/certs/ca.pem",
        )

        with patch(
            "nautilus_trader.adapters.tinvest.config.nautilus_pyo3.TInvestClientConfig",
        ) as mock_pyo3_cls:
            config.to_pyo3(
                trader_id="TRADER-001",
                account_id="ACC-123",
            )

        mock_pyo3_cls.assert_called_once_with(
            token="pyo3-token",
            target="custom:443",
            sandbox=True,
            connection_timeout_ms=3_000,
            keepalive_ms=15_000,
            max_message_size=32 * 1024 * 1024,
            max_retries=2,
            retry_wait_ms=500,
            trader_id="TRADER-001",
            account_id="ACC-123",
            ca_cert_path="/etc/certs/ca.pem",
        )

    def test_to_pyo3_empty_target_passes_none(self):
        config = TInvestClientConfig(token="pyo3-token", target="")

        with patch(
            "nautilus_trader.adapters.tinvest.config.nautilus_pyo3.TInvestClientConfig",
        ) as mock_pyo3_cls:
            config.to_pyo3()

        assert mock_pyo3_cls.call_args.kwargs["target"] is None

    def test_to_pyo3_called_without_trader_and_account(self):
        config = TInvestClientConfig(token="pyo3-token")

        with patch(
            "nautilus_trader.adapters.tinvest.config.nautilus_pyo3.TInvestClientConfig",
        ) as mock_pyo3_cls:
            config.to_pyo3()

        assert mock_pyo3_cls.call_args.kwargs["trader_id"] is None
        assert mock_pyo3_cls.call_args.kwargs["account_id"] is None

    def test_config_is_frozen(self):
        config = TInvestClientConfig(token="test-token")

        with pytest.raises(AttributeError):
            config.token = "changed"  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# TInvestDataClientConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestDataClientConfig:
    def test_minimal_config(self):
        tinvest = TInvestClientConfig(token="data-token")
        config = TInvestDataClientConfig(tinvest=tinvest)

        assert config.tinvest.token == "data-token"
        assert config.update_instruments_interval_mins is None
        # Inherited defaults
        assert config.handle_revised_bars is False
        assert isinstance(config.instrument_provider, InstrumentProviderConfig)
        assert isinstance(config.routing, RoutingConfig)

    def test_with_update_interval(self):
        tinvest = TInvestClientConfig(token="data-token")
        config = TInvestDataClientConfig(
            tinvest=tinvest,
            update_instruments_interval_mins=30,
        )

        assert config.update_instruments_interval_mins == 30

    def test_config_is_frozen(self):
        tinvest = TInvestClientConfig(token="data-token")
        config = TInvestDataClientConfig(tinvest=tinvest)

        with pytest.raises(AttributeError):
            config.update_instruments_interval_mins = 60  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# TInvestExecClientConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestExecClientConfig:
    def test_defaults(self):
        tinvest = TInvestClientConfig(token="exec-token")
        config = TInvestExecClientConfig(tinvest=tinvest)

        assert config.tinvest.token == "exec-token"
        assert config.account_id is None
        assert config.use_bestprice_orders is False
        assert config.use_async_orders is False
        # Inherited defaults
        assert isinstance(config.instrument_provider, InstrumentProviderConfig)
        assert isinstance(config.routing, RoutingConfig)

    def test_use_bestprice_orders(self):
        tinvest = TInvestClientConfig(token="exec-token")
        config = TInvestExecClientConfig(
            tinvest=tinvest,
            use_bestprice_orders=True,
        )

        assert config.use_bestprice_orders is True

    def test_use_async_orders(self):
        tinvest = TInvestClientConfig(token="exec-token")
        config = TInvestExecClientConfig(
            tinvest=tinvest,
            use_async_orders=True,
        )

        assert config.use_async_orders is True

    def test_with_account_id(self):
        tinvest = TInvestClientConfig(token="exec-token")
        config = TInvestExecClientConfig(
            tinvest=tinvest,
            account_id="ACCOUNT-42",
        )

        assert config.account_id == "ACCOUNT-42"

    def test_config_is_frozen(self):
        tinvest = TInvestClientConfig(token="exec-token")
        config = TInvestExecClientConfig(tinvest=tinvest)

        with pytest.raises(AttributeError):
            config.use_bestprice_orders = True  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# TInvestInstrumentProviderConfig
# ──────────────────────────────────────────────────────────────────────────────


class TestTInvestInstrumentProviderConfig:
    def test_defaults(self):
        config = TInvestInstrumentProviderConfig()

        assert config.load_all is True
        assert config.load_ids is None
        assert config.filters is None
        assert config.filter_callable is None
        assert config.log_warnings is True

    def test_custom_values(self):
        config = TInvestInstrumentProviderConfig(
            load_all=False,
            log_warnings=False,
        )

        assert config.load_all is False
        assert config.log_warnings is False

    def test_config_is_frozen(self):
        config = TInvestInstrumentProviderConfig()

        with pytest.raises(AttributeError):
            config.load_all = False  # type: ignore[misc]
