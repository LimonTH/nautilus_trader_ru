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

//! Conversion functions between T-Invest proto types and Nautilus model types.

use nautilus_core::UnixNanos;
use nautilus_model::data::bar::{Bar, BarType};
use nautilus_model::data::quote::QuoteTick;
use nautilus_model::data::trade::TradeTick;
use nautilus_model::enums::AggressorSide;
use nautilus_model::enums::{AssetClass, OptionKind};
use nautilus_model::identifiers::{InstrumentId, Symbol, TradeId, Venue};
use nautilus_model::instruments::any::InstrumentAny;
use nautilus_model::instruments::currency_pair::CurrencyPair;
use nautilus_model::instruments::equity::Equity;
use nautilus_model::instruments::futures_contract::FuturesContract;
use nautilus_model::instruments::option_contract::OptionContract;
use nautilus_model::types::fixed::FIXED_PRECISION;
use nautilus_model::types::{Currency, Money, Price, Quantity};
use prost_types::Timestamp;
use rust_decimal::Decimal;
use tracing::warn;
use ustr::Ustr;

use crate::common::types::{MoneyValue, Quotation, proto_timestamp_to_datetime};
use crate::enums::TINVEST_VENUE;

/// Convert a T-Invest figi/instrument_uid to a Nautilus InstrumentId.
pub fn to_instrument_id(figi: &str) -> InstrumentId {
    InstrumentId::new(Symbol::new(figi), Venue::new(TINVEST_VENUE))
}

/// Convert a T-Invest Quotation to a Nautilus Price.
pub fn quotation_to_price(q: &crate::proto::Quotation, precision: u8) -> Price {
    let decimal = Quotation::from(q).to_decimal();
    Price::new(decimal.to_string().parse::<f64>().unwrap_or(0.0), precision)
}

/// Convert a T-Invest Quotation to a Nautilus Quantity.
pub fn quotation_to_quantity(q: &crate::proto::Quotation, precision: u8) -> Quantity {
    let decimal = Quotation::from(q).to_decimal();
    Quantity::new(decimal.to_string().parse::<f64>().unwrap_or(0.0), precision)
}

/// Convert a T-Invest MoneyValue to a Nautilus Money.
pub fn money_value_to_money(mv: &crate::proto::MoneyValue) -> Money {
    let money_value = MoneyValue::from(mv);
    let decimal = money_value.to_decimal();
    Money::new(
        decimal.to_string().parse::<f64>().unwrap_or(0.0),
        Currency::from(money_value.currency.as_str()),
    )
}

/// Convert a proto Timestamp to Unix nanoseconds.
pub fn timestamp_to_unix_nanos(ts: &Timestamp) -> u64 {
    let dt = proto_timestamp_to_datetime(ts);
    dt.timestamp_nanos_opt().unwrap_or(0) as u64
}

/// Convert a Quotation to rust_decimal::Decimal.
pub fn quotation_to_decimal(q: &crate::proto::Quotation) -> Decimal {
    Quotation::from(q).to_decimal()
}

/// Convert a f64 to a proto Quotation.
///
/// Handles positive and negative values correctly by normalising
/// the units/nano representation so both components have the same sign.
pub fn f64_to_quotation(value: f64) -> crate::proto::Quotation {
    let units = value.trunc() as i64;
    let nano = (value.fract() * 1_000_000_000.0).round() as i32;
    let (units, nano) = if nano < 0 {
        (units - 1, nano + 1_000_000_000)
    } else if units <= 0 && nano > 0 {
        (units + 1, nano - 1_000_000_000)
    } else {
        (units, nano)
    };
    crate::proto::Quotation { units, nano }
}

/// Convert Unix nanos to a proto Timestamp.
pub fn unix_nanos_to_timestamp(nanos: u64) -> Timestamp {
    Timestamp {
        seconds: (nanos / 1_000_000_000) as i64,
        nanos: (nanos % 1_000_000_000) as i32,
    }
}

