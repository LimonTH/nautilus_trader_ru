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

use std::future::Future;
use std::sync::Arc;
use std::time::Duration;

use tokio::sync::RwLock;
use tonic::metadata::{Ascii, MetadataValue};
use tonic::transport::{Certificate, Channel, ClientTlsConfig, Endpoint};
use tonic::{Request, Status};
use tracing::{error, info};

use crate::config::TInvestClientConfig;
use crate::proto::{
    instruments_service_client::InstrumentsServiceClient,
    market_data_service_client::MarketDataServiceClient,
    market_data_stream_service_client::MarketDataStreamServiceClient,
    operations_service_client::OperationsServiceClient,
    operations_stream_service_client::OperationsStreamServiceClient,
    orders_service_client::OrdersServiceClient,
    orders_stream_service_client::OrdersStreamServiceClient,
    sandbox_service_client::SandboxServiceClient,
    signal_service_client::SignalServiceClient,
    stop_orders_service_client::StopOrdersServiceClient,
    users_service_client::UsersServiceClient,
};

/// Error type for T-Invest client operations.
#[derive(Debug, thiserror::Error)]
pub enum TInvestClientError {
    #[error("gRPC error: {0}")]
    Grpc(#[from] Status),

    #[error("Transport error: {0}")]
    Transport(#[from] tonic::transport::Error),

    #[error("Authentication error: {0}")]
    Auth(String),

    #[error("Not connected")]
    NotConnected,
}

/// A gRPC client for the T-Invest API.
///
/// Manages connections to all T-Invest services and provides authenticated
/// access to both production and sandbox environments.
#[derive(Clone, Debug)]
pub struct TInvestGrpcClient {
    /// The client configuration.
    config: TInvestClientConfig,
    /// The underlying gRPC channel (shared across clones via Arc).
    channel: Arc<RwLock<Option<Channel>>>,
    /// The auth token metadata value.
    auth_header: MetadataValue<Ascii>,
    // Service stubs (lazily initialized)
    instruments: Arc<RwLock<Option<InstrumentsServiceClient<Channel>>>>,
    market_data: Arc<RwLock<Option<MarketDataServiceClient<Channel>>>>,
    market_data_stream: Arc<RwLock<Option<MarketDataStreamServiceClient<Channel>>>>,
    operations: Arc<RwLock<Option<OperationsServiceClient<Channel>>>>,
    operations_stream: Arc<RwLock<Option<OperationsStreamServiceClient<Channel>>>>,
    orders: Arc<RwLock<Option<OrdersServiceClient<Channel>>>>,
    orders_stream: Arc<RwLock<Option<OrdersStreamServiceClient<Channel>>>>,
    stop_orders: Arc<RwLock<Option<StopOrdersServiceClient<Channel>>>>,
    users: Arc<RwLock<Option<UsersServiceClient<Channel>>>>,
    sandbox: Arc<RwLock<Option<SandboxServiceClient<Channel>>>>,
    signals: Arc<RwLock<Option<SignalServiceClient<Channel>>>>,
}

impl TInvestGrpcClient {
    /// Create a new T-Invest gRPC client from configuration.
    pub fn new(config: TInvestClientConfig) -> Result<Self, TInvestClientError> {
        let auth_header = format!("Bearer {}", config.token)
            .parse::<MetadataValue<Ascii>>()
            .map_err(|e| TInvestClientError::Auth(format!("Invalid token format: {e}")))?;

        Ok(Self {
            config,
            channel: Arc::new(RwLock::new(None)),
            auth_header,
            instruments: Arc::new(RwLock::new(None)),
            market_data: Arc::new(RwLock::new(None)),
            market_data_stream: Arc::new(RwLock::new(None)),
            operations: Arc::new(RwLock::new(None)),
            operations_stream: Arc::new(RwLock::new(None)),
            orders: Arc::new(RwLock::new(None)),
            orders_stream: Arc::new(RwLock::new(None)),
            stop_orders: Arc::new(RwLock::new(None)),
            users: Arc::new(RwLock::new(None)),
            sandbox: Arc::new(RwLock::new(None)),
            signals: Arc::new(RwLock::new(None)),
        })
    }

    /// Connect to the T-Invest API.
    pub async fn connect(&mut self) -> Result<(), TInvestClientError> {
        let mut tls = ClientTlsConfig::new().with_enabled_roots();

        // Add Russian Trusted Root CA if configured (required for T-Invest API in Russia)
        if let Some(ref ca_path) = self.config.ca_cert_path {
            let ca_pem = std::fs::read_to_string(ca_path)
                .map_err(|e| TInvestClientError::Auth(format!("Failed to read CA cert file: {e}")))?;
            let cert = Certificate::from_pem(ca_pem);
            tls = tls.ca_certificate(cert);
        }

        let endpoint = Endpoint::from_shared(format!("https://{}", self.config.effective_target()))
            .map_err(|e| TInvestClientError::Auth(format!("Invalid endpoint: {e}")))?
            .tls_config(tls)
            .map_err(|e| TInvestClientError::Auth(format!("Invalid TLS configuration: {e}")))?
            .timeout(Duration::from_millis(self.config.connection_timeout_ms))
            .keep_alive_while_idle(true)
            .http2_keep_alive_interval(Duration::from_millis(self.config.keepalive_ms))
            .initial_connection_window_size(self.config.max_message_size as u32)
            .initial_stream_window_size(self.config.max_message_size as u32);

        let connected_channel = endpoint.connect().await.map_err(|e| {
            TInvestClientError::Auth(format!(
                "Failed to connect to {}: {e} (ca_cert_path={})",
                self.config.effective_target(),
                self.config.ca_cert_path.as_deref().unwrap_or("none"),
            ))
        })?;
        *self.channel.write().await = Some(connected_channel);

        Ok(())
    }

    /// Disconnect from the T-Invest API.
    pub async fn disconnect(&mut self) {
        *self.channel.write().await = None;
        *self.instruments.write().await = None;
        *self.market_data.write().await = None;
        *self.market_data_stream.write().await = None;
        *self.operations.write().await = None;
        *self.operations_stream.write().await = None;
        *self.orders.write().await = None;
        *self.orders_stream.write().await = None;
        *self.stop_orders.write().await = None;
        *self.users.write().await = None;
        *self.sandbox.write().await = None;
        *self.signals.write().await = None;
    }

    /// Returns true if the client is connected.
    pub fn is_connected(&self) -> bool {
        self.channel.try_read().map(|c| c.is_some()).unwrap_or(false)
    }

    /// Returns the client configuration.
    pub fn config(&self) -> &TInvestClientConfig {
        &self.config
    }

    /// Attach auth token to a gRPC request.
    pub fn with_auth<T>(&self, mut request: Request<T>) -> Request<T> {
        let auth_value = &self.auth_header;
        // Debug: log first 30 chars to verify token is being sent
        let auth_str = auth_value.to_str().unwrap_or("<invalid>");
        let truncated = if auth_str.len() > 30 {
            format!("{}...", &auth_str[..30])
        } else {
            auth_str.to_string()
        };
        tracing::debug!("with_auth: inserting authorization header: {truncated}");
        request
            .metadata_mut()
            .insert("authorization", auth_value.clone());
        request
    }

    /// Execute an async operation with retry and exponential backoff.
    ///
    /// Uses [`TInvestClientConfig::max_retries`] and [`TInvestClientConfig::retry_wait_ms`]
    /// to configure retry behaviour. On each retry the wait time doubles:
    /// first retry waits `retry_wait_ms`, second `retry_wait_ms * 2`, third `retry_wait_ms * 4`, …
    ///
    /// # Type parameters
    ///
    /// * `F`  – closure that produces a future.
    /// * `Fut` – the future returning `Result<T, E>`.
    /// * `T`  – success value.
    /// * `E`  – error type (must implement `std::fmt::Display`).
    pub async fn with_retry<F, Fut, T, E>(
        &self,
        operation_name: &str,
        mut f: F,
    ) -> Result<T, E>
    where
        F: FnMut() -> Fut,
        Fut: Future<Output = Result<T, E>>,
        E: std::fmt::Display,
    {
        let max_retries = self.config.max_retries;
        let base_wait = Duration::from_millis(self.config.retry_wait_ms);

        let mut attempt = 0u32;
        loop {
            match f().await {
                Ok(value) => return Ok(value),
                Err(err) => {
                    if attempt >= max_retries {
                        error!(
                            "{operation_name}: exhausted {max_retries} retries, last error: {err}"
                        );
                        return Err(err);
                    }
                    // Exponential backoff: wait_ms * 2^attempt
                    let delay = base_wait * (1u32 << attempt.min(10));
                    attempt += 1;
                    info!(
                        "{operation_name}: attempt {attempt}/{max_retries} failed ({err}), retrying in {delay:?}..."
                    );
                    tokio::time::sleep(delay).await;
                }
            }
        }
    }

    /// Get or create the channel.
    fn get_channel(&self) -> Result<Channel, TInvestClientError> {
        // Clone the channel from the shared Arc (Channel itself is cheap to clone)
        self.channel
            .try_read()
            .map_err(|_| TInvestClientError::NotConnected)?
            .clone()
            .ok_or(TInvestClientError::NotConnected)
    }

    // --- Service stub accessors ---

    pub async fn instruments(&self) -> Result<InstrumentsServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.instruments.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = InstrumentsServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn market_data(&self) -> Result<MarketDataServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.market_data.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = MarketDataServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn market_data_stream(
        &self,
    ) -> Result<MarketDataStreamServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.market_data_stream.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = MarketDataStreamServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn operations(&self) -> Result<OperationsServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.operations.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = OperationsServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn operations_stream(
        &self,
    ) -> Result<OperationsStreamServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.operations_stream.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = OperationsStreamServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn orders(&self) -> Result<OrdersServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.orders.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = OrdersServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn orders_stream(
        &self,
    ) -> Result<OrdersStreamServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.orders_stream.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = OrdersStreamServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn stop_orders(
        &self,
    ) -> Result<StopOrdersServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.stop_orders.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = StopOrdersServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn users(&self) -> Result<UsersServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.users.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = UsersServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    pub async fn sandbox(&self) -> Result<SandboxServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.sandbox.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = SandboxServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }

    /// Get or create the signals service stub (F15).
    ///
    /// The SignalsService exposes analytical signals which have no Nautilus
    /// equivalent (NOT_APPLICABLE); this stub is provided for completeness of
    /// the gRPC contract surface only.
    pub async fn signals(&self) -> Result<SignalServiceClient<Channel>, TInvestClientError> {
        let mut guard = self.signals.write().await;
        if let Some(client) = guard.as_ref() {
            Ok(client.clone())
        } else {
            let channel = self.get_channel()?;
            let client = SignalServiceClient::new(channel);
            *guard = Some(client.clone());
            Ok(client)
        }
    }
}