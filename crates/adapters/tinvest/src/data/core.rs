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

//! Live market data client for T-Invest API.

use std::{
    future::Future,
    sync::Mutex,
};

use async_trait::async_trait;
use nautilus_common::{
    clients::DataClient,
    live::get_runtime,
    messages::{
        DataEvent,
        data::{
            RequestBars,
            RequestBookDeltas, RequestBookDepth, RequestBookSnapshot, RequestForwardPrices,
            RequestFundingRates, RequestInstrument, RequestInstruments, RequestQuotes,
            RequestTrades, SubscribeInstrument, SubscribeInstruments,
            UnsubscribeInstrument, UnsubscribeInstruments,
        },
    },
};
use nautilus_core::{
    MUTEX_POISONED,
    time::{AtomicTime, get_atomic_clock_realtime},
};
use nautilus_model::{
    identifiers::{ClientId, Venue},
    instruments::Instrument,
};
use nautilus_model::data::Data;
use tokio::task::JoinHandle;
use tracing::{debug, error, info, info_span, warn};

use crate::client::{TInvestClientError, TInvestGrpcClient};
use crate::common::convert::{
    convert_bond_to_instrument, convert_currency_to_instrument, convert_etf_to_instrument,
    convert_future_to_instrument, convert_option_to_instrument, convert_proto_candle_to_bar,
    convert_proto_orderbook_to_quote_tick, convert_proto_trade_to_tick, convert_share_to_instrument,
};
use crate::proto::{
    GetCandlesRequest, GetClosePricesRequest, GetClosePricesResponse, GetLastPricesRequest,
    GetLastPricesResponse, GetLastTradesRequest, GetOrderBookRequest, GetTradingStatusRequest,
    GetTradingStatusResponse, InstrumentRequest, InstrumentsRequest,
    market_data_response::Payload,
};
use crate::stream::core::TInvestMarketDataStream;

/// Provides live market data via the T-Invest gRPC API.
///
/// Implements the [`DataClient`] trait with MessageBus integration for
/// event-driven data delivery.
#[derive(Debug)]
pub struct TInvestLiveMarketDataClient {
    client_id: ClientId,
    clock: &'static AtomicTime,
    grpc_client: TInvestGrpcClient,
    data_sender: Option<tokio::sync::mpsc::UnboundedSender<DataEvent>>,
    pending_tasks: Mutex<Vec<JoinHandle<()>>>,
}

impl TInvestLiveMarketDataClient {
    /// Creates a new [`TInvestLiveMarketDataClient`].
    #[must_use]
    pub fn new(client_id: ClientId, grpc_client: TInvestGrpcClient) -> Self {
        let clock = get_atomic_clock_realtime();
        Self {
            client_id,
            clock,
            grpc_client,
            data_sender: None,
            pending_tasks: Mutex::new(Vec::new()),
        }
    }

    // -- helper methods --