/// Determine the price precision from a Quotation (min_price_increment).
///
/// Clamps the result to [`FIXED_PRECISION`] and logs a warning if the
/// raw precision exceeds the maximum allowed value.
pub fn price_increment_to_precision(increment: &crate::proto::Quotation) -> u8 {
    let decimal = Quotation::from(increment).to_decimal();
    let precision_str = decimal.to_string();
    let precision: u8 = if let Some(dot_pos) = precision_str.find('.') {
        let fractional = &precision_str[dot_pos + 1..];
        let trimmed = fractional.trim_end_matches('0');
        trimmed.len() as u8
    } else {
        0
    };

    if precision > FIXED_PRECISION {
        warn!(
            "price_increment_to_precision: computed precision {} exceeds FIXED_PRECISION ({}), \
             clamping. Quotation(units={}, nano={}), decimal_str={}",
            precision, FIXED_PRECISION, increment.units, increment.nano, precision_str,
        );
        FIXED_PRECISION
    } else {
        precision
    }
}

/// Convert a T-Invest Share proto to a nautilus Equity instrument.
pub fn convert_share_to_instrument(share: &crate::proto::Share, ts_init: u64) -> InstrumentAny {
    let instrument_id = to_instrument_id(&share.figi);
    let raw_symbol = Symbol::new(&share.ticker);
    let currency = Currency::from(share.currency.as_str());
    let price_precision = share
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(2);
    let price_increment = share
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.01, 2));
    let lot_size = Some(Quantity::new(share.lot as f64, 0));
    let isin = if share.isin.is_empty() {
        None
    } else {
        Some(Ustr::from(&share.isin))
    };
    let ts = UnixNanos::from(ts_init);

    let equity = Equity::new(
        instrument_id,
        raw_symbol,
        isin,
        currency,
        price_precision,
        price_increment,
        lot_size,
        None, // max_quantity
        None, // min_quantity
        None, // max_price
        None, // min_price
        None, // margin_init
        None, // margin_maint
        None, // maker_fee
        None, // taker_fee
        None, // tick_scheme
        None, // info
        ts,
        ts,
    );

    equity.into()
}

/// Convert a T-Invest Bond proto to a nautilus Equity instrument (generic bond representation).
pub fn convert_bond_to_instrument(bond: &crate::proto::Bond, ts_init: u64) -> InstrumentAny {
    let instrument_id = to_instrument_id(&bond.figi);
    let raw_symbol = Symbol::new(&bond.ticker);
    let currency = Currency::from(bond.currency.as_str());
    let price_precision = bond
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(2);
    let price_increment = bond
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.01, 2));
    let lot_size = Some(Quantity::new(bond.lot as f64, 0));
    let isin = if bond.isin.is_empty() {
        None
    } else {
        Some(Ustr::from(&bond.isin))
    };
    let ts = UnixNanos::from(ts_init);

    let equity = Equity::new(
        instrument_id,
        raw_symbol,
        isin,
        currency,
        price_precision,
        price_increment,
        lot_size,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        ts,
        ts,
    );

    equity.into()
}

/// Convert a T-Invest Future proto to a nautilus FuturesContract.
pub fn convert_future_to_instrument(future: &crate::proto::Future, ts_init: u64) -> InstrumentAny {
    let instrument_id = to_instrument_id(&future.figi);
    let raw_symbol = Symbol::new(&future.ticker);
    let underlying = if future.basic_asset.is_empty() {
        Ustr::from(&future.ticker)
    } else {
        Ustr::from(&future.basic_asset)
    };
    let currency = Currency::from(future.currency.as_str());
    let price_precision = future
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(2);
    let price_increment = future
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.01, 2));
    let lot_size = Quantity::new(future.lot as f64, 0);
    let multiplier = Quantity::new(1.0, 0);
    let expiration_ns = future
        .expiration_date
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .unwrap_or(0);
    let ts = UnixNanos::from(ts_init);

    let futures_contract = FuturesContract::new(
        instrument_id,
        raw_symbol,
        nautilus_model::enums::AssetClass::Equity,
        None, // exchange
        underlying,
        UnixNanos::default(),
        UnixNanos::from(expiration_ns),
        currency,
        price_precision,
        price_increment,
        multiplier,
        lot_size,
        None, // max_quantity
        None, // min_quantity
        None, // max_price
        None, // min_price
        None, // margin_init
        None, // margin_maint
        None, // maker_fee
        None, // taker_fee
        None, // tick_scheme
        None, // info
        ts,
        ts,
    );

    futures_contract.into()
}

