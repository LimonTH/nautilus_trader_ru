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

//! Stream subscription management for T-Invest API.
//!
//! Manages bidirectional and server-side gRPC streams for real-time market data,
//! order state updates, trades, and portfolio/position changes.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tokio::sync::oneshot;
use tokio::sync::{Mutex, mpsc};
use tokio_stream::wrappers::UnboundedReceiverStream;

use crate::client::TInvestClientError;
use crate::client::TInvestGrpcClient;
use crate::proto::SubscriptionAction;
use crate::proto::{
    InfoInstrument, MarketDataRequest, MarketDataResponse, MarketDataServerSideStreamRequest,
    OperationsStreamRequest, OperationsStreamResponse, OrderBookInstrument,
    OrderStateStreamRequest, PortfolioStreamRequest, PortfolioStreamResponse,
    PositionsStreamRequest, PositionsStreamResponse, SubscribeInfoRequest,
    SubscribeOrderBookRequest, SubscribeTradesRequest, TradeInstrument, TradesStreamRequest,
    TradesStreamResponse,
};

/// A declarative macro that generates a server-side gRPC stream struct and its
/// implementation, eliminating repetitive boilerplate.
///
/// # Usage patterns
///
/// ## Account-ID based streams
///
/// ```ignore
/// define_server_side_stream!(
///     (account_id)
///     TInvestOrderStateStream,
///     orders_stream,
///     order_state_stream,
///     OrderStateStreamRequest,
///     crate::proto::OrderStateStreamResponse,
///     "Order state"
/// );
/// ```
///
/// ## Request-based streams (pass full request object)
///
/// ```ignore
/// define_server_side_stream!(
///     (request)
///     TInvestMarketDataServerSideStream,
///     market_data_stream,
///     market_data_server_side_stream,
///     MarketDataServerSideStreamRequest,
///     MarketDataResponse,
///     "Market data server-side"
/// );
/// ```
macro_rules! define_server_side_stream {
    // -- Account-ID based variant -------------------------------------------------
    (
        (account_id)
        $vis:vis $struct_name:ident,
        $stub_getter:ident,
        $rpc_method:ident,
        $request_type:ty,
        $response_type:ty,
        $label:literal
    ) => {
        #[doc = concat!("Manages a server-side stream for ", $label, " updates.")]
        #[derive(Debug)]
        $vis struct $struct_name {
            grpc_client: TInvestGrpcClient,
            running: Arc<AtomicBool>,
        }

        impl $struct_name {
            /// Creates a new [` $struct_name `].
            #[must_use]
            pub fn new(grpc_client: TInvestGrpcClient) -> Self {
                Self {
                    grpc_client,
                    running: Arc::new(AtomicBool::new(false)),
                }
            }

            /// Start the stream for the given account.
            pub async fn start<F>(
                &self,
                account_id: &str,
                on_response: F,
            ) -> Result<(), tonic::Status>
            where
                F: Fn($response_type) + Send + 'static,
            {
                if self.running.load(Ordering::SeqCst) {
                    tracing::warn!(concat!($label, " stream already running"));
                    return Ok(());
                }

                let label_str = $label;

                let mut stub = self.grpc_client.$stub_getter().await.map_err(|e| {
                    tonic::Status::internal(format!(
                        "Failed to get {label_str} stream service: {e}"
                    ))
                })?;

                let inner_request = {
                    let mut req = <$request_type>::default();
                    req.accounts = vec![account_id.to_string()];
                    req
                };
                let request = self.grpc_client.with_auth(tonic::Request::new(inner_request));

                let response = stub.$rpc_method(request).await?;
                let mut stream = response.into_inner();

                self.running.store(true, Ordering::SeqCst);
                let running = self.running.clone();
                let account_id_owned = account_id.to_string();

                tokio::spawn(async move {
                    tracing::info!(
                        "{label_str} stream started for account {account_id_owned}"
                    );

                    while running.load(Ordering::SeqCst) {
                        match stream.message().await {
                            Ok(Some(response)) => {
                                on_response(response);
                            }
                            Ok(None) => {
                                tracing::info!("{label_str} stream closed by server");
                                break;
                            }
                            Err(e) => {
                                tracing::error!("{label_str} stream error: {e}");
                                break;
                            }
                        }
                    }

                    running.store(false, Ordering::SeqCst);
                    tracing::info!("{label_str} stream ended");
                });

                Ok(())
            }

            /// Stop the stream.
            pub fn stop(&self) {
                self.running.store(false, Ordering::SeqCst);
                tracing::info!(concat!($label, " stream stopped"));
            }

            /// Returns `true` if the stream is currently running.
            #[must_use]
            pub fn is_running(&self) -> bool {
                self.running.load(Ordering::SeqCst)
            }
        }
    };

    // -- Request-based variant ----------------------------------------------------
    (
        (request)
        $vis:vis $struct_name:ident,
        $stub_getter:ident,
        $rpc_method:ident,
        $request_type:ty,
        $response_type:ty,
        $label:literal
    ) => {
        #[doc = concat!("Manages a server-side stream for ", $label, ".")]
        #[derive(Debug)]
        $vis struct $struct_name {
            grpc_client: TInvestGrpcClient,
            running: Arc<AtomicBool>,
        }

        impl $struct_name {
            /// Creates a new [` $struct_name `].
            #[must_use]
            pub fn new(grpc_client: TInvestGrpcClient) -> Self {
                Self {
                    grpc_client,
                    running: Arc::new(AtomicBool::new(false)),
                }
            }

            /// Start the server-side stream with the given subscription request.
            pub async fn start<F>(
                &self,
                subscribe: $request_type,
                on_response: F,
            ) -> Result<(), tonic::Status>
            where
                F: Fn($response_type) + Send + 'static,
            {
                if self.running.load(Ordering::SeqCst) {
                    tracing::warn!(concat!($label, " already running"));
                    return Ok(());
                }

                let label_str = $label;

                let mut stub = self.grpc_client.$stub_getter().await.map_err(|e| {
                    tonic::Status::internal(format!(
                        "Failed to get {label_str} service: {e}"
                    ))
                })?;

                let request = self.grpc_client.with_auth(tonic::Request::new(subscribe));
                let response = stub.$rpc_method(request).await?;
                let mut stream = response.into_inner();

                self.running.store(true, Ordering::SeqCst);
                let running = self.running.clone();

                tokio::spawn(async move {
                    tracing::info!("{label_str} started");

                    while running.load(Ordering::SeqCst) {
                        match stream.message().await {
                            Ok(Some(response)) => {
                                on_response(response);
                            }
                            Ok(None) => {
                                tracing::info!("{label_str} closed by server");
                                break;
                            }
                            Err(e) => {
                                tracing::error!("{label_str} error: {e}");
                                break;
                            }
                        }
                    }

                    running.store(false, Ordering::SeqCst);
                    tracing::info!("{label_str} ended");
                });

                Ok(())
            }

            /// Stop the server-side stream.
            pub fn stop(&self) {
                self.running.store(false, Ordering::SeqCst);
                tracing::info!(concat!($label, " stopped"));
            }

            /// Returns `true` if the stream is currently running.
            #[must_use]
            pub fn is_running(&self) -> bool {
                self.running.load(Ordering::SeqCst)
            }
        }
    };
}