    /// Spawn an async task and track its handle.
    fn spawn_task<F>(&self, description: &'static str, fut: F)
    where
        F: Future<Output = anyhow::Result<()>> + Send + 'static,
    {
        let _span = info_span!("tinvest_data", task = description);
        let runtime = get_runtime();
        let handle = runtime.spawn(async move {
            if let Err(e) = fut.await {
                error!("{description} failed: {e}");
            }
        });

        let mut tasks = self.pending_tasks.lock().expect(MUTEX_POISONED);
        tasks.retain(|h| !h.is_finished());
        tasks.push(handle);
    }

    /// Abort all pending tasks.
    fn abort_pending_tasks(&self) {
        let mut tasks = self.pending_tasks.lock().expect(MUTEX_POISONED);
        for handle in tasks.drain(..) {
            handle.abort();
        }
    }

    // -- public convenience methods --

    /// Get the last prices for the given instruments.
    #[allow(deprecated)]
    pub async fn get_last_prices(
        &self,
        figi: &[String],
    ) -> Result<GetLastPricesResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_last_prices: {} instruments", figi.len());

        let mut stub = self.grpc_client.market_data().await?;
        let request = GetLastPricesRequest {
            figi: vec![],
            instrument_id: figi.to_vec(),
            last_price_type: 0,
            instrument_status: None,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_last_prices(request).await?;
        let resp = response.into_inner();
        info!("Got {} last prices", resp.last_prices.len());
        Ok(resp)
    }

    /// Get the trading status for the given instrument.
    #[allow(deprecated)]
    pub async fn get_trading_status(
        &self,
        figi: &str,
    ) -> Result<GetTradingStatusResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_trading_status: {figi}");

        let mut stub = self.grpc_client.market_data().await?;
        let request = GetTradingStatusRequest {
            figi: None,
            instrument_id: Some(figi.to_string()),
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_trading_status(request).await?;
        let resp = response.into_inner();
        info!("Trading status for {}: {:?}", figi, resp.trading_status);
        Ok(resp)
    }

    /// Get the close prices for the given instruments.
    pub async fn get_close_prices(
        &self,
        figi: &[String],
    ) -> Result<GetClosePricesResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_close_prices: {} instruments", figi.len());

        let mut stub = self.grpc_client.market_data().await?;
        let instruments: Vec<crate::proto::InstrumentClosePriceRequest> = figi
            .iter()
            .map(|id| crate::proto::InstrumentClosePriceRequest {
                instrument_id: id.clone(),
            })
            .collect();

        let request = GetClosePricesRequest {
            instruments,
            instrument_status: None,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_close_prices(request).await?;
        let resp = response.into_inner();
        info!("Got {} close prices", resp.close_prices.len());
        Ok(resp)
    }

    /// Start the bidirectional market data stream and wire callbacks to the [`DataEvent`] sender.
    ///
    /// Dispatches:
    /// - `MarketDataResponse::trade` → `DataEvent::Data(Data::Trade(...))`
    /// - `MarketDataResponse::orderbook` → `DataEvent::Data(Data::Quote(...))`
    /// - `MarketDataResponse::candle` → `DataEvent::Data(Data::Bar(...))`
    pub async fn start_market_data_stream(
        &self,
    ) -> Result<(), tonic::Status> {
        let sender = match &self.data_sender {
            Some(s) => s.clone(),
            None => {
                warn!("Cannot start market data stream: data_sender not initialized");
                return Ok(());
            }
        };
        let clock = self.clock;

        let stream = TInvestMarketDataStream::new(self.grpc_client.clone());

        stream
            .start(move |response: crate::proto::MarketDataResponse| {
                let ts_init = clock.get_time_ns();

                if let Some(payload) = response.payload {
                    let data_event = match payload {
                        Payload::Trade(trade) => {
                            let instrument_id =
                                crate::common::convert::to_instrument_id(&trade.figi);
                            let tick = convert_proto_trade_to_tick(
                                &trade,
                                instrument_id,
                                ts_init,
                            );
                            Some(DataEvent::Data(Data::Trade(tick)))
                        }
                        Payload::Orderbook(orderbook) => {
                            let instrument_id =
                                crate::common::convert::to_instrument_id(&orderbook.figi);
                            convert_proto_orderbook_to_quote_tick(
                                &orderbook,
                                instrument_id,
                                ts_init,
                            )
                            .map(|quote| DataEvent::Data(Data::Quote(quote)))
                        }
                        Payload::Candle(candle) => {
                            let instrument_id =
                                crate::common::convert::to_instrument_id(&candle.figi);
                            // Build a BarType from the candle interval
                            let bar_type = candle_interval_to_bar_type(
                                candle.interval,
                                instrument_id,
                            );
                            if let Some(bt) = bar_type {
                                let bar = convert_proto_candle_to_bar(&candle, bt, ts_init);
                                Some(DataEvent::Data(Data::Bar(bar)))
                            } else {
                                None
                            }
                        }
                        _ => None, // subscribe responses, pings, etc. — ignore
                    };

                    if let Some(event) = data_event {
                        if let Err(e) = sender.send(event) {
                            error!("Failed to send data event: {e}");
                        }
                    }
                }
            })
            .await?;

        info!("Market data stream started with DataClient integration");
        Ok(())
    }
}

/// Convert a T-Invest [`CandleInterval`] to a Nautilus [`BarType`].
fn candle_interval_to_bar_type(
    interval: i32,
    instrument_id: nautilus_model::identifiers::InstrumentId,
) -> Option<nautilus_model::data::bar::BarType> {
    use nautilus_model::data::bar::{BarSpecification, BarType};
    use nautilus_model::enums::{AggregationSource, BarAggregation, PriceType};

    let spec = match interval {
        1 => BarSpecification::new(1, BarAggregation::Minute, PriceType::Last),
        2 => BarSpecification::new(5, BarAggregation::Minute, PriceType::Last),
        3 => BarSpecification::new(15, BarAggregation::Minute, PriceType::Last),
        4 => BarSpecification::new(1, BarAggregation::Hour, PriceType::Last),
        5 => BarSpecification::new(1, BarAggregation::Day, PriceType::Last),
        6 => BarSpecification::new(2, BarAggregation::Minute, PriceType::Last),
        7 => BarSpecification::new(3, BarAggregation::Minute, PriceType::Last),
        8 => BarSpecification::new(10, BarAggregation::Minute, PriceType::Last),
        9 => BarSpecification::new(30, BarAggregation::Minute, PriceType::Last),
        10 => BarSpecification::new(2, BarAggregation::Hour, PriceType::Last),
        11 => BarSpecification::new(4, BarAggregation::Hour, PriceType::Last),
        12 => BarSpecification::new(1, BarAggregation::Week, PriceType::Last),
        13 => BarSpecification::new(1, BarAggregation::Month, PriceType::Last),
        _ => return None,
    };
    Some(BarType::new(instrument_id, spec, AggregationSource::External))
}

#[async_trait(?Send)]
impl DataClient for TInvestLiveMarketDataClient {
    fn client_id(&self) -> ClientId {
        self.client_id
    }