/// Convert a T-Invest Currency proto to a nautilus CurrencyPair.
pub fn convert_currency_to_instrument(
    currency: &crate::proto::Currency,
    ts_init: u64,
) -> InstrumentAny {
    let instrument_id = to_instrument_id(&currency.figi);
    let raw_symbol = Symbol::new(&currency.ticker);
    let iso_currency = if currency.iso_currency_name.is_empty() {
        "RUB"
    } else {
        &currency.iso_currency_name
    };
    let base_currency = Currency::from(iso_currency);
    let quote_currency = Currency::from("RUB");
    let price_precision = currency
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(4);
    let price_increment = currency
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.0001, 4));
    let lot_size = Some(Quantity::new(currency.lot as f64, 0));
    let size_increment = Quantity::new(1.0, 0);
    let multiplier = Some(Quantity::new(1.0, 0));
    let ts = UnixNanos::from(ts_init);

    let pair = CurrencyPair::new(
        instrument_id,
        raw_symbol,
        base_currency,
        quote_currency,
        price_precision,
        0, // size_precision
        price_increment,
        size_increment,
        multiplier,
        lot_size,
        None, // max_quantity
        None, // min_quantity
        None, // max_notional
        None, // min_notional
        None, // max_price
        None, // min_price
        None, // margin_init
        None, // margin_maint
        None, // maker_fee
        None, // taker_fee
        None, // tick_scheme
        None, // info
        ts,
        ts,
    );

    pair.into()
}

/// Convert a T-Invest Etf proto to a nautilus Equity instrument.
pub fn convert_etf_to_instrument(etf: &crate::proto::Etf, ts_init: u64) -> InstrumentAny {
    let instrument_id = to_instrument_id(&etf.figi);
    let raw_symbol = Symbol::new(&etf.ticker);
    let currency = Currency::from(etf.currency.as_str());
    let price_precision = etf
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(2);
    let price_increment = etf
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.01, 2));
    let lot_size = Some(Quantity::new(etf.lot as f64, 0));
    let ts = UnixNanos::from(ts_init);

    let equity = Equity::new(
        instrument_id,
        raw_symbol,
        None, // isin
        currency,
        price_precision,
        price_increment,
        lot_size,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        ts,
        ts,
    );

    equity.into()
}

/// Convert a T-Invest Option proto to a nautilus OptionContract.
pub fn convert_option_to_instrument(option: &crate::proto::Option, ts_init: u64) -> InstrumentAny {
    // Use uid as the symbol (Option proto has no figi field)
    let instrument_id = to_instrument_id(&option.uid);
    let raw_symbol = Symbol::new(&option.ticker);
    let underlying = if option.basic_asset.is_empty() {
        Ustr::from(&option.ticker)
    } else {
        Ustr::from(&option.basic_asset)
    };
    let currency = Currency::from(option.currency.as_str());
    let price_precision = option
        .min_price_increment
        .as_ref()
        .map(price_increment_to_precision)
        .unwrap_or(2);
    let price_increment = option
        .min_price_increment
        .as_ref()
        .map(|inc| quotation_to_price(inc, price_precision))
        .unwrap_or_else(|| Price::new(0.01, 2));
    let lot_size = Quantity::new(option.lot as f64, 0);
    let multiplier = option
        .basic_asset_size
        .as_ref()
        .map(|q| {
            let decimal = Quotation::from(q).to_decimal();
            Quantity::new(decimal.to_string().parse::<f64>().unwrap_or(1.0), 0)
        })
        .unwrap_or_else(|| Quantity::new(1.0, 0));

    // Map OptionDirection → OptionKind
    // OPTION_DIRECTION_PUT = 1, OPTION_DIRECTION_CALL = 2
    let option_kind = match option.direction {
        1 => OptionKind::Put,
        2 => OptionKind::Call,
        _ => OptionKind::Call, // default
    };

    // Strike price from MoneyValue
    let strike_price = option
        .strike_price
        .as_ref()
        .map(|mv| {
            let mv = MoneyValue::from(mv);
            let decimal = mv.to_decimal();
            // Strike price precision: use price_precision
            Price::new(
                decimal.to_string().parse::<f64>().unwrap_or(0.0),
                price_precision,
            )
        })
        .unwrap_or_else(|| Price::zero(price_precision));

    let activation_ns = option
        .first_trade_date
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .unwrap_or(0);

    let expiration_ns = option
        .expiration_date
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .unwrap_or(0);

    let exchange = if option.exchange.is_empty() {
        None
    } else {
        Some(Ustr::from(&option.exchange))
    };

    let ts = UnixNanos::from(ts_init);

    let option_contract = OptionContract::new(
        instrument_id,
        raw_symbol,
        AssetClass::Equity,
        exchange,
        underlying,
        option_kind,
        strike_price,
        currency,
        UnixNanos::from(activation_ns),
        UnixNanos::from(expiration_ns),
        price_precision,
        price_increment,
        multiplier,
        lot_size,
        None, // max_quantity
        None, // min_quantity
        None, // max_price
        None, // min_price
        None, // margin_init
        None, // margin_maint
        None, // maker_fee
        None, // taker_fee
        None, // tick_scheme
        None, // info
        ts,
        ts,
    );

    option_contract.into()
}

