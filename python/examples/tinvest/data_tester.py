#!/usr/bin/env python3
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

import argparse
import os

import pandas as pd

from nautilus_trader.adapters.tinvest import TINVEST
from nautilus_trader.adapters.tinvest import TInvestClientConfig
from nautilus_trader.adapters.tinvest import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest import TInvestLiveDataClientFactory
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.test_kit.strategies.tester_data import DataTester
from nautilus_trader.test_kit.strategies.tester_data import DataTesterConfig


# *** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***

parser = argparse.ArgumentParser(description="T-Invest Data Tester")
parser.add_argument(
    "--sandbox",
    action="store_true",
    help="Use T-Invest sandbox environment",
)
parser.add_argument(
    "--instrument",
    type=str,
    default="BBG004730N88.TINVEST",
    help="Instrument ID (FIGI.TINVEST) — default: SBER",
)
parser.add_argument(
    "--trader-id",
    type=str,
    default="TESTER-001",
    help="Trader ID for the node",
)
parser.add_argument(
    "--run",
    action="store_true",
    help="Connect and run the data tester node",
)
args = parser.parse_args()

# Determine token from environment
if args.sandbox:
    token = os.environ.get("TINVEST_SANDBOX_TOKEN", "")
else:
    token = os.environ.get("TINVEST_API_TOKEN", "")

if not token:
    env_var = "TINVEST_SANDBOX_TOKEN" if args.sandbox else "TINVEST_API_TOKEN"
    raise ValueError(
        f"Token not found. Set {env_var} environment variable.",
    )

# Build instrument ID
instrument_id = InstrumentId.from_str(args.instrument)

# Configure the trading node
config_node = TradingNodeConfig(
    trader_id=TraderId(args.trader_id),
    logging=LoggingConfig(
        log_level="INFO",
        use_pyo3=True,
    ),
    exec_engine=LiveExecEngineConfig(
        reconciliation=False,  # Not applicable for data-only tester
    ),
    data_clients={
        TINVEST: TInvestDataClientConfig(
            tinvest=TInvestClientConfig(
                token=token,
                sandbox=args.sandbox,
            ),
        ),
    },
    timeout_connection=20.0,
    timeout_disconnection=5.0,
    timeout_post_stop=5.0,
)

# Instantiate the node with a configuration
node = TradingNode(config=config_node)

# Configure and initialize the tester
config_tester = DataTesterConfig(
    client_id=ClientId.from_str(TINVEST),
    instrument_ids=[instrument_id],
    bar_types=[
        BarType.from_str(f"{instrument_id.value}-1-MINUTE-LAST-EXTERNAL"),
    ],
    subscribe_book_deltas=True,
    subscribe_quotes=True,
    subscribe_trades=True,
    request_instruments=True,
    request_trades=True,
    request_bars=True,
    request_book_snapshot=True,
    requests_start_delta=pd.Timedelta(minutes=60),
    manage_book=True,
    log_data=True,
)
tester = DataTester(config=config_tester)

node.trader.add_actor(tester)

# Register client factory with the node
node.add_data_client_factory(TINVEST, TInvestLiveDataClientFactory)
node.build()

if not args.run:
    print("Built T-Invest data tester node. Pass --run to connect.")
else:
    # Stop and dispose of the node with SIGINT/CTRL+C
    if __name__ == "__main__":
        try:
            node.run()
        finally:
            node.dispose()