    fn venue(&self) -> Option<Venue> {
        Some(Venue::new("TINVEST"))
    }

    fn start(&mut self) -> anyhow::Result<()> {
        info!("Starting T-Invest data client");
        self.data_sender = nautilus_common::live::runner::try_get_data_event_sender();
        if self.data_sender.is_none() {
            warn!("Data event sender not initialized; data events will not be emitted");
        }
        Ok(())
    }

    fn stop(&mut self) -> anyhow::Result<()> {
        info!("Stopping T-Invest data client");
        self.abort_pending_tasks();
        Ok(())
    }

    fn reset(&mut self) -> anyhow::Result<()> { Ok(()) }
    fn dispose(&mut self) -> anyhow::Result<()> { Ok(()) }

    fn is_connected(&self) -> bool { self.grpc_client.is_connected() }
    fn is_disconnected(&self) -> bool { !self.grpc_client.is_connected() }

    async fn connect(&mut self) -> anyhow::Result<()> {
        self.grpc_client.connect().await?;
        info!("Connected T-Invest data client");
        Ok(())
    }

    async fn disconnect(&mut self) -> anyhow::Result<()> {
        self.abort_pending_tasks();
        self.grpc_client.disconnect().await;
        info!("Disconnected T-Invest data client");
        Ok(())
    }

    fn subscribe_instruments(&mut self, _cmd: SubscribeInstruments) -> anyhow::Result<()> {
        debug!("subscribe_instruments called");
        Ok(())
    }
    fn subscribe_instrument(&mut self, _cmd: SubscribeInstrument) -> anyhow::Result<()> {
        debug!("subscribe_instrument called");
        Ok(())
    }
    fn unsubscribe_instruments(&mut self, _cmd: &UnsubscribeInstruments) -> anyhow::Result<()> {
        debug!("unsubscribe_instruments called");
        Ok(())
    }
    fn unsubscribe_instrument(&mut self, _cmd: &UnsubscribeInstrument) -> anyhow::Result<()> {
        debug!("unsubscribe_instrument called");
        Ok(())
    }