/// Convert a T-Invest Candle to bar data components.
/// Returns (open, high, low, close, volume, timestamp_nanos).
pub fn convert_candle_to_bar_data(
    candle: &crate::proto::HistoricCandle,
) -> (Price, Price, Price, Price, Quantity, u64) {
    let precision = 2;
    let open = candle
        .open
        .as_ref()
        .map(|q| quotation_to_price(q, precision))
        .unwrap_or_else(|| Price::zero(precision));
    let high = candle
        .high
        .as_ref()
        .map(|q| quotation_to_price(q, precision))
        .unwrap_or_else(|| Price::zero(precision));
    let low = candle
        .low
        .as_ref()
        .map(|q| quotation_to_price(q, precision))
        .unwrap_or_else(|| Price::zero(precision));
    let close = candle
        .close
        .as_ref()
        .map(|q| quotation_to_price(q, precision))
        .unwrap_or_else(|| Price::zero(precision));
    let volume = Quantity::new(candle.volume as f64, 0);
    let ts = candle
        .time
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .unwrap_or(0);

    (open, high, low, close, volume, ts)
}

/// Convert a T-Invest Trade to trade tick data.
/// Returns (price, quantity, timestamp_nanos, is_buyer_side).
pub fn convert_trade_to_trade_data(trade: &crate::proto::Trade) -> (Price, Quantity, u64, bool) {
    let precision = 2;
    let price = trade
        .price
        .as_ref()
        .map(|q| quotation_to_price(q, precision))
        .unwrap_or_else(|| Price::zero(precision));
    let quantity = Quantity::new(trade.quantity as f64, 0);
    let ts = trade
        .time
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .unwrap_or(0);
    let side = trade.direction == 1;

    (price, quantity, ts, side)
}

/// Convert OrderState execution report status to nautilus OrderStatus string.
pub fn order_status_from_tinvest(status: i32) -> &'static str {
    match status {
        1 => "FILLED",
        2 => "REJECTED",
        3 => "CANCELED",
        4 => "ACCEPTED",
        5 => "PARTIALLY_FILLED",
        _ => "ACCEPTED",
    }
}

/// Convert T-Invest OrderDirection to nautilus OrderSide string.
pub fn order_side_from_tinvest(direction: i32) -> &'static str {
    match direction {
        1 => "BUY",
        2 => "SELL",
        _ => "BUY",
    }
}

/// Convert nautilus OrderSide to T-Invest OrderDirection.
pub fn order_side_to_tinvest(side: &str) -> i32 {
    match side {
        "BUY" => 1,
        "SELL" => 2,
        _ => 1,
    }
}

/// Convert nautilus OrderType to T-Invest OrderType.
///
/// Supports the T-Invest `ORDER_TYPE_BESTPRICE` ("best price") order type.
/// In Nautilus a best-price order is expressed as a market order; when the
/// caller explicitly passes `"BESTPRICE"` we map to `ORDER_TYPE_BESTPRICE`.
pub fn order_type_to_tinvest(order_type: &str) -> i32 {
    match order_type {
        "LIMIT" => 1,
        "MARKET" => 2,
        "BESTPRICE" => 3,
        _ => 1,
    }
}

