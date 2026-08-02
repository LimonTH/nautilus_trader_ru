// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! Mappings between T-Invest API enums and Nautilus model types.

use nautilus_model::types::Currency;

/// Venue identifier for T-Invest (MOEX).
pub const TINVEST_VENUE: &str = "TINVEST";

/// Mapping from T-Invest instrument types to Nautilus asset class strings.
pub fn instrument_type_to_asset_class(instrument_type: &str) -> &str {
    match instrument_type {
        "share" => "equity",
        "bond" => "bond",
        "future" => "futures",
        "option" => "option",
        "currency" => "fx",
        "etf" => "etf",
        _ => "equity",
    }
}

/// T-Invest instrument type constants.
pub mod instrument_types {
    pub const SHARE: &str = "share";
    pub const BOND: &str = "bond";
    pub const FUTURE: &str = "future";
    pub const OPTION: &str = "option";
    pub const CURRENCY: &str = "currency";
    pub const ETF: &str = "etf";
}

/// Mapping from T-Invest CandleInterval to Nautilus bar aggregation strings.
pub fn candle_interval_to_bar_spec(interval: i32) -> Option<String> {
    match interval {
        1 => Some("1-MINUTE".to_string()),
        2 => Some("5-MINUTE".to_string()),
        3 => Some("15-MINUTE".to_string()),
        4 => Some("1-HOUR".to_string()),
        5 => Some("1-DAY".to_string()),
        6 => Some("2-MINUTE".to_string()),
        7 => Some("3-MINUTE".to_string()),
        8 => Some("10-MINUTE".to_string()),
        9 => Some("30-MINUTE".to_string()),
        10 => Some("2-HOUR".to_string()),
        11 => Some("4-HOUR".to_string()),
        12 => Some("1-WEEK".to_string()),
        13 => Some("1-MONTH".to_string()),
        _ => None,
    }
}

/// Mapping from Nautilus bar aggregation to T-Invest CandleInterval.
pub fn bar_spec_to_candle_interval(bar_spec: &str) -> Option<i32> {
    match bar_spec {
        "1-MINUTE" => Some(1),
        "2-MINUTE" => Some(6),
        "3-MINUTE" => Some(7),
        "5-MINUTE" => Some(2),
        "10-MINUTE" => Some(8),
        "15-MINUTE" => Some(3),
        "30-MINUTE" => Some(9),
        "1-HOUR" => Some(4),
        "2-HOUR" => Some(10),
        "4-HOUR" => Some(11),
        "1-DAY" => Some(5),
        "1-WEEK" => Some(12),
        "1-MONTH" => Some(13),
        _ => None,
    }
}

/// Mapping from T-Invest OrderDirection to Nautilus order side.
pub fn order_direction_to_order_side(direction: i32) -> &'static str {
    match direction {
        1 => "BUY",
        2 => "SELL",
        _ => "BUY",
    }
}

/// Mapping from Nautilus order side to T-Invest OrderDirection.
pub fn order_side_to_order_direction(side: &str) -> i32 {
    match side {
        "BUY" => 1,  // ORDER_DIRECTION_BUY
        "SELL" => 2, // ORDER_DIRECTION_SELL
        _ => 1,      // BUY
    }
}

/// Mapping from T-Invest OrderType to Nautilus order type string.
pub fn order_type_to_nautilus(order_type: i32) -> &'static str {
    match order_type {
        1 => "LIMIT",  // ORDER_TYPE_LIMIT
        2 => "MARKET", // ORDER_TYPE_MARKET
        3 => "LIMIT",  // ORDER_TYPE_BESTPRICE
        _ => "LIMIT",
    }
}

/// Known currencies available on MOEX.
pub fn known_currencies() -> Vec<Currency> {
    vec![
        Currency::from("RUB"),
        Currency::from("USD"),
        Currency::from("EUR"),
        Currency::from("CNY"),
        Currency::from("GBP"),
        Currency::from("TRY"),
        Currency::from("KZT"),
        Currency::from("BYN"),
    ]
}