    fn request_instruments(&self, _request: RequestInstruments) -> anyhow::Result<()> {
        info!("Loading all instruments from T-Invest API...");

        let sender = match &self.data_sender {
            Some(s) => s.clone(),
            None => {
                warn!("Cannot send instruments: data_sender not initialized");
                return Ok(());
            }
        };
        let grpc_client = self.grpc_client.clone();
        let ts_init = self.clock.get_time_ns();

        self.spawn_task("request_instruments", async move {
            let mut stub = grpc_client.instruments().await?;
            let request = InstrumentsRequest {
                instrument_status: Some(1),
                instrument_exchange: None,
            };

            // Load shares
            {
                let req = grpc_client.with_auth(tonic::Request::new(request));
                let resp = stub.shares(req).await?;
                let inner = resp.into_inner();
                info!("Loaded {} shares", inner.instruments.len());
                for share in &inner.instruments {
                    let instrument = convert_share_to_instrument(share, ts_init.as_u64());
                    if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                        warn!("Failed to send share instrument: {e}");
                    }
                }
            }

            // Load bonds
            {
                let req = grpc_client.with_auth(tonic::Request::new(request));
                let resp = stub.bonds(req).await?;
                let inner = resp.into_inner();
                info!("Loaded {} bonds", inner.instruments.len());
                for bond in &inner.instruments {
                    let instrument = convert_bond_to_instrument(bond, ts_init.as_u64());
                    if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                        warn!("Failed to send bond instrument: {e}");
                    }
                }
            }

            // Load futures
            {
                let req = grpc_client.with_auth(tonic::Request::new(request));
                let resp = stub.futures(req).await?;
                let inner = resp.into_inner();
                info!("Loaded {} futures", inner.instruments.len());
                for future in &inner.instruments {
                    let instrument = convert_future_to_instrument(future, ts_init.as_u64());
                    if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                        warn!("Failed to send future instrument: {e}");
                    }
                }
            }

            // Load ETFs
            {
                let req = grpc_client.with_auth(tonic::Request::new(request));
                let resp = stub.etfs(req).await?;
                let inner = resp.into_inner();
                info!("Loaded {} ETFs", inner.instruments.len());
                for etf in &inner.instruments {
                    let instrument = convert_etf_to_instrument(etf, ts_init.as_u64());
                    if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                        warn!("Failed to send etf instrument: {e}");
                    }
                }
            }