/// Convert T-Invest OrderType integer to nautilus OrderType string.
///
/// `ORDER_TYPE_BESTPRICE` has no direct Nautilus equivalent and behaves like
/// a market order (aggressive fill at the best available price), so it is
/// mapped to `"MARKET"`.
pub fn order_type_from_tinvest(order_type: i32) -> &'static str {
    match order_type {
        1 => "LIMIT",
        2 => "MARKET",
        3 => "MARKET",
        _ => "LIMIT",
    }
}

/// Convert an OrderState proto to an OrderStatusReport.
///
/// Maps T-Invest order fields to the nautilus order status report structure.
/// Not all fields can be mapped 1:1 — uses sensible defaults where information
/// is missing in the T-Invest response.
pub fn convert_order_state_to_report(
    order: &crate::proto::OrderState,
    account_id: nautilus_model::identifiers::AccountId,
    ts_init: UnixNanos,
) -> nautilus_model::reports::OrderStatusReport {
    use nautilus_model::enums::{OrderSide, OrderStatus, OrderType, TimeInForce};
    use nautilus_model::identifiers::{ClientOrderId, VenueOrderId};
    use nautilus_model::types::{Price, Quantity};

    let instrument_id = to_instrument_id(&order.figi);
    let venue_order_id = VenueOrderId::from(order.order_id.as_str());
    let client_order_id = if order.order_request_id.is_empty() {
        None
    } else {
        Some(ClientOrderId::from(order.order_request_id.as_str()))
    };

    let order_side = match order.direction {
        1 => OrderSide::Buy,
        2 => OrderSide::Sell,
        _ => OrderSide::Buy,
    };

    let order_type = match order.order_type {
        1 => OrderType::Limit,
        2 => OrderType::Market,
        _ => OrderType::Limit,
    };

    let order_status = match order.execution_report_status {
        1 => OrderStatus::Filled,
        2 => OrderStatus::Rejected,
        3 => OrderStatus::Canceled,
        4 => OrderStatus::Accepted,
        5 => OrderStatus::PartiallyFilled,
        _ => OrderStatus::Accepted,
    };

    let quantity = Quantity::new(order.lots_requested as f64, 0);
    let filled_qty = Quantity::new(order.lots_executed as f64, 0);

    let price = order.initial_security_price.as_ref().map(|mv| {
        let mv = MoneyValue::from(mv);
        Price::new(mv.to_decimal().to_string().parse::<f64>().unwrap_or(0.0), 2)
    });

    let ts_accepted = order
        .order_date
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .map(UnixNanos::from)
        .unwrap_or(ts_init);

    let avg_px = order
        .average_position_price
        .as_ref()
        .map(|mv| MoneyValue::from(mv).to_decimal());

    nautilus_model::reports::OrderStatusReport::new(
        account_id,
        instrument_id,
        client_order_id,
        venue_order_id,
        order_side,
        order_type,
        TimeInForce::Gtc, // T-Invest OrderState doesn't expose time_in_force
        order_status,
        quantity,
        filled_qty,
        ts_accepted,
        ts_init,
        ts_init,
        None,
    )
    .with_price(price.unwrap_or_else(|| Price::zero(2)))
    .with_avg_px(avg_px.unwrap_or_default())
}

