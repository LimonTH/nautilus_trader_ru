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
from decimal import Decimal

from nautilus_trader.adapters.tinvest import TINVEST
from nautilus_trader.adapters.tinvest import TInvestClientConfig
from nautilus_trader.adapters.tinvest import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest import TInvestLiveDataClientFactory
from nautilus_trader.adapters.tinvest import TInvestLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.strategies.tester_exec import ExecTester
from nautilus_trader.test_kit.strategies.tester_exec import ExecTesterConfig


# *** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***

parser = argparse.ArgumentParser(description="T-Invest Execution Tester")
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
    "--account-id",
    type=str,
    default="TINVEST-001",
    help="T-Invest account ID",
)
parser.add_argument(
    "--quantity",
    type=str,
    default="1",
    help="Order quantity in lots (integer) — default: 1",
)
parser.add_argument(
    "--trader-id",
    type=str,
    default="TESTER-001",
    help="Trader ID for the node",
)
parser.add_argument(
    "--bestprice",
    action="store_true",
    help="Use T-Invest ORDER_TYPE_BESTPRICE for MARKET orders",
)
parser.add_argument(
    "--run",
    action="store_true",
    help="Connect and run the exec tester node",
)
parser.add_argument(
    "--live-orders",
    action="store_true",
    help="Send real orders (disable dry-run mode)",
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

# T-Invest trades in lots — quantity is integer number of lots
order_qty = Decimal(args.quantity)

# Configure the trading node
config_node = TradingNodeConfig(
    trader_id=TraderId(args.trader_id),
    logging=LoggingConfig(
        log_level="INFO",
        use_pyo3=True,
    ),
    exec_engine=LiveExecEngineConfig(
        reconciliation=True,
        reconciliation_instrument_ids=[instrument_id],
        open_check_interval_secs=5.0,
        open_check_open_only=False,
        position_check_interval_secs=60,
        graceful_shutdown_on_exception=True,
    ),
    data_clients={
        TINVEST: TInvestDataClientConfig(
            tinvest=TInvestClientConfig(
                token=token,
                sandbox=args.sandbox,
            ),
            instrument_provider=InstrumentProviderConfig(
                load_all=False,
                load_ids=frozenset([instrument_id]),
            ),
        ),
    },
    exec_clients={
        TINVEST: TInvestExecClientConfig(
            tinvest=TInvestClientConfig(
                token=token,
                sandbox=args.sandbox,
            ),
            account_id=args.account_id,
            use_bestprice_orders=args.bestprice,
            instrument_provider=InstrumentProviderConfig(
                load_all=False,
                load_ids=frozenset([instrument_id]),
            ),
        ),
    },
    timeout_connection=20.0,
    timeout_reconciliation=10.0,
    timeout_portfolio=10.0,
    timeout_disconnection=10.0,
    timeout_post_stop=5.0,
)

# Instantiate the node with a configuration
node = TradingNode(config=config_node)

# Configure the exec tester strategy
config_tester = ExecTesterConfig(
    strategy_id="TInvestExecTester",
    instrument_id=instrument_id,
    client_id=ClientId.from_str(TINVEST),
    external_order_claims=[instrument_id],
    order_qty=order_qty,
    subscribe_quotes=True,
    subscribe_trades=True,
    open_position_on_start_qty=order_qty if args.live_orders else None,
    dry_run=not args.live_orders,
    log_data=True,
)

# Instantiate the strategy
strategy = ExecTester(config=config_tester)

# Add strategy to the node
node.trader.add_strategy(strategy)

# Register client factories with the node
node.add_data_client_factory(TINVEST, TInvestLiveDataClientFactory)
node.add_exec_client_factory(TINVEST, TInvestLiveExecClientFactory)
node.build()

if not args.run:
    print("Built T-Invest exec tester node. Pass --run to connect.")
else:
    # Stop and dispose of the node with SIGINT/CTRL+C
    if __name__ == "__main__":
        try:
            node.run()
        finally:
            node.dispose()
