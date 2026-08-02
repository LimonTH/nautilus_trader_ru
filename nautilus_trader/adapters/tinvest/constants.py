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
T-Invest adapter constants.

These are internal-only constants shared between data, execution, and
providers modules.  They are NOT re-exported via the public ``__init__.py``.
"""

from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.objects import Price


# ──────────────────────────────────────────────────────────────────────────────
# Candle / Bar mapping (data.py)
# ──────────────────────────────────────────────────────────────────────────────

# Map T-Invest candle interval to BarSpec string (LAST price type for candles)
_CANDLE_INTERVAL_MAP: dict[int, str] = {
    1: "1-MINUTE-LAST",
    2: "5-MINUTE-LAST",
    3: "15-MINUTE-LAST",
    4: "1-HOUR-LAST",
    5: "1-DAY-LAST",
    6: "2-MINUTE-LAST",
    7: "3-MINUTE-LAST",
    8: "10-MINUTE-LAST",
    9: "30-MINUTE-LAST",
    10: "2-HOUR-LAST",
    11: "4-HOUR-LAST",
    12: "1-WEEK-LAST",
    13: "1-MONTH-LAST",
}

# Reverse map from BarSpec string to T-Invest candle interval
_BAR_SPEC_TO_INTERVAL: dict[str, int] = {v: k for k, v in _CANDLE_INTERVAL_MAP.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Execution: direction / status / order type (execution.py)
# ──────────────────────────────────────────────────────────────────────────────

# Map T-Invest direction to nautilus OrderSide
_TINVEST_DIRECTION_TO_SIDE = {
    1: OrderSide.BUY,
    2: OrderSide.SELL,
}

# Map T-Invest execution_report_status to nautilus OrderStatus
_TINVEST_STATUS_TO_ORDER_STATUS = {
    0: OrderStatus.INITIALIZED,
    1: OrderStatus.FILLED,
    2: OrderStatus.REJECTED,
    3: OrderStatus.CANCELED,
    4: OrderStatus.ACCEPTED,
    5: OrderStatus.PARTIALLY_FILLED,
    6: OrderStatus.PENDING_CANCEL,
    7: OrderStatus.EXPIRED,
}

# Map T-Invest order_type to nautilus OrderType
# ORDER_TYPE_BESTPRICE (3) has no direct Nautilus equivalent; it behaves like
# a market order (aggressive fill at the best available price).
_TINVEST_ORDER_TYPE = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.MARKET,
}

# Nautilus order types that are routed to T-Invest PostStopOrder (F3)
_STOP_ORDER_TYPES = {
    OrderType.STOP_MARKET,
    OrderType.STOP_LIMIT,
    OrderType.MARKET_IF_TOUCHED,
    OrderType.LIMIT_IF_TOUCHED,
}


# ──────────────────────────────────────────────────────────────────────────────
# Providers: instrument mapping / price defaults (providers.py)
# ──────────────────────────────────────────────────────────────────────────────

# Map T-Invest instrument_type → nautilus AssetClass enum
_INSTRUMENT_TYPE_TO_ASSET_CLASS: dict[str, AssetClass] = {
    "share": AssetClass.EQUITY,
    "bond": AssetClass.DEBT,
    "etf": AssetClass.EQUITY,
    "future": AssetClass.INDEX,
    "option": AssetClass.EQUITY,
    "currency": AssetClass.FX,
}

# Default price precision / increment for T-Invest instruments.
# Russian equities trade in RUB with 2 decimal places (copecks).
_DEFAULT_PRICE_PRECISION = 2
_DEFAULT_PRICE_INCREMENT = Price.from_str("0.01")

# The maximum fixed-point precision from the Rust layer.
# Matches FIXED_PRECISION in high-precision mode (16).
_MAX_PRECISION = 16
