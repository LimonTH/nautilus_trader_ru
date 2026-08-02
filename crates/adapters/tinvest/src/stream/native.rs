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

//! Native gRPC streaming wrappers for PyO3 integration.
//!
//! Each stream type spawns a dedicated [`std::thread`] with its own
//! [`tokio::runtime::Runtime`] and delivers converted data through a
//! Python-aware callback that acquires the GIL.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3::types::PyDict;
use tokio::runtime::Runtime;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

use crate::client::TInvestGrpcClient;
use crate::proto::{
    MarketDataRequest, MarketDataResponse, OrderBookInstrument, OrderStateStreamRequest,
    OrderStateStreamResponse, PortfolioStreamRequest, PortfolioStreamResponse,
    PositionsStreamRequest, PositionsStreamResponse, SubscribeInfoRequest,
    SubscribeOrderBookRequest, SubscribeTradesRequest, SubscriptionAction, TradeInstrument,
    market_data_request,
};

// -------------------------------------------------------------------------------------------
// Helper: convert proto responses to Python dicts (called from within GIL)
// -------------------------------------------------------------------------------------------

fn money_value_to_dict<'py>(
    py: Python<'py>,
    mv: &crate::proto::MoneyValue,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("currency", &mv.currency)?;
    d.set_item("units", mv.units)?;
    d.set_item("nano", mv.nano)?;
    Ok(d)
}

fn quotation_to_dict<'py>(
    py: Python<'py>,
    q: &crate::proto::Quotation,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("units", q.units)?;
    d.set_item("nano", q.nano)?;
    Ok(d)
}

