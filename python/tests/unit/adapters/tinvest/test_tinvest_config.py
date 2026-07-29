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

from nautilus_trader.adapters.tinvest.config import (
    TInvestClientConfig,
    TInvestDataClientConfig,
    TInvestExecClientConfig,
    TInvestInstrumentProviderConfig,
)
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.live.config import LiveDataClientConfig, LiveExecClientConfig


class TestTInvestClientConfig:
    def test_token_presence(self):
        # Arrange
        config = TInvestClientConfig(token="test_token_value")
        # Act
        result = config.token
        # Assert
        assert result == "test_token_value"

    def test_sandbox_default_false(self):
        # Arrange
        config = TInvestClientConfig(token="test")
        # Act
        result = config.sandbox
        # Assert
        assert result is False

    def test_sandbox_enabled(self):
        # Arrange
        config = TInvestClientConfig(token="test", sandbox=True)
        # Act
        result = config.sandbox
        # Assert
        assert result is True

    def test_config_repr_does_not_leak_token(self):
        # Arrange
        config = TInvestClientConfig(token="test")
        # Act
        config_repr = repr(config)
        # Assert
        assert "test" not in config_repr

    def test_default_connection_timeout_ms(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.connection_timeout_ms == 5_000

    def test_default_keepalive_ms(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.keepalive_ms == 10_000

    def test_default_max_message_size(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.max_message_size == 64 * 1024 * 1024

    def test_default_max_retries(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.max_retries == 3

    def test_default_retry_wait_ms(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.retry_wait_ms == 1_000

    def test_default_target_is_empty_string(self):
        # Arrange, Act
        config = TInvestClientConfig(token="test")
        # Assert
        assert config.target == ""

    def test_custom_target(self):
        # Arrange
        config = TInvestClientConfig(token="test", target="custom:8080")
        # Act
        result = config.target
        # Assert
        assert result == "custom:8080"

    def test_effective_target_returns_custom_when_set(self):
        # Arrange
        config = TInvestClientConfig(token="test", target="custom:8080")
        # Act
        result = config.effective_target()
        # Assert
        assert result == "custom:8080"

    def test_effective_target_returns_sandbox_when_sandbox_true(self):
        # Arrange
        config = TInvestClientConfig(token="test", sandbox=True)
        # Act
        result = config.effective_target()
        # Assert
        assert result == "sandbox-invest-public-api.tbank.ru:443"

    def test_effective_target_returns_live_by_default(self):
        # Arrange
        config = TInvestClientConfig(token="test")
        # Act
        result = config.effective_target()
        # Assert
        assert result == "invest-public-api.tbank.ru:443"

    def test_all_field_types_are_correct(self):
        # Arrange, Act
        config = TInvestClientConfig(
            token="test",
            target="host:443",
            sandbox=True,
            connection_timeout_ms=10_000,
            keepalive_ms=30_000,
            max_message_size=128 * 1024 * 1024,
            max_retries=5,
            retry_wait_ms=2_000,
            ca_cert_path="/path/to/cert.pem",
        )
        # Assert
        assert isinstance(config.token, str)
        assert isinstance(config.target, str)
        assert isinstance(config.sandbox, bool)
        assert isinstance(config.connection_timeout_ms, int)
        assert isinstance(config.keepalive_ms, int)
        assert isinstance(config.max_message_size, int)
        assert isinstance(config.max_retries, int)
        assert isinstance(config.retry_wait_ms, int)
        assert isinstance(config.ca_cert_path, (str, type(None)))


class TestTInvestDataClientConfig:
    def test_is_subclass_of_live_data_client_config(self):
        # Arrange, Act, Assert
        assert issubclass(TInvestDataClientConfig, LiveDataClientConfig)

    def test_wraps_tinvest_client_config(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test", sandbox=True)
        # Act
        config = TInvestDataClientConfig(
            tinvest=tinvest_config,
        )
        # Assert
        assert config.tinvest is tinvest_config

    def test_default_instrument_provider_loads_all(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        # Act
        config = TInvestDataClientConfig(
            tinvest=tinvest_config,
        )
        # Assert
        assert config.instrument_provider.load_all is True

    def test_custom_update_instruments_interval(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        # Act
        config = TInvestDataClientConfig(
            tinvest=tinvest_config,
            update_instruments_interval_mins=30,
        )
        # Assert
        assert config.update_instruments_interval_mins == 30

    def test_default_update_instruments_interval_is_none(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        # Act
        config = TInvestDataClientConfig(
            tinvest=tinvest_config,
        )
        # Assert
        assert config.update_instruments_interval_mins is None

    def test_custom_instrument_provider(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        provider_config = InstrumentProviderConfig(load_all=False)
        # Act
        config = TInvestDataClientConfig(
            tinvest=tinvest_config,
            instrument_provider=provider_config,
        )
        # Assert
        assert config.instrument_provider is provider_config
        assert config.instrument_provider.load_all is False


class TestTInvestExecClientConfig:
    def test_is_subclass_of_live_exec_client_config(self):
        # Arrange, Act, Assert
        assert issubclass(TInvestExecClientConfig, LiveExecClientConfig)

    def test_with_account_id(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        # Act
        config = TInvestExecClientConfig(
            tinvest=tinvest_config,
            account_id="TINVEST-001",
        )
        # Assert
        assert config.account_id == "TINVEST-001"

    def test_default_account_id_is_none(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        # Act
        config = TInvestExecClientConfig(
            tinvest=tinvest_config,
        )
        # Assert
        assert config.account_id is None

    def test_wraps_tinvest_client_config(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test", sandbox=True)
        # Act
        config = TInvestExecClientConfig(
            tinvest=tinvest_config,
            account_id="TINVEST-001",
        )
        # Assert
        assert config.tinvest is tinvest_config

    def test_custom_instrument_provider(self):
        # Arrange
        tinvest_config = TInvestClientConfig(token="test")
        provider_config = InstrumentProviderConfig(load_all=False)
        # Act
        config = TInvestExecClientConfig(
            tinvest=tinvest_config,
            instrument_provider=provider_config,
        )
        # Assert
        assert config.instrument_provider is provider_config


class TestTInvestInstrumentProviderConfig:
    def test_default_load_all(self):
        # Arrange, Act
        config = TInvestInstrumentProviderConfig()
        # Assert
        assert config.load_all is True

    def test_set_load_all_false(self):
        # Arrange, Act
        config = TInvestInstrumentProviderConfig(load_all=False)
        # Assert
        assert config.load_all is False