// Generated server-side stream types

define_server_side_stream!(
    (account_id)
    pub TInvestOrderStateStream,
    orders_stream,
    order_state_stream,
    OrderStateStreamRequest,
    crate::proto::OrderStateStreamResponse,
    "Order state"
);

define_server_side_stream!(
    (account_id)
    pub TInvestTradesStream,
    orders_stream,
    trades_stream,
    TradesStreamRequest,
    TradesStreamResponse,
    "Trades"
);

define_server_side_stream!(
    (account_id)
    pub TInvestPositionsStream,
    operations_stream,
    positions_stream,
    PositionsStreamRequest,
    PositionsStreamResponse,
    "Positions"
);

define_server_side_stream!(
    (account_id)
    pub TInvestOperationsStream,
    operations_stream,
    operations_stream,
    OperationsStreamRequest,
    OperationsStreamResponse,
    "Operations"
);

define_server_side_stream!(
    (request)
    pub TInvestMarketDataServerSideStream,
    market_data_stream,
    market_data_server_side_stream,
    MarketDataServerSideStreamRequest,
    MarketDataResponse,
    "Market data server-side"
);

// Manually maintained stream types (bidirectional / reconnect)

/// Manages a bidirectional stream for real-time market data.
#[derive(Debug)]
pub struct TInvestMarketDataStream {
    grpc_client: TInvestGrpcClient,
    running: Arc<AtomicBool>,
    sender: Arc<Mutex<Option<mpsc::UnboundedSender<MarketDataRequest>>>>,
}

