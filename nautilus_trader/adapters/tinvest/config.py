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

from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.config import LiveExecClientConfig
from nautilus_trader.config import NautilusConfig
from nautilus_trader.core import nautilus_pyo3


class TInvestClientConfig(NautilusConfig, frozen=True):
    """
    Configuration for the T-Invest gRPC client connection.

    Parameters
    ----------
    token : str
        The T-Invest API token.
    target : str, optional
        The target gRPC endpoint (host:port). Defaults to sandbox or live target.
    sandbox : bool, default False
        If True, use the sandbox environment.
    connection_timeout_ms : int, optional
        Connection timeout in milliseconds.
    keepalive_ms : int, optional
        Keepalive interval in milliseconds.
    max_message_size : int, optional
        Maximum gRPC message size in bytes.
    max_retries : int, optional
        Maximum number of retry attempts.
    retry_wait_ms : int, optional
        Initial retry wait duration in milliseconds.
    """

    token: str
    target: str = ""
    sandbox: bool = False
    connection_timeout_ms: int = 5_000
    keepalive_ms: int = 10_000
    max_message_size: int = 64 * 1024 * 1024
    max_retries: int = 3
    retry_wait_ms: int = 1_000
    ca_cert_path: str | None = None

    def effective_target(self) -> str:
        if self.target:
            return self.target
        if self.sandbox:
            return "sandbox-invest-public-api.tbank.ru:443"
        return "invest-public-api.tbank.ru:443"

    def to_pyo3(
        self,
        trader_id: str | None = None,
        account_id: str | None = None,
    ) -> nautilus_pyo3.TInvestClientConfig:
        return nautilus_pyo3.TInvestClientConfig(
            token=self.token,
            target=self.target if self.target else None,
            sandbox=self.sandbox,
            connection_timeout_ms=self.connection_timeout_ms,
            keepalive_ms=self.keepalive_ms,
            max_message_size=self.max_message_size,
            max_retries=self.max_retries,
            retry_wait_ms=self.retry_wait_ms,
            trader_id=trader_id,
            account_id=account_id,
            ca_cert_path=self.ca_cert_path,
        )


class TInvestDataClientConfig(LiveDataClientConfig, frozen=True, kw_only=True):
    """
    Configuration for the T-Invest data client.

    Parameters
    ----------
    tinvest : TInvestClientConfig
        The T-Invest gRPC client configuration.
    instrument_provider : InstrumentProviderConfig, optional
        The instrument provider configuration.
    update_instruments_interval_mins : int, optional
        The interval in minutes between instrument updates. If None, no periodic updates.
    """

    tinvest: TInvestClientConfig
    update_instruments_interval_mins: int | None = None


class TInvestExecClientConfig(LiveExecClientConfig, frozen=True, kw_only=True):
    """
    Configuration for the T-Invest execution client.

    Parameters
    ----------
    tinvest : TInvestClientConfig
        The T-Invest gRPC client configuration.
    account_id : str, optional
        The account ID to use for trading.
    instrument_provider : InstrumentProviderConfig, optional
        The instrument provider configuration.
    use_bestprice_orders : bool, default False
        If True, Nautilus ``MARKET`` orders are submitted as T-Invest
        ``ORDER_TYPE_BESTPRICE`` ("best price"). Ignored for options, which
        only support limit orders.
    use_async_orders : bool, default False
        If True, orders are submitted via ``PostOrderAsync`` (fire-and-forget;
        no blocking wait for the exchange response). Order state is then
        reconciled via the order state stream or polling.
    """

    tinvest: TInvestClientConfig
    account_id: str | None = None
    use_bestprice_orders: bool = False
    use_async_orders: bool = False


class TInvestInstrumentProviderConfig(InstrumentProviderConfig, frozen=True):
    """
    Configuration for the T-Invest instrument provider.

    Parameters
    ----------
    load_all : bool, default True
        If True, load all available instruments from T-Invest API.
    """

    load_all: bool = True