/// Convert an OperationItem proto to a Vec of FillReports.
///
/// One OperationItem may contain multiple trades (OperationItemTrade).
/// Each trade becomes a separate FillReport.
pub fn convert_operation_item_to_fill_reports(
    op: &crate::proto::OperationItem,
    account_id: nautilus_model::identifiers::AccountId,
    ts_init: UnixNanos,
) -> Vec<nautilus_model::reports::FillReport> {
    use nautilus_model::enums::{LiquiditySide, OrderSide};
    use nautilus_model::identifiers::{TradeId, VenueOrderId};
    use nautilus_model::types::{Currency, Money, Price, Quantity};

    let instrument_id = to_instrument_id(&op.figi);
    let venue_order_id = VenueOrderId::from(op.id.as_str());

    let payment_mv = op.payment.as_ref().map(MoneyValue::from);
    let order_side = payment_mv
        .as_ref()
        .map(|mv| {
            if mv.to_decimal() >= rust_decimal::Decimal::ZERO {
                OrderSide::Buy
            } else {
                OrderSide::Sell
            }
        })
        .unwrap_or(OrderSide::Buy);

    let commission = op
        .commission
        .as_ref()
        .map(|mv| {
            let mv = MoneyValue::from(mv);
            Money::new(
                mv.to_decimal().to_string().parse::<f64>().unwrap_or(0.0),
                Currency::from(mv.currency.as_str()),
            )
        })
        .unwrap_or_else(|| Money::new(0.0, Currency::RUB()));

    let ts_event = op
        .date
        .as_ref()
        .map(timestamp_to_unix_nanos)
        .map(UnixNanos::from)
        .unwrap_or(ts_init);

    let mut reports = Vec::new();

    // If there are trades, create individual fill reports for each trade
    if let Some(ref trades_info) = op.trades_info {
        for trade in &trades_info.trades {
            // Skip zero-quantity trades (not valid fills)
            if trade.quantity <= 0 {
                continue;
            }
            let trade_id = TradeId::from(trade.num.as_str());
            let last_qty = Quantity::new(trade.quantity as f64, 0);
            let last_px = trade
                .price
                .as_ref()
                .map(|mv| {
                    let mv = MoneyValue::from(mv);
                    Price::new(mv.to_decimal().to_string().parse::<f64>().unwrap_or(0.0), 2)
                })
                .unwrap_or_else(|| Price::zero(2));

            let report = nautilus_model::reports::FillReport::new(
                account_id,
                instrument_id,
                venue_order_id,
                trade_id,
                order_side,
                last_qty,
                last_px,
                commission,
                LiquiditySide::Taker,
                None,
                None,
                ts_event,
                ts_init,
                None,
            );
            reports.push(report);
        }
    }

    // If no trade details available, create one report from the operation itself
    if reports.is_empty() && op.quantity > 0 {
        let trade_id = TradeId::from(op.id.as_str());
        let last_qty = Quantity::new(op.quantity as f64, 0);
        let last_px = op
            .price
            .as_ref()
            .map(|mv| {
                let mv = MoneyValue::from(mv);
                Price::new(mv.to_decimal().to_string().parse::<f64>().unwrap_or(0.0), 2)
            })
            .unwrap_or_else(|| Price::zero(2));

        let report = nautilus_model::reports::FillReport::new(
            account_id,
            instrument_id,
            venue_order_id,
            trade_id,
            order_side,
            last_qty,
            last_px,
            commission,
            LiquiditySide::Taker,
            None,
            None,
            ts_event,
            ts_init,
            None,
        );
        reports.push(report);
    }

    reports
}

/// Convert a PositionsSecurities proto to a PositionStatusReport.
pub fn convert_security_position_to_report(
    sec: &crate::proto::PositionsSecurities,
    account_id: nautilus_model::identifiers::AccountId,
    ts_init: UnixNanos,
) -> nautilus_model::reports::PositionStatusReport {
    use nautilus_model::enums::PositionSideSpecified;
    use nautilus_model::identifiers::PositionId;
    use nautilus_model::types::Quantity;

    let instrument_id = to_instrument_id(&sec.figi);
    let position_side = match sec.balance.cmp(&0) {
        std::cmp::Ordering::Greater => PositionSideSpecified::Long,
        std::cmp::Ordering::Less => PositionSideSpecified::Short,
        std::cmp::Ordering::Equal => PositionSideSpecified::Flat,
    };
    let quantity = Quantity::new(sec.balance.unsigned_abs() as f64, 0);
    let venue_position_id = if sec.position_uid.is_empty() {
        None
    } else {
        Some(PositionId::from(sec.position_uid.as_str()))
    };

    nautilus_model::reports::PositionStatusReport::new(
        account_id,
        instrument_id,
        position_side,
        quantity,
        ts_init,
        ts_init,
        None, // report_id
        venue_position_id,
        None, // avg_px_open
    )
}