impl TInvestMarketDataStream {
    #[must_use]
    pub fn new(grpc_client: TInvestGrpcClient) -> Self {
        Self {
            grpc_client,
            running: Arc::new(AtomicBool::new(false)),
            sender: Arc::new(Mutex::new(None)),
        }
    }

    /// Start the bidirectional market data stream.
    pub async fn start<F>(&self, on_response: F) -> Result<(), tonic::Status>
    where
        F: Fn(MarketDataResponse) + Send + 'static,
    {
        if self.running.load(Ordering::SeqCst) {
            tracing::warn!("Market data stream already running");
            return Ok(());
        }

        let mut stub = self.grpc_client.market_data_stream().await.map_err(|e| {
            tonic::Status::internal(format!("Failed to get market data stream service: {e}"))
        })?;

        // Create channels for sending requests into the bidirectional stream
        let (tx, rx) = mpsc::unbounded_channel::<MarketDataRequest>();
        let rx_stream = UnboundedReceiverStream::new(rx);

        let request = tonic::Request::new(rx_stream);
        let request = self.grpc_client.with_auth(request);

        let response = stub.market_data_stream(request).await?;
        let mut response_stream = response.into_inner();

        self.running.store(true, Ordering::SeqCst);
        *self.sender.lock().await = Some(tx);

        let running = self.running.clone();
        tokio::spawn(async move {
            tracing::info!("Market data stream started");

            while running.load(Ordering::SeqCst) {
                match response_stream.message().await {
                    Ok(Some(response)) => {
                        on_response(response);
                    }
                    Ok(None) => {
                        tracing::info!("Market data stream closed by server");
                        break;
                    }
                    Err(e) => {
                        tracing::error!("Market data stream error: {e}");
                        break;
                    }
                }
            }

            running.store(false, Ordering::SeqCst);
            tracing::info!("Market data stream ended");
        });

        Ok(())
    }

    /// Subscribe to real-time trade ticks.
    pub async fn subscribe_trades(&self, instrument_id: &str) -> Result<(), tonic::Status> {
        let sender = self.sender.lock().await;
        let sender = sender
            .as_ref()
            .ok_or_else(|| tonic::Status::failed_precondition("Market data stream not started"))?;

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(
                crate::proto::market_data_request::Payload::SubscribeTradesRequest(
                    SubscribeTradesRequest {
                        subscription_action: SubscriptionAction::Subscribe as i32,
                        instruments: vec![TradeInstrument {
                            figi: String::new(),
                            instrument_id: instrument_id.to_string(),
                        }],
                        trade_source: 3,
                        with_open_interest: false,
                    },
                ),
            ),
        };

        sender.send(request).map_err(|e| {
            tonic::Status::internal(format!("Failed to send subscription request: {e}"))
        })?;