fn market_data_response_to_dict<'py>(
    py: Python<'py>,
    response: &MarketDataResponse,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    if let Some(ref payload) = response.payload {
        match payload {
            crate::proto::market_data_response::Payload::Trade(trade) => {
                d.set_item("payload_type", "trade")?;
                d.set_item("figi", &trade.figi)?;
                d.set_item("direction", trade.direction)?;
                d.set_item("quantity", trade.quantity)?;
                d.set_item("instrument_uid", &trade.instrument_uid)?;
                if let Some(ref price) = trade.price {
                    d.set_item("price", quotation_to_dict(py, price)?)?;
                }
                if let Some(ref time) = trade.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
            crate::proto::market_data_response::Payload::Orderbook(orderbook) => {
                d.set_item("payload_type", "orderbook")?;
                d.set_item("figi", &orderbook.figi)?;
                d.set_item("depth", orderbook.depth)?;
                d.set_item("is_consistent", orderbook.is_consistent)?;
                let bids = PyDict::new(py);
                for bid in &orderbook.bids {
                    if let Some(ref price) = bid.price {
                        bids.set_item(
                            bid.quantity.to_string().as_str(),
                            quotation_to_dict(py, price)?,
                        )?;
                    }
                }
                d.set_item("bids", bids)?;
                let asks = PyDict::new(py);
                for ask in &orderbook.asks {
                    if let Some(ref price) = ask.price {
                        asks.set_item(
                            ask.quantity.to_string().as_str(),
                            quotation_to_dict(py, price)?,
                        )?;
                    }
                }
                d.set_item("asks", asks)?;
                if let Some(ref time) = orderbook.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
            crate::proto::market_data_response::Payload::Candle(candle) => {
                d.set_item("payload_type", "candle")?;
                d.set_item("figi", &candle.figi)?;
                d.set_item("interval", candle.interval)?;
                d.set_item("volume", candle.volume)?;
                if let Some(ref open) = candle.open {
                    d.set_item("open", quotation_to_dict(py, open)?)?;
                }
                if let Some(ref high) = candle.high {
                    d.set_item("high", quotation_to_dict(py, high)?)?;
                }
                if let Some(ref low) = candle.low {
                    d.set_item("low", quotation_to_dict(py, low)?)?;
                }
                if let Some(ref close) = candle.close {
                    d.set_item("close", quotation_to_dict(py, close)?)?;
                }
                if let Some(ref time) = candle.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
            crate::proto::market_data_response::Payload::TradingStatus(status) => {
                d.set_item("payload_type", "trading_status")?;
                d.set_item("figi", &status.figi)?;
                d.set_item("trading_status", status.trading_status)?;
                if let Some(ref time) = status.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
            crate::proto::market_data_response::Payload::LastPrice(last_price) => {
                d.set_item("payload_type", "last_price")?;
                d.set_item("figi", &last_price.figi)?;
                if let Some(ref price) = last_price.price {
                    d.set_item("price", quotation_to_dict(py, price)?)?;
                }
                if let Some(ref time) = last_price.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
            crate::proto::market_data_response::Payload::SubscribeInfoResponse(info) => {
                d.set_item("payload_type", "subscribe_info_response")?;
                d.set_item("tracking_id", &info.tracking_id)?;
            }
            crate::proto::market_data_response::Payload::SubscribeTradesResponse(resp) => {
                d.set_item("payload_type", "subscribe_trades_response")?;
                d.set_item("tracking_id", &resp.tracking_id)?;
            }
            crate::proto::market_data_response::Payload::SubscribeOrderBookResponse(resp) => {
                d.set_item("payload_type", "subscribe_orderbook_response")?;
                d.set_item("tracking_id", &resp.tracking_id)?;
            }
            crate::proto::market_data_response::Payload::SubscribeCandlesResponse(resp) => {
                d.set_item("payload_type", "subscribe_candles_response")?;
                d.set_item("tracking_id", &resp.tracking_id)?;
            }
            crate::proto::market_data_response::Payload::SubscribeLastPriceResponse(resp) => {
                d.set_item("payload_type", "subscribe_last_price_response")?;
                d.set_item("tracking_id", &resp.tracking_id)?;
            }
            crate::proto::market_data_response::Payload::OpenInterest(oi) => {
                d.set_item("payload_type", "open_interest")?;
                d.set_item("instrument_uid", &oi.instrument_uid)?;
                d.set_item("open_interest", oi.open_interest)?;
                d.set_item("ticker", &oi.ticker)?;
                d.set_item("class_code", &oi.class_code)?;
            }
            crate::proto::market_data_response::Payload::Ping(ping) => {
                d.set_item("payload_type", "ping")?;
                if let Some(ref time) = ping.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
        }
    }
    Ok(d)
}

fn order_state_stream_response_to_dict<'py>(
    py: Python<'py>,
    response: &OrderStateStreamResponse,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    if let Some(ref payload) = response.payload {
        match payload {
            crate::proto::order_state_stream_response::Payload::OrderState(order_state) => {
                d.set_item("payload_type", "order_state")?;
                d.set_item("order_id", &order_state.order_id)?;
                d.set_item(
                    "execution_report_status",
                    order_state.execution_report_status,
                )?;
                d.set_item("ticker", &order_state.ticker)?;
                d.set_item("class_code", &order_state.class_code)?;
                d.set_item("direction", order_state.direction)?;
                d.set_item("order_type", order_state.order_type)?;
                d.set_item("time_in_force", order_state.time_in_force)?;
                d.set_item("lot_size", order_state.lot_size)?;
                d.set_item("account_id", &order_state.account_id)?;
                d.set_item("trade_order_id", &order_state.trade_order_id)?;
                if let Some(ref oid) = order_state.order_request_id {
                    d.set_item("order_request_id", oid.as_str())?;
                }
                if let Some(ref created_at) = order_state.created_at {
                    d.set_item("created_at_seconds", created_at.seconds)?;
                    d.set_item("created_at_nanos", created_at.nanos)?;
                }
                if let Some(ref price) = order_state.initial_order_price {
                    d.set_item("initial_order_price", money_value_to_dict(py, price)?)?;
                }
                if let Some(ref price) = order_state.order_price {
                    d.set_item("order_price", money_value_to_dict(py, price)?)?;
                }
                if let Some(ref amount) = order_state.amount {
                    d.set_item("amount", money_value_to_dict(py, amount)?)?;
                }
                if let Some(ref executed_order_price) = order_state.executed_order_price {
                    d.set_item(
                        "executed_order_price",
                        money_value_to_dict(py, executed_order_price)?,
                    )?;
                }
            }
            crate::proto::order_state_stream_response::Payload::StopOrderState(stop_order) => {
                d.set_item("payload_type", "stop_order_state")?;
                d.set_item("stop_order_id", &stop_order.stop_order_id)?;
                d.set_item("ticker", &stop_order.ticker)?;
                d.set_item("class_code", &stop_order.class_code)?;
                d.set_item("direction", stop_order.direction)?;
                d.set_item("order_type", stop_order.order_type)?;
            }
            crate::proto::order_state_stream_response::Payload::Subscription(sub) => {
                d.set_item("payload_type", "subscription")?;
                d.set_item("tracking_id", &sub.tracking_id)?;
                d.set_item("status", sub.status)?;
            }
            crate::proto::order_state_stream_response::Payload::Ping(ping) => {
                d.set_item("payload_type", "ping")?;
                if let Some(ref time) = ping.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
        }
    }
    Ok(d)
}

fn portfolio_stream_response_to_dict<'py>(
    py: Python<'py>,
    response: &PortfolioStreamResponse,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    if let Some(ref payload) = response.payload {
        match payload {
            crate::proto::portfolio_stream_response::Payload::Portfolio(portfolio) => {
                d.set_item("payload_type", "portfolio")?;
                d.set_item("account_id", &portfolio.account_id)?;
                if let Some(ref mv) = portfolio.total_amount_shares {
                    d.set_item("total_amount_shares", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref mv) = portfolio.total_amount_bonds {
                    d.set_item("total_amount_bonds", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref mv) = portfolio.total_amount_etf {
                    d.set_item("total_amount_etf", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref mv) = portfolio.total_amount_currencies {
                    d.set_item("total_amount_currencies", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref mv) = portfolio.total_amount_futures {
                    d.set_item("total_amount_futures", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref mv) = portfolio.total_amount_portfolio {
                    d.set_item("total_amount_portfolio", money_value_to_dict(py, mv)?)?;
                }
                if let Some(ref q) = portfolio.expected_yield {
                    d.set_item("expected_yield", quotation_to_dict(py, q)?)?;
                }
            }
            crate::proto::portfolio_stream_response::Payload::Subscriptions(_subs) => {
                d.set_item("payload_type", "subscriptions")?;
            }
            crate::proto::portfolio_stream_response::Payload::Ping(ping) => {
                d.set_item("payload_type", "ping")?;
                if let Some(ref time) = ping.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
        }
    }
    Ok(d)
}

fn positions_stream_response_to_dict<'py>(
    py: Python<'py>,
    response: &PositionsStreamResponse,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    if let Some(ref payload) = response.payload {
        match payload {
            crate::proto::positions_stream_response::Payload::Position(position_data) => {
                d.set_item("payload_type", "position")?;
                d.set_item("account_id", &position_data.account_id)?;
                if let Some(ref date) = position_data.date {
                    d.set_item("date_seconds", date.seconds)?;
                    d.set_item("date_nanos", date.nanos)?;
                }
                // money, securities, futures, options are repeated fields - pass counts
                d.set_item("money_count", position_data.money.len() as i64)?;
                d.set_item("securities_count", position_data.securities.len() as i64)?;
                d.set_item("futures_count", position_data.futures.len() as i64)?;
                d.set_item("options_count", position_data.options.len() as i64)?;
            }
            crate::proto::positions_stream_response::Payload::Subscriptions(_subs) => {
                d.set_item("payload_type", "subscriptions")?;
            }
            crate::proto::positions_stream_response::Payload::InitialPositions(_ip) => {
                d.set_item("payload_type", "initial_positions")?;
            }
            crate::proto::positions_stream_response::Payload::Ping(ping) => {
                d.set_item("payload_type", "ping")?;
                if let Some(ref time) = ping.time {
                    d.set_item("time_seconds", time.seconds)?;
                    d.set_item("time_nanos", time.nanos)?;
                }
            }
        }
    }
    Ok(d)
}

// -------------------------------------------------------------------------------------------
// MarketDataStream — bidirectional gRPC stream running in a dedicated std::thread
// -------------------------------------------------------------------------------------------

/// A native bidirectional market data stream running in a dedicated OS thread
/// with its own tokio runtime. Converts incoming proto messages to Python dicts
/// and delivers them through a user-provided callback.
#[derive(Debug)]
pub struct NativeMarketDataStream {
    cancel_token: CancellationToken,
    is_active: Arc<AtomicBool>,
    request_tx: std::sync::mpsc::SyncSender<MarketDataRequest>,
    thread_handle: Option<thread::JoinHandle<()>>,
}

impl NativeMarketDataStream {
    /// Create a new market data stream.
    ///
    /// The `on_data` callback is called from the dedicated stream thread with
    /// the GIL held. It receives a Python dict representation of the incoming
    /// [`MarketDataResponse`].
    #[must_use]
    pub fn new(
        client: TInvestGrpcClient,
        on_data: Box<dyn Fn(Py<PyDict>) + Send + 'static>,
    ) -> Self {
        let cancel_token = CancellationToken::new();
        let is_active = Arc::new(AtomicBool::new(false));
        let (request_tx, request_rx) = std::sync::mpsc::sync_channel::<MarketDataRequest>(256);

        let ct = cancel_token.clone();
        let active = is_active.clone();

        let handle = thread::spawn(move || {
            let rt = match Runtime::new() {
                Ok(rt) => rt,
                Err(e) => {
                    error!("NativeMarketDataStream: failed to create tokio runtime: {e}");
                    return;
                }
            };

            rt.block_on(async move {
                info!("NativeMarketDataStream: background thread started");

                let mut stub = match client.market_data_stream().await {
                    Ok(s) => s,
                    Err(e) => {
                        error!("NativeMarketDataStream: failed to get stream service: {e}");
                        return;
                    }
                };

                let (tx, rx) = tokio::sync::mpsc::unbounded_channel::<MarketDataRequest>();
                let rx_stream = tokio_stream::wrappers::UnboundedReceiverStream::new(rx);
                let request = client.with_auth(tonic::Request::new(rx_stream));

                let response = match stub.market_data_stream(request).await {
                    Ok(resp) => resp.into_inner(),
                    Err(e) => {
                        error!("NativeMarketDataStream: failed to open stream: {e}");
                        return;
                    }
                };

                active.store(true, Ordering::SeqCst);
                info!("NativeMarketDataStream: stream opened, now active");

                let tx_clone = tx;
                let ct_inner = ct.clone();

                // Spawn request forwarder
                tokio::spawn(async move {
                    loop {
                        match request_rx.try_recv() {
                            Ok(req) => {
                                if tx_clone.send(req).is_err() {
                                    break;
                                }
                            }
                            Err(mpsc::TryRecvError::Empty) => {
                                if ct_inner.is_cancelled() {
                                    break;
                                }
                                tokio::time::sleep(Duration::from_millis(10)).await;
                            }
                            Err(mpsc::TryRecvError::Disconnected) => break,
                        }
                    }
                });

                let mut response = response;
                loop {
                    tokio::select! {
                        _ = ct.cancelled() => {
                            info!("NativeMarketDataStream: cancellation received, shutting down");
                            break;
                        }
                        msg = response.message() => {
                            match msg {
                                Ok(Some(market_data)) => {
                                    Python::attach(|py| {
                                        match market_data_response_to_dict(py, &market_data) {
                                            Ok(dict) => on_data(dict.unbind()),
                                            Err(e) => {
                                                error!("NativeMarketDataStream: dict conversion error: {e}");
                                            }
                                        }
                                    });
                                }
                                Ok(None) => {
                                    info!("NativeMarketDataStream: stream closed by server");
                                    break;
                                }
                                Err(e) => {
                                    error!("NativeMarketDataStream: stream error: {e}");
                                    tokio::time::sleep(Duration::from_secs(1)).await;
                                    break;
                                }
                            }
                        }
                    }
                }

                active.store(false, Ordering::SeqCst);
                info!("NativeMarketDataStream: stream ended");
            });
        });

        Self {
            cancel_token,
            is_active,
            request_tx,
            thread_handle: Some(handle),
        }
    }

    /// Subscribe to trade ticks for the given instrument UIDs.
    #[allow(deprecated)]
    pub fn subscribe_trades(&self, instrument_ids: &[String]) {
        if !self.is_active.load(Ordering::SeqCst) {
            warn!("NativeMarketDataStream: cannot subscribe, stream not active");
            return;
        }

        let instruments: Vec<TradeInstrument> = instrument_ids
            .iter()
            .map(|id| TradeInstrument {
                figi: String::new(),
                instrument_id: id.clone(),
            })
            .collect();

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(market_data_request::Payload::SubscribeTradesRequest(
                SubscribeTradesRequest {
                    subscription_action: SubscriptionAction::Subscribe as i32,
                    instruments,
                    trade_source: 3,
                    with_open_interest: false,
                },
            )),
        };

        if let Err(e) = self.request_tx.send(request) {
            error!("NativeMarketDataStream: failed to send subscribe_trades: {e}");
        }
    }

    /// Unsubscribe from trade ticks.
    #[allow(deprecated)]
    pub fn unsubscribe_trades(&self, instrument_ids: &[String]) {
        if !self.is_active.load(Ordering::SeqCst) {
            return;
        }

        let instruments: Vec<TradeInstrument> = instrument_ids
            .iter()
            .map(|id| TradeInstrument {
                figi: String::new(),
                instrument_id: id.clone(),
            })
            .collect();

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(market_data_request::Payload::SubscribeTradesRequest(
                SubscribeTradesRequest {
                    subscription_action: SubscriptionAction::Unsubscribe as i32,
                    instruments,
                    trade_source: 3,
                    with_open_interest: false,
                },
            )),
        };

        if let Err(e) = self.request_tx.send(request) {
            error!("NativeMarketDataStream: failed to send unsubscribe_trades: {e}");
        }
    }

    /// Subscribe to order book updates.
    #[allow(deprecated)]
    pub fn subscribe_order_book(&self, instrument_ids: &[String], depth: i32) {
        if !self.is_active.load(Ordering::SeqCst) {
            warn!("NativeMarketDataStream: cannot subscribe, stream not active");
            return;
        }

        let instruments: Vec<OrderBookInstrument> = instrument_ids
            .iter()
            .map(|id| OrderBookInstrument {
                figi: String::new(),
                depth,
                instrument_id: id.clone(),
                order_book_type: 1,
            })
            .collect();

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(market_data_request::Payload::SubscribeOrderBookRequest(
                SubscribeOrderBookRequest {
                    subscription_action: SubscriptionAction::Subscribe as i32,
                    instruments,
                },
            )),
        };

        if let Err(e) = self.request_tx.send(request) {
            error!("NativeMarketDataStream: failed to send subscribe_order_book: {e}");
        }
    }

    /// Unsubscribe from order book updates.
    #[allow(deprecated)]
    pub fn unsubscribe_order_book(&self, instrument_ids: &[String], depth: i32) {
        if !self.is_active.load(Ordering::SeqCst) {
            return;
        }

        let instruments: Vec<OrderBookInstrument> = instrument_ids
            .iter()
            .map(|id| OrderBookInstrument {
                figi: String::new(),
                depth,
                instrument_id: id.clone(),
                order_book_type: 1,
            })
            .collect();

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(market_data_request::Payload::SubscribeOrderBookRequest(
                SubscribeOrderBookRequest {
                    subscription_action: SubscriptionAction::Unsubscribe as i32,
                    instruments,
                },
            )),
        };

        if let Err(e) = self.request_tx.send(request) {
            error!("NativeMarketDataStream: failed to send unsubscribe_order_book: {e}");
        }
    }

    /// Subscribe to trading info (status) updates.
    #[allow(deprecated)]
    pub fn subscribe_info(&self, instrument_ids: &[String]) {
        if !self.is_active.load(Ordering::SeqCst) {
            warn!("NativeMarketDataStream: cannot subscribe, stream not active");
            return;
        }

        let instruments: Vec<crate::proto::InfoInstrument> = instrument_ids
            .iter()
            .map(|id| crate::proto::InfoInstrument {
                figi: String::new(),
                instrument_id: id.clone(),
            })
            .collect();

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(market_data_request::Payload::SubscribeInfoRequest(
                SubscribeInfoRequest {
                    subscription_action: SubscriptionAction::Subscribe as i32,
                    instruments,
                },
            )),
        };

        if let Err(e) = self.request_tx.send(request) {
            error!("NativeMarketDataStream: failed to send subscribe_info: {e}");
        }
    }

    /// Stop the stream and join the background thread.
    pub fn stop(mut self) {
        self.cancel_token.cancel();
        self.is_active.store(false, Ordering::SeqCst);
        if let Some(handle) = self.thread_handle.take() {
            info!("NativeMarketDataStream: waiting for background thread to finish...");

            let _ = handle.join();
            info!("NativeMarketDataStream: background thread joined");
        }
    }

    /// Returns `true` if the stream is currently active.
    #[must_use]
    pub fn is_active(&self) -> bool {
        self.is_active.load(Ordering::SeqCst)
    }
}

impl Drop for NativeMarketDataStream {
    fn drop(&mut self) {
        if self.is_active.load(Ordering::SeqCst) {
            self.cancel_token.cancel();
        }
    }
}

// -------------------------------------------------------------------------------------------
// Macro: server-side stream with dedicated std::thread
// -------------------------------------------------------------------------------------------

macro_rules! define_native_server_stream {
    (
        $vis:vis $struct_name:ident,
        $stub_getter:ident,
        $rpc_method:ident,
        $request_type:ty,
        $response_type:ty,
        $label:literal,
        $response_converter:ident,
        $request_builder:expr
    ) => {
        #[doc = concat!("A native server-side stream for ", $label, " running in a dedicated")]
        #[doc = concat!("OS thread with its own tokio runtime.")]
        #[derive(Debug)]
        $vis struct $struct_name {
            cancel_token: CancellationToken,
            is_active: Arc<AtomicBool>,
            thread_handle: Option<thread::JoinHandle<()>>,
        }

        impl $struct_name {
            /// Create a new stream.
            ///
            /// The `on_data` callback receives a Python dict representation of
            /// each incoming response. It is called from the stream thread with
            /// the GIL held.
            #[must_use]
            pub fn new(
                client: TInvestGrpcClient,
                accounts: Vec<String>,
                on_data: Box<dyn Fn(Py<PyDict>) + Send + 'static>,
            ) -> Self {
                let cancel_token = CancellationToken::new();
                let is_active = Arc::new(AtomicBool::new(false));

                let ct = cancel_token.clone();
                let active = is_active.clone();
                let label = $label.to_string();

                let handle = thread::spawn(move || {
                    let rt = match Runtime::new() {
                        Ok(rt) => rt,
                        Err(e) => {
                            error!("{label}: failed to create tokio runtime: {e}");
                            return;
                        }
                    };

                    rt.block_on(async move {
                        info!("{label}: background thread started");

                        let mut stub = match client.$stub_getter().await {
                            Ok(s) => s,
                            Err(e) => {
                                error!("{label}: failed to get stream service: {e}");
                                return;
                            }
                        };

                        let inner_request = $request_builder(&accounts);
                        let request = client.with_auth(tonic::Request::new(inner_request));

                        let response = match stub.$rpc_method(request).await {
                            Ok(resp) => resp.into_inner(),
                            Err(e) => {
                                error!("{label}: failed to open stream: {e}");
                                return;
                            }
                        };

                        active.store(true, Ordering::SeqCst);
                        info!("{label}: stream opened, now active");

                        let mut stream = response;
                        loop {
                            tokio::select! {
                                _ = ct.cancelled() => {
                                    info!("{label}: cancellation received, shutting down");
                                    break;
                                }
                                msg = stream.message() => {
                                    match msg {
                                        Ok(Some(response)) => {
                                            let _ = Python::attach(|py| {
                                                match $response_converter(py, &response) {
                                                    Ok(dict) => {
                                                        on_data(dict.unbind());
                                                    }
                                                    Err(e) => {
                                                        error!("{label}: dict conversion error: {e}");
                                                    }
                                                }
                                            });
                                        }
                                        Ok(None) => {
                                            info!("{label}: stream closed by server");
                                            break;
                                        }
                                        Err(e) => {
                                            error!("{label}: stream error: {e}");
                                            break;
                                        }
                                    }
                                }
                            }
                        }

                        active.store(false, Ordering::SeqCst);
                        info!("{label}: stream ended");
                    });
                });

                Self {
                    cancel_token,
                    is_active,
                    thread_handle: Some(handle),
                }
            }

            /// Stop the stream and join the background thread.
            pub fn stop(mut self) {
                self.cancel_token.cancel();
                self.is_active.store(false, Ordering::SeqCst);
                if let Some(handle) = self.thread_handle.take() {
                    info!("{}: waiting for background thread to finish...", $label);
                    let _ = handle.join();
                    info!("{}: background thread joined", $label);
                }
            }

            /// Returns `true` if the stream is currently active.
            #[must_use]
            pub fn is_active(&self) -> bool {
                self.is_active.load(Ordering::SeqCst)
            }
        }

        impl Drop for $struct_name {
            fn drop(&mut self) {
                if self.is_active.load(Ordering::SeqCst) {
                    self.cancel_token.cancel();
                }
            }
        }
    };
}

// -------------------------------------------------------------------------------------------
// Generated server-side stream types
// -------------------------------------------------------------------------------------------

define_native_server_stream!(
    pub NativeOrderStateStream,
    orders_stream,
    order_state_stream,
    OrderStateStreamRequest,
    OrderStateStreamResponse,
    "NativeOrderStateStream",
    order_state_stream_response_to_dict,
    |accounts: &[String]| {
        let mut req = OrderStateStreamRequest::default();
        req.accounts = accounts.to_vec();
        req
    }
);

define_native_server_stream!(
    pub NativePortfolioStream,
    operations_stream,
    portfolio_stream,
    PortfolioStreamRequest,
    PortfolioStreamResponse,
    "NativePortfolioStream",
    portfolio_stream_response_to_dict,
    |accounts: &[String]| {
        PortfolioStreamRequest {
            accounts: accounts.to_vec(),
            ping_settings: None,
        }
    }
);

define_native_server_stream!(
    pub NativePositionsStream,
    operations_stream,
    positions_stream,
    PositionsStreamRequest,
    PositionsStreamResponse,
    "NativePositionsStream",
    positions_stream_response_to_dict,
    |accounts: &[String]| {
        PositionsStreamRequest {
            accounts: accounts.to_vec(),
            ping_settings: None,
            with_initial_positions: false,
        }
    }
);