/// Convert a PositionsFutures proto to a PositionStatusReport.
pub fn convert_futures_position_to_report(
    fut: &crate::proto::PositionsFutures,
    account_id: nautilus_model::identifiers::AccountId,
    ts_init: UnixNanos,
) -> nautilus_model::reports::PositionStatusReport {
    use nautilus_model::enums::PositionSideSpecified;
    use nautilus_model::identifiers::PositionId;
    use nautilus_model::types::Quantity;

    let instrument_id = to_instrument_id(&fut.figi);
    // For futures, positive balance = long, negative = short
    let position_side = match fut.balance.cmp(&0) {
        std::cmp::Ordering::Greater => PositionSideSpecified::Long,
        std::cmp::Ordering::Less => PositionSideSpecified::Short,
        std::cmp::Ordering::Equal => PositionSideSpecified::Flat,
    };
    let quantity = Quantity::new(fut.balance.unsigned_abs() as f64, 0);
    let venue_position_id = if fut.position_uid.is_empty() {
        None
    } else {
        Some(PositionId::from(fut.position_uid.as_str()))
    };

    nautilus_model::reports::PositionStatusReport::new(
        account_id,
        instrument_id,
        position_side,
        quantity,
        ts_init,
        ts_init,
        None,
        venue_position_id,
        None,
    )
}

// Stream-data → Nautilus event conversion helpers

/// Convert a T-Invest proto [`Trade`](crate::proto::Trade) to a Nautilus [`TradeTick`].
pub fn convert_proto_trade_to_tick(
    trade: &crate::proto::Trade,
    instrument_id: InstrumentId,
    ts_init: UnixNanos,
) -> TradeTick {
    let price = quotation_to_price(&trade.price.unwrap_or_default(), 2);
    let size = Quantity::new(trade.quantity as f64, 0);
    let aggressor_side = match trade.direction {
        1 => AggressorSide::Buyer,
        2 => AggressorSide::Seller,
        _ => AggressorSide::NoAggressor,
    };
    let trade_id = TradeId::new(&format!(
        "{}-{}",
        trade.figi,
        trade.time.as_ref().map_or(0, |t| t.seconds)
    ));
    let ts_event = trade
        .time
        .as_ref()
        .map_or(ts_init, |t| UnixNanos::from(timestamp_to_unix_nanos(t)));

    TradeTick::new(
        instrument_id,
        price,
        size,
        aggressor_side,
        trade_id,
        ts_event,
        ts_init,
    )
}

/// Convert a T-Invest proto [`Candle`](crate::proto::Candle) to a Nautilus [`Bar`].
pub fn convert_proto_candle_to_bar(
    candle: &crate::proto::Candle,
    bar_type: BarType,
    ts_init: UnixNanos,
) -> Bar {
    let open = quotation_to_price(&candle.open.unwrap_or_default(), 2);
    let high = quotation_to_price(&candle.high.unwrap_or_default(), 2);
    let low = quotation_to_price(&candle.low.unwrap_or_default(), 2);
    let close = quotation_to_price(&candle.close.unwrap_or_default(), 2);
    let volume = Quantity::new(candle.volume as f64, 0);
    let ts_event = candle
        .time
        .as_ref()
        .map_or(ts_init, |t| UnixNanos::from(timestamp_to_unix_nanos(t)));

    Bar::new(bar_type, open, high, low, close, volume, ts_event, ts_init)
}

/// Convert a T-Invest proto [`OrderBook`](crate::proto::OrderBook) to a Nautilus [`QuoteTick`].
///
/// Extracts the best bid and ask from the order book.
pub fn convert_proto_orderbook_to_quote_tick(
    orderbook: &crate::proto::OrderBook,
    instrument_id: InstrumentId,
    ts_init: UnixNanos,
) -> Option<QuoteTick> {
    let best_bid = orderbook.bids.first()?;
    let best_ask = orderbook.asks.first()?;

    let bid_price = quotation_to_price(&best_bid.price.unwrap_or_default(), 2);
    let ask_price = quotation_to_price(&best_ask.price.unwrap_or_default(), 2);
    let bid_size = Quantity::new(best_bid.quantity as f64, 0);
    let ask_size = Quantity::new(best_ask.quantity as f64, 0);
    let ts_event = orderbook
        .time
        .as_ref()
        .map_or(ts_init, |t| UnixNanos::from(timestamp_to_unix_nanos(t)));

    Some(QuoteTick::new(
        instrument_id,
        bid_price,
        ask_price,
        bid_size,
        ask_size,
        ts_event,
        ts_init,
    ))
}