        tracing::info!("Subscribed to trade ticks for {instrument_id}");
        Ok(())
    }

    /// Unsubscribe from trade ticks.
    pub async fn unsubscribe_trades(&self, instrument_id: &str) -> Result<(), tonic::Status> {
        let sender = self.sender.lock().await;
        let sender = sender
            .as_ref()
            .ok_or_else(|| tonic::Status::failed_precondition("Market data stream not started"))?;

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(
                crate::proto::market_data_request::Payload::SubscribeTradesRequest(
                    SubscribeTradesRequest {
                        subscription_action: SubscriptionAction::Unsubscribe as i32,
                        instruments: vec![TradeInstrument {
                            figi: String::new(),
                            instrument_id: instrument_id.to_string(),
                        }],
                        trade_source: 3,
                        with_open_interest: false,
                    },
                ),
            ),
        };

        sender.send(request).map_err(|e| {
            tonic::Status::internal(format!("Failed to send unsubscription request: {e}"))
        })?;

        tracing::info!("Unsubscribed from trade ticks for {instrument_id}");
        Ok(())
    }

    /// Subscribe to order book (depth) updates.
    pub async fn subscribe_order_book(
        &self,
        instrument_id: &str,
        depth: i32,
    ) -> Result<(), tonic::Status> {
        let sender = self.sender.lock().await;
        let sender = sender
            .as_ref()
            .ok_or_else(|| tonic::Status::failed_precondition("Market data stream not started"))?;

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(
                crate::proto::market_data_request::Payload::SubscribeOrderBookRequest(
                    SubscribeOrderBookRequest {
                        subscription_action: SubscriptionAction::Subscribe as i32,
                        instruments: vec![OrderBookInstrument {
                            figi: String::new(),
                            depth,
                            instrument_id: instrument_id.to_string(),
                            order_book_type: 1,
                        }],
                    },
                ),
            ),
        };

        sender.send(request).map_err(|e| {
            tonic::Status::internal(format!("Failed to send subscription request: {e}"))
        })?;

        tracing::info!("Subscribed to order book for {instrument_id} depth={depth}");
        Ok(())
    }

    /// Unsubscribe from order book updates.
    pub async fn unsubscribe_order_book(
        &self,
        instrument_id: &str,
        depth: i32,
    ) -> Result<(), tonic::Status> {
        let sender = self.sender.lock().await;
        let sender = sender
            .as_ref()
            .ok_or_else(|| tonic::Status::failed_precondition("Market data stream not started"))?;

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(
                crate::proto::market_data_request::Payload::SubscribeOrderBookRequest(
                    SubscribeOrderBookRequest {
                        subscription_action: SubscriptionAction::Unsubscribe as i32,
                        instruments: vec![OrderBookInstrument {
                            figi: String::new(),
                            depth,
                            instrument_id: instrument_id.to_string(),
                            order_book_type: 1,
                        }],
                    },
                ),
            ),
        };

        sender.send(request).map_err(|e| {
            tonic::Status::internal(format!("Failed to send unsubscription request: {e}"))
        })?;

        tracing::info!("Unsubscribed from order book for {instrument_id}");
        Ok(())
    }

    /// Subscribe to instrument info (trading status) updates.
    pub async fn subscribe_info(&self, instrument_id: &str) -> Result<(), tonic::Status> {
        let sender = self.sender.lock().await;
        let sender = sender
            .as_ref()
            .ok_or_else(|| tonic::Status::failed_precondition("Market data stream not started"))?;

        #[allow(deprecated)]
        let request = MarketDataRequest {
            payload: Some(
                crate::proto::market_data_request::Payload::SubscribeInfoRequest(
                    SubscribeInfoRequest {
                        subscription_action: SubscriptionAction::Subscribe as i32,
                        instruments: vec![InfoInstrument {
                            figi: String::new(),
                            instrument_id: instrument_id.to_string(),
                        }],
                    },
                ),
            ),
        };

        sender.send(request).map_err(|e| {
            tonic::Status::internal(format!("Failed to send subscription request: {e}"))
        })?;

        tracing::info!("Subscribed to info for {instrument_id}");
        Ok(())
    }

    /// Stop the market data stream.
    pub async fn stop(&self) {
        self.running.store(false, Ordering::SeqCst);
        let mut sender = self.sender.lock().await;
        *sender = None;
        tracing::info!("Market data stream stopped");
    }

    /// Returns true if the stream is running.
    #[must_use]
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