            // Load currencies
            {
                let req = grpc_client.with_auth(tonic::Request::new(request));
                let resp = stub.currencies(req).await?;
                let inner = resp.into_inner();
                info!("Loaded {} currencies", inner.instruments.len());
                for currency in &inner.instruments {
                    let instrument = convert_currency_to_instrument(currency, ts_init.as_u64());
                    if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                        warn!("Failed to send currency instrument: {e}");
                    }
                }
            }

            // Load options
            {
                // Note: Options are loaded per basic_asset_uid via OptionsBy.
                // The deprecated Options endpoint may still work for loading all options.
                #[allow(deprecated)]
                {
                    let req = grpc_client.with_auth(tonic::Request::new(request));
                    match stub.options(req).await {
                        Ok(resp) => {
                            let inner = resp.into_inner();
                            info!("Loaded {} options", inner.instruments.len());
                            for option in &inner.instruments {
                                let instrument =
                                    convert_option_to_instrument(option, ts_init.as_u64());
                                if let Err(e) = sender.send(DataEvent::Instrument(instrument)) {
                                    warn!("Failed to send option instrument: {e}");
                                }
                            }
                        }
                        Err(e) => {
                            warn!("Failed to load options: {e}");
                        }
                    }
                }
            }

            info!("T-Invest instrument loading complete");
            Ok(())
        });

        Ok(())
    }

    fn request_instrument(&self, request: RequestInstrument) -> anyhow::Result<()> {
        let figi = request.instrument_id.symbol.to_string();
        info!("request_instrument: {figi}");

        let grpc_client = self.grpc_client.clone();
        let ts_init = request.ts_init;

        self.spawn_task("request_instrument", async move {
            let mut stub = grpc_client.instruments().await?;
            let instrument_request = InstrumentRequest {
                id_type: 0,
                class_code: None,
                id: figi.clone(),
            };

            // Try share_by
            {
                let req = grpc_client.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.share_by(req).await {
                    let inner = resp.into_inner();
                    if let Some(share) = inner.instrument {
                        let instrument = convert_share_to_instrument(&share, ts_init.as_u64());
                        info!("Loaded share instrument: {}", instrument.id());
                        return Ok(());
                    }
                }
            }

            // Try bond_by
            {
                let req = grpc_client.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.bond_by(req).await {
                    let inner = resp.into_inner();
                    if let Some(bond) = inner.instrument {
                        let instrument = convert_bond_to_instrument(&bond, ts_init.as_u64());
                        info!("Loaded bond instrument: {}", instrument.id());
                        return Ok(());
                    }
                }
            }

            // Try future_by
            {
                let req = grpc_client.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.future_by(req).await {
                    let inner = resp.into_inner();
                    if let Some(future) = inner.instrument {
                        let instrument = convert_future_to_instrument(&future, ts_init.as_u64());
                        info!("Loaded future instrument: {}", instrument.id());
                        return Ok(());
                    }
                }
            }

            // Try option_by
            {
                let req = grpc_client.with_auth(tonic::Request::new(instrument_request));
                if let Ok(resp) = stub.option_by(req).await {
                    let inner = resp.into_inner();
                    if let Some(option) = inner.instrument {
                        let instrument = convert_option_to_instrument(&option, ts_init.as_u64());
                        info!("Loaded option instrument: {}", instrument.id());
                        return Ok(());
                    }
                }
            }

            warn!("Instrument not found: {figi}");
            Ok(())
        });

        Ok(())
    }

    #[allow(deprecated)]
    fn request_quotes(&self, request: RequestQuotes) -> anyhow::Result<()> {
        let figi = request.instrument_id.symbol.to_string();
        info!("request_quotes: {figi}");

        let sender = match &self.data_sender {
            Some(s) => s.clone(),
            None => {
                warn!("Cannot send quotes: data_sender not initialized");
                return Ok(());
            }
        };
        let grpc_client = self.grpc_client.clone();
        let clock = self.clock;

        self.spawn_task("request_quotes", async move {
            let mut stub = grpc_client.market_data().await?;
            let req = GetOrderBookRequest {
                figi: Some(figi.clone()),
                depth: 10,
                instrument_id: Some(figi.clone()),
            };
            let req = grpc_client.with_auth(tonic::Request::new(req));
            let resp = stub.get_order_book(req).await?;
            let book = resp.into_inner();
            info!(
                "Got order book for {}: {} bids, {} asks",
                figi, book.bids.len(), book.asks.len(),
            );

            let instrument_id = crate::common::convert::to_instrument_id(&figi);
            let ts_init = clock.get_time_ns();

            // Convert GetOrderBookResponse to proto::OrderBook for the converter
            let orderbook = crate::proto::OrderBook {
                figi: book.figi.clone(),
                depth: book.depth,
                is_consistent: true,
                bids: book.bids.clone(),
                asks: book.asks.clone(),
                time: book.orderbook_ts,
                limit_up: book.limit_up,
                limit_down: book.limit_down,
                instrument_uid: book.instrument_uid.clone(),
                order_book_type: 0,
                ticker: book.ticker.clone(),
                class_code: book.class_code.clone(),
            };
            if let Some(quote) = convert_proto_orderbook_to_quote_tick(&orderbook, instrument_id, ts_init)
            {
                if let Err(e) = sender.send(DataEvent::Data(Data::Quote(quote))) {
                    warn!("Failed to send quote: {e}");
                }
            }
            Ok(())
        });

        Ok(())
    }

    #[allow(deprecated)]
    fn request_trades(&self, request: RequestTrades) -> anyhow::Result<()> {
        let figi = request.instrument_id.symbol.to_string();
        info!("request_trades: {figi}");

        let sender = match &self.data_sender {
            Some(s) => s.clone(),
            None => {
                warn!("Cannot send trades: data_sender not initialized");
                return Ok(());
            }
        };
        let grpc_client = self.grpc_client.clone();
        let clock = self.clock;

        self.spawn_task("request_trades", async move {
            let mut stub = grpc_client.market_data().await?;
            let now = prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            };
            let one_hour_ago = prost_types::Timestamp {
                seconds: now.seconds - 3600,
                nanos: 0,
            };
            let req = GetLastTradesRequest {
                figi: Some(figi.clone()),
                from: Some(one_hour_ago),
                to: Some(now),
                instrument_id: Some(figi.clone()),
                trade_source: 3,
            };
            let req = grpc_client.with_auth(tonic::Request::new(req));
            let resp = stub.get_last_trades(req).await?;
            let trades = resp.into_inner();
            info!("Got {} trades for {}", trades.trades.len(), figi);

            let instrument_id = crate::common::convert::to_instrument_id(&figi);
            let ts_init = clock.get_time_ns();
            for trade in &trades.trades {
                let tick = convert_proto_trade_to_tick(trade, instrument_id, ts_init);
                if let Err(e) = sender.send(DataEvent::Data(Data::Trade(tick))) {
                    warn!("Failed to send trade: {e}");
                }
            }
            Ok(())
        });

        Ok(())
    }

    #[allow(deprecated)]
    fn request_bars(&self, request: RequestBars) -> anyhow::Result<()> {
        let instrument_id = request.bar_type.instrument_id();
        let figi = instrument_id.symbol.to_string();
        let bar_spec_str = request.bar_type.spec().to_string();
        let bar_type = request.bar_type;
        info!("request_bars: {figi} spec={bar_spec_str}");

        let sender = match &self.data_sender {
            Some(s) => s.clone(),
            None => {
                warn!("Cannot send bars: data_sender not initialized");
                return Ok(());
            }
        };
        let grpc_client = self.grpc_client.clone();
        let clock = self.clock;
        let from_nanos = request
            .start
            .map(|dt| dt.timestamp_nanos_opt().unwrap_or(0) as u64)
            .unwrap_or(0);
        let to_nanos = request
            .end
            .map(|dt| dt.timestamp_nanos_opt().unwrap_or(0) as u64)
            .unwrap_or(0);
        let limit_val = request.limit.map(|n| n.get()).unwrap_or(100) as i32;

        self.spawn_task("request_bars", async move {
            let candle_interval = match crate::enums::bar_spec_to_candle_interval(&bar_spec_str) {
                Some(i) => i,
                None => {
                    error!("Unknown bar spec: {bar_spec_str}");
                    return Ok(());
                }
            };

            let mut stub = grpc_client.market_data().await?;
            let req = GetCandlesRequest {
                figi: Some(figi.clone()),
                from: Some(crate::common::convert::unix_nanos_to_timestamp(from_nanos)),
                to: Some(crate::common::convert::unix_nanos_to_timestamp(to_nanos)),
                interval: candle_interval,
                instrument_id: Some(figi.clone()),
                candle_source_type: None,
                limit: Some(limit_val),
            };
            let req = grpc_client.with_auth(tonic::Request::new(req));
            let resp = stub.get_candles(req).await?;
            let candles = resp.into_inner();
            info!(
                "Got {} candles for {} (interval={})",
                candles.candles.len(), figi, candle_interval,
            );

            let ts_init = clock.get_time_ns();
            for historic in &candles.candles {
                // Convert HistoricCandle to proto::Candle for the converter
                let candle = crate::proto::Candle {
                    figi: figi.clone(),
                    interval: candle_interval,
                    open: historic.open,
                    high: historic.high,
                    low: historic.low,
                    close: historic.close,
                    volume: historic.volume,
                    time: historic.time,
                    last_trade_ts: None,
                    instrument_uid: String::new(),
                    ticker: String::new(),
                    class_code: String::new(),
                    volume_buy: historic.volume_buy,
                    volume_sell: historic.volume_sell,
                    candle_source_type: historic.candle_source,
                };
                let bar = convert_proto_candle_to_bar(&candle, bar_type, ts_init);
                if let Err(e) = sender.send(DataEvent::Data(Data::Bar(bar))) {
                    warn!("Failed to send bar: {e}");
                }
            }
            Ok(())
        });

        Ok(())
    }

    fn request_book_snapshot(&self, _request: RequestBookSnapshot) -> anyhow::Result<()> {
        debug!("request_book_snapshot called");
        Ok(())
    }
    fn request_book_depth(&self, _request: RequestBookDepth) -> anyhow::Result<()> {
        debug!("request_book_depth called");
        Ok(())
    }
    fn request_book_deltas(&self, _request: RequestBookDeltas) -> anyhow::Result<()> {
        debug!("request_book_deltas called");
        Ok(())
    }
    fn request_funding_rates(&self, _request: RequestFundingRates) -> anyhow::Result<()> {
        Ok(())
    }
    fn request_forward_prices(&self, _request: RequestForwardPrices) -> anyhow::Result<()> {
        Ok(())
    }
}
