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
#  T-Invest (TINKOFF INVEST) Live Adapter Example
#
#  To run this example you will need a T-Invest API token (see https://tinvest.ru/).
#
#  1. Obtain a token from T-Invest
#  2. Set the TINVEST_API_TOKEN environment variable or pass token directly to TInvestClientConfig
#  3. For sandbox mode, set sandbox=True in TInvestClientConfig
#  4. Run this script
# -------------------------------------------------------------------------------------------------

import asyncio
import os

# Load .env / .envrc before any os.getenv() calls
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from load_env import load_env

load_env()  # reads .env (or .envrc as fallback)

from nautilus_trader.adapters.tinvest.common import TINVEST_VENUE
from nautilus_trader.adapters.tinvest.config import (
    TInvestClientConfig,
    TInvestDataClientConfig,
    TInvestExecClientConfig,
)
from nautilus_trader.adapters.tinvest.factories import (
    TInvestLiveDataClientFactory,
    TInvestLiveExecClientFactory,
)
from nautilus_trader.common.config import InstrumentProviderConfig
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.live.config import LiveDataEngineConfig, LiveExecEngineConfig
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId


# *** Load from environment ***
TINVEST_API_TOKEN = os.getenv("TINVEST_API_TOKEN", "t.your_api_token_here")
USE_SANDBOX = os.getenv("TINVEST_SANDBOX", "true").lower() == "true"
ACCOUNT_ID = os.getenv("TINVEST_ACCOUNT_ID", "TINVEST-1234567890")
# Path to Russian Trusted Root CA certificate (PEM format).
# Required for TLS connection to T-Invest API from within Russia.
# Extracted from libs/invest-java/core/src/main/resources/RussianTrustedRootCA.jks
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))  # examples/live -> examples -> root
_CA_CERT_DEFAULT = os.path.join(
    _PROJECT_ROOT, "crates", "adapters", "tinvest", "certs", "RussianTrustedRootCA.pem",
)
CA_CERT_PATH = os.getenv("TINVEST_CA_CERT_PATH", _CA_CERT_DEFAULT)


async def main():
    # Configure the T-Invest client
    tinvest_config = TInvestClientConfig(
        token=TINVEST_API_TOKEN,
        sandbox=USE_SANDBOX,
        ca_cert_path=CA_CERT_PATH if os.path.exists(CA_CERT_PATH) else None,
    )
    if CA_CERT_PATH and os.path.exists(CA_CERT_PATH):
        print(f"🔒 Using CA cert: {CA_CERT_PATH}")
    else:
        print(f"⚠️  CA cert not found at: {CA_CERT_PATH}")

    # Configure data client
    data_config = TInvestDataClientConfig(
        tinvest=tinvest_config,
        instrument_provider=InstrumentProviderConfig(load_all=True),
    )

    # Configure execution client
    exec_config = TInvestExecClientConfig(
        tinvest=tinvest_config,
        account_id=ACCOUNT_ID,
        instrument_provider=InstrumentProviderConfig(load_all=True),
    )

    # Build the trading node config
    config_node = TradingNodeConfig(
        trader_id=TraderId("TESTER-001"),
        logging=LoggingConfig(log_level="INFO"),
        data_clients={
            TINVEST_VENUE.value: data_config,
        },
        exec_clients={
            TINVEST_VENUE.value: exec_config,
        },
        data_engine=LiveDataEngineConfig(),
        exec_engine=LiveExecEngineConfig(),
    )

    # Build the trading node
    node = TradingNode(config=config_node)

    # Register the T-Invest factory
    node.add_data_client_factory(TINVEST_VENUE.value, TInvestLiveDataClientFactory)
    node.add_exec_client_factory(TINVEST_VENUE.value, TInvestLiveExecClientFactory)

    # Build clients before running
    node.build()

    # Run the node
    try:
        node.run()
        print(f"🚀 T-Invest TradingNode running (sandbox={USE_SANDBOX}, account={ACCOUNT_ID})")
        print("Press Ctrl+C to stop...")
        await asyncio.sleep(3600)
    finally:
        node.dispose()


if __name__ == "__main__":
    asyncio.run(main())