/// Manages a server-side stream for portfolio updates.
pub struct TInvestPortfolioStream {
    account_id: String,
    grpc_client: TInvestGrpcClient,
    on_portfolio: Arc<dyn Fn(PortfolioStreamResponse) + Send + Sync + 'static>,
    running: Arc<AtomicBool>,
    stop_tx: Arc<tokio::sync::Mutex<Option<oneshot::Sender<()>>>>,
    name: String,
}

impl std::fmt::Debug for TInvestPortfolioStream {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TInvestPortfolioStream")
            .field("account_id", &self.account_id)
            .field("grpc_client", &self.grpc_client)
            .field("on_portfolio", &"<callback>")
            .field("running", &self.running)
            .field("stop_tx", &"<oneshot::Sender>")
            .field("name", &self.name)
            .finish()
    }
}

impl TInvestPortfolioStream {
    #[must_use]
    pub fn new(
        account_id: String,
        grpc_client: TInvestGrpcClient,
        on_portfolio: impl Fn(PortfolioStreamResponse) + Send + Sync + 'static,
    ) -> Self {
        Self {
            account_id,
            grpc_client,
            on_portfolio: Arc::new(on_portfolio),
            running: Arc::new(AtomicBool::new(false)),
            stop_tx: Arc::new(tokio::sync::Mutex::new(None)),
            name: "PortfolioStream".to_string(),
        }
    }

    pub async fn start(&self) -> Result<(), String> {
        if self.running.load(Ordering::SeqCst) {
            return Err("PortfolioStream уже запущен".to_string());
        }

        let account_id = self.account_id.clone();
        let client = self.grpc_client.clone();
        let on_portfolio = self.on_portfolio.clone();
        let running = self.running.clone();
        let (tx, mut rx) = oneshot::channel();

        *self.stop_tx.lock().await = Some(tx);
        running.store(true, Ordering::SeqCst);

        tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = &mut rx => {
                        tracing::info!("PortfolioStream received stop signal");
                        break;
                    }
                    result = Self::run_stream(client.clone(), account_id.clone(), on_portfolio.clone()) => {
                        match result {
                            Ok(_) => {
                                tracing::info!("PortfolioStream completed normally");
                                break;
                            }
                            Err(e) => {
                                tracing::error!("PortfolioStream error: {e:?}");
                                tokio::time::sleep(Duration::from_secs(5)).await;
                                tracing::info!("PortfolioStream reconnecting...");
                            }
                        }
                    }
                }
            }
            running.store(false, Ordering::SeqCst);
        });

        Ok(())
    }

    async fn run_stream(
        client: TInvestGrpcClient,
        account_id: String,
        on_portfolio: Arc<dyn Fn(PortfolioStreamResponse) + Send + Sync + 'static>,
    ) -> Result<(), TInvestClientError> {
        let mut stream = client
            .operations_stream()
            .await?
            .portfolio_stream(tonic::Request::new(PortfolioStreamRequest {
                accounts: vec![account_id],
                ping_settings: None,
            }))
            .await?
            .into_inner();

        while let Some(response) = stream.message().await? {
            on_portfolio(response);
        }

        Ok(())
    }

    pub async fn stop(&self) {
        if let Some(tx) = self.stop_tx.lock().await.take() {
            let _ = tx.send(());
        }
    }

    #[must_use]
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_market_data_stream_initial_state() {
        let config = crate::config::TInvestClientConfig::default();
        let grpc_client = TInvestGrpcClient::new(config).unwrap();
        let stream = TInvestMarketDataStream::new(grpc_client);
        assert!(!stream.is_running());
    }

    #[test]
    fn test_order_state_stream_initial_state() {
        let config = crate::config::TInvestClientConfig::default();
        let grpc_client = TInvestGrpcClient::new(config).unwrap();
        let stream = TInvestOrderStateStream::new(grpc_client);
        assert!(!stream.is_running());
    }
}
