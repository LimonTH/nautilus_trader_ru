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

//! Live execution client for T-Invest API.

use std::{cell::RefCell, future::Future, rc::Rc, sync::Mutex};

use async_trait::async_trait;
use nautilus_common::{
    cache::Cache,
    clients::ExecutionClient,
    live::get_runtime,
    messages::execution::{
        BatchCancelOrders, BatchModifyOrders, CancelAllOrders, CancelOrder, GenerateFillReports,
        GenerateOrderStatusReport, GenerateOrderStatusReports, GeneratePositionStatusReports,
        ModifyOrder, QueryAccount, QueryOrder, SubmitOrder, SubmitOrderList,
    },
};
use nautilus_core::{
    MUTEX_POISONED, UUID4, UnixNanos,
    time::{AtomicTime, get_atomic_clock_realtime},
};
use nautilus_execution::client::core::ExecutionClientCore;
use nautilus_live::ExecutionEventEmitter;
use nautilus_model::{
    accounts::AccountAny,
    enums::{AccountType, OmsType},
    identifiers::{AccountId, ClientId, TraderId, Venue, VenueOrderId},
    orders::Order,
    reports::{ExecutionMassStatus, FillReport, OrderStatusReport, PositionStatusReport},
    types::{AccountBalance, Currency, MarginBalance, Money},
};
use tokio::task::JoinHandle;
use tracing::{Instrument, debug, error, info, info_span};

use crate::client::{TInvestClientError, TInvestGrpcClient};
use crate::common::convert::{
    convert_futures_position_to_report, convert_operation_item_to_fill_reports,
    convert_order_state_to_report, convert_security_position_to_report, f64_to_quotation,
    order_side_to_tinvest, order_type_to_tinvest,
};
use crate::proto::{
    GetMaxLotsRequest, GetMaxLotsResponse, OperationsRequest, OperationsResponse, PortfolioRequest,
    PortfolioResponse,
};
use crate::stream::core::TInvestOrderStateStream;

/// Provides live order execution via the T-Invest gRPC API.
///
/// Implements the [`ExecutionClient`] trait using the T-Invest Orders/Operations
/// gRPC services with [`ExecutionClientCore`] for identity/state and
/// [`ExecutionEventEmitter`] for async event dispatch.
#[derive(Debug)]
pub struct TInvestLiveExecutionClient {
    core: ExecutionClientCore,
    clock: &'static AtomicTime,
    emitter: ExecutionEventEmitter,
    grpc_client: TInvestGrpcClient,
    pending_tasks: Mutex<Vec<JoinHandle<()>>>,
}

impl TInvestLiveExecutionClient {
    /// Creates a new [`TInvestLiveExecutionClient`].
    #[must_use]
    pub fn new(
        trader_id: TraderId,
        client_id: ClientId,
        account_id: AccountId,
        base_currency: Option<Currency>,
        grpc_client: TInvestGrpcClient,
    ) -> Self {
        let clock = get_atomic_clock_realtime();
        let cache = Rc::new(RefCell::new(Cache::default()));
        let core = ExecutionClientCore::new(
            trader_id,
            client_id,
            Venue::new("TINVEST"),
            OmsType::Netting,
            account_id,
            AccountType::Cash,
            base_currency,
            Rc::clone(&cache),
        );
        let emitter = ExecutionEventEmitter::new(
            clock,
            trader_id,
            account_id,
            AccountType::Cash,
            base_currency,
        );

        Self {
            core,
            clock,
            emitter,
            grpc_client,
            pending_tasks: Mutex::new(Vec::new()),
        }
    }

    /// Spawn an async task and track its handle.
    fn spawn_task<F>(&self, description: &'static str, fut: F)
    where
        F: Future<Output = anyhow::Result<()>> + Send + 'static,
    {
        let span = info_span!("tinvest_exec", task = description);
        let runtime = get_runtime();
        let handle = runtime.spawn(
            async move {
                if let Err(e) = fut.await {
                    error!("{description} failed: {e}");
                }
            }
            .instrument(span),
        );

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

    /// Get the current portfolio for the given account.
    ///
    /// Calls `OperationsService::GetPortfolio`.
    pub async fn get_portfolio(
        &self,
        account_id: &str,
    ) -> Result<PortfolioResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_portfolio: account={account_id}");

        let mut stub = self.grpc_client.operations().await?;
        let request = PortfolioRequest {
            account_id: account_id.to_string(),
            currency: None,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_portfolio(request).await?;
        let resp = response.into_inner();
        info!(
            "Portfolio for {}: {} positions",
            account_id,
            resp.positions.len(),
        );
        Ok(resp)
    }

    /// Get operations for the given account.
    ///
    /// Calls `OperationsService::GetOperations` (deprecated).
    #[allow(deprecated)]
    pub async fn get_operations(
        &self,
        account_id: &str,
        figi: &Option<String>,
        from: &Option<chrono::DateTime<chrono::Utc>>,
        to: &Option<chrono::DateTime<chrono::Utc>>,
    ) -> Result<OperationsResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_operations: account={account_id}");

        let mut stub = self.grpc_client.operations().await?;

        let from_ts = from.map(|dt| prost_types::Timestamp {
            seconds: dt.timestamp(),
            nanos: dt.timestamp_subsec_nanos() as i32,
        });
        let to_ts = to.map(|dt| prost_types::Timestamp {
            seconds: dt.timestamp(),
            nanos: dt.timestamp_subsec_nanos() as i32,
        });

        let request = OperationsRequest {
            account_id: account_id.to_string(),
            figi: figi.clone(),
            from: from_ts,
            to: to_ts,
            state: None,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_operations(request).await?;
        let resp = response.into_inner();
        info!(
            "Operations for {}: {} items",
            account_id,
            resp.operations.len(),
        );
        Ok(resp)
    }

    /// Calculate the maximum available lots for buy/sell.
    ///
    /// Calls `OrdersService::GetMaxLots`.
    pub async fn get_max_lots(
        &self,
        account_id: &str,
        figi: &str,
        price: Option<f64>,
    ) -> Result<GetMaxLotsResponse, TInvestClientError> {
        if !self.grpc_client.is_connected() {
            return Err(TInvestClientError::NotConnected);
        }

        info!("get_max_lots: account={account_id}, figi={figi}");

        let mut stub = self.grpc_client.orders().await?;
        let price_quotation = price.map(f64_to_quotation);

        let request = GetMaxLotsRequest {
            account_id: account_id.to_string(),
            instrument_id: figi.to_string(),
            price: price_quotation,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_max_lots(request).await?;
        let resp = response.into_inner();
        info!("Max lots for {}: currency={}", figi, resp.currency,);
        Ok(resp)
    }

    /// Start the order state stream and wire callbacks to the [`ExecutionEventEmitter`].
    ///
    /// Dispatches `OrderStateStreamResponse::order_state` messages through the emitter
    /// based on the execution report status.
    pub async fn start_order_state_stream(&self) -> Result<(), tonic::Status> {
        let account_id = self.core.account_id.to_string();
        let core_account_id = self.core.account_id;

        let stream = TInvestOrderStateStream::new(self.grpc_client.clone());

        stream
            .start(
                &account_id,
                move |response: crate::proto::OrderStateStreamResponse| {
                    if let Some(payload) = response.payload {
                        use crate::proto::order_state_stream_response::Payload;

                        if let Payload::OrderState(order_state) = payload {
                            info!(
                                "Order state update: order_id={}, direction={}, status={}, lots_req={}, lots_exec={}",
                                order_state.order_id,
                                order_state.direction,
                                order_state.execution_report_status,
                                order_state.lots_requested,
                                order_state.lots_executed,
                            );

                            // The order_state_stream_response::OrderState is a different type
                            // from proto::OrderState. Full event emission with cache-based
                            // order lookup requires additional conversion logic.
                            // For now, the stream is wired and events are logged.
                            let _ = core_account_id;
                        }
                    }
                },
            )
            .await?;

        info!("Order state stream started with ExecutionClient integration");
        Ok(())
    }

    /// Fetch the account portfolio from the API and emit an [`AccountState`] event.
    ///
    /// Calls `OperationsService::GetPortfolio`, converts the response to
    /// [`AccountBalance`] and emits through the [`ExecutionEventEmitter`].
    pub fn update_account_state(&self) {
        let grpc_client = self.grpc_client.clone();
        let account_id_str = self.core.account_id.to_string();
        let emitter = self.emitter.clone();
        let clock = self.clock;

        self.spawn_task("update_account_state", async move {
            let mut stub = grpc_client.operations().await?;
            let request = PortfolioRequest {
                account_id: account_id_str.clone(),
                currency: None,
            };
            let request = grpc_client.with_auth(tonic::Request::new(request));
            let response = stub.get_portfolio(request).await?;
            let portfolio = response.into_inner();

            let ts_event = clock.get_time_ns();

            // Convert total_amount_portfolio to AccountBalance
            let mut balances: Vec<AccountBalance> = Vec::new();
            if let Some(total) = &portfolio.total_amount_portfolio {
                let currency = Currency::from(total.currency.as_str());
                let total_f64 = total.units as f64 + total.nano as f64 * 1e-9;
                let total_money = Money::new(total_f64, currency);
                let locked_money = Money::new(0.0, currency);
                let free_money = Money::new(total_f64, currency);
                balances.push(AccountBalance {
                    currency,
                    total: total_money,
                    locked: locked_money,
                    free: free_money,
                });
            }

            let margins: Vec<MarginBalance> = Vec::new();

            emitter.emit_account_state(balances, margins, false, ts_event);
            info!("Account state emitted for {account_id_str}");
            Ok(())
        });
    }
}

#[async_trait(?Send)]
impl ExecutionClient for TInvestLiveExecutionClient {
    fn is_connected(&self) -> bool {
        self.core.is_connected()
    }

    fn client_id(&self) -> ClientId {
        self.core.client_id
    }

    fn account_id(&self) -> AccountId {
        self.core.account_id
    }

    fn venue(&self) -> Venue {
        self.core.venue
    }

    fn oms_type(&self) -> OmsType {
        self.core.oms_type
    }

    fn get_account(&self) -> Option<AccountAny> {
        self.core.cache().account_owned(&self.core.account_id)
    }

    fn generate_account_state(
        &self,
        balances: Vec<AccountBalance>,
        margins: Vec<MarginBalance>,
        reported: bool,
        ts_event: UnixNanos,
    ) -> anyhow::Result<()> {
        self.emitter
            .emit_account_state(balances, margins, reported, ts_event);
        Ok(())
    }

    fn start(&mut self) -> anyhow::Result<()> {
        info!("Starting T-Invest execution client");
        let exec_sender = nautilus_common::live::runner::get_exec_event_sender();
        self.emitter.set_sender(exec_sender);
        self.core.set_started();
        Ok(())
    }

    fn stop(&mut self) -> anyhow::Result<()> {
        info!("Stopping T-Invest execution client");
        self.abort_pending_tasks();
        self.core.set_stopped();
        Ok(())
    }

    async fn connect(&mut self) -> anyhow::Result<()> {
        self.grpc_client.connect().await?;
        self.core.set_connected();
        info!(
            "Connected T-Invest execution client for account {account_id}",
            account_id = self.core.account_id
        );
        Ok(())
    }

    async fn disconnect(&mut self) -> anyhow::Result<()> {
        self.abort_pending_tasks();
        self.grpc_client.disconnect().await;
        self.core.set_disconnected();
        info!("Disconnected T-Invest execution client");
        Ok(())
    }

    #[allow(deprecated)]
    fn submit_order(&self, cmd: SubmitOrder) -> anyhow::Result<()> {
        let grpc_client = self.grpc_client.clone();
        let account_id = self.core.account_id.to_string();
        let instrument_id = cmd.instrument_id;
        let figi = instrument_id.symbol.to_string();
        let client_order_id = cmd.client_order_id;
        let quantity = cmd.order_init.quantity.as_f64() as i64;
        let side = order_side_to_tinvest(cmd.order_init.order_side.as_ref());
        let order_type_str = cmd.order_init.order_type.as_ref().to_string();
        let order_type = order_type_to_tinvest(&order_type_str);
        let price = cmd
            .order_init
            .price
            .map(|p| p.as_f64())
            .map(f64_to_quotation);
        let trigger_price = cmd
            .order_init
            .trigger_price
            .map(|p| p.as_f64())
            .map(f64_to_quotation);
        let emitter = self.emitter.clone();
        let ts_event = self.clock.get_time_ns();

        // Try to get the order from cache (should be there, put by framework)
        let order = self.core.get_order(&client_order_id)?;
        emitter.emit_order_submitted(&order);

        // F3: stop-orders are routed to StopOrdersService::PostStopOrder
        let is_stop = matches!(
            order_type_str.as_str(),
            "STOP_MARKET" | "STOP_LIMIT" | "MARKET_IF_TOUCHED" | "LIMIT_IF_TOUCHED"
        );

        info!(
            "Submitting order: figi={}, side={}, qty={}, type={}, client_oid={}, stop={is_stop}",
            figi, side, quantity, order_type, client_order_id,
        );

        self.spawn_task("submit_order", async move {
            if is_stop {
                // Map Nautilus stop type → T-Invest (stop_order_type, exchange_order_type)
                // stop_order_type: 1=TakeProfit, 2=StopLoss, 3=StopLimit
                // exchange_order_type: 1=Market, 2=Limit
                let (stop_order_type, exchange_order_type, stop_price, limit_price) =
                    match order_type_str.as_str() {
                        "STOP_MARKET" => (2, 1, trigger_price, None),
                        "STOP_LIMIT" => (3, 2, trigger_price, price),
                        "MARKET_IF_TOUCHED" => (1, 1, trigger_price, None),
                        "LIMIT_IF_TOUCHED" => (1, 2, trigger_price, price),
                        _ => unreachable!("stop order already checked"),
                    };

                let mut stub = grpc_client.stop_orders().await?;
                let request = crate::proto::PostStopOrderRequest {
                    figi: None, // deprecated, use instrument_id
                    quantity,
                    price: limit_price,
                    stop_price,
                    direction: side,
                    account_id: account_id.clone(),
                    expiration_type: 1,
                    stop_order_type,
                    instrument_id: figi.clone(),
                    order_id: client_order_id.to_string(),
                    expire_date: None,
                    exchange_order_type,
                    take_profit_type: if stop_order_type == 1 { 1 } else { 0 },
                    trailing_data: None,
                    price_type: 0,
                    confirm_margin_trade: false,
                    instant_execution: None,
                };
                let request = grpc_client.with_auth(tonic::Request::new(request));

                match stub.post_stop_order(request).await {
                    Ok(response) => {
                        let resp = response.into_inner();
                        let venue_order_id = VenueOrderId::new(&resp.stop_order_id);
                        info!(
                            "Stop-order submitted successfully: stop_order_id={}",
                            resp.stop_order_id,
                        );
                        emitter.emit_order_accepted(&order, venue_order_id, ts_event);
                    }
                    Err(e) => {
                        error!(
                            "Failed to submit stop-order: {e} (instrument={figi}, client_oid={client_order_id})",
                        );
                        emitter.emit_order_rejected(&order, &format!("{e}"), ts_event, false);
                        return Err(e.into());
                    }
                }
            } else {
                let mut stub = grpc_client.orders().await?;
                let request = crate::proto::PostOrderRequest {
                    figi: Some(figi.clone()),
                    quantity,
                    price,
                    direction: side,
                    account_id: account_id.clone(),
                    order_type,
                    order_id: client_order_id.to_string(),
                    instrument_id: figi.clone(),
                    time_in_force: 1,
                    price_type: 2,
                    confirm_margin_trade: false,
                };
                let request = grpc_client.with_auth(tonic::Request::new(request));

                match stub.post_order(request).await {
                    Ok(response) => {
                        let resp = response.into_inner();
                        let venue_order_id = VenueOrderId::new(&resp.order_id);
                        info!(
                            "Order submitted successfully: order_id={}, status={}",
                            resp.order_id,
                            resp.execution_report_status,
                        );
                        emitter.emit_order_accepted(&order, venue_order_id, ts_event);
                    }
                    Err(e) => {
                        error!(
                            "Failed to submit order: {e} (instrument={figi}, client_oid={client_order_id})",
                        );
                        emitter.emit_order_rejected(&order, &format!("{e}"), ts_event, false);
                        return Err(e.into());
                    }
                }
            }
            Ok(())
        });

        Ok(())
    }

    fn submit_order_list(&self, cmd: SubmitOrderList) -> anyhow::Result<()> {
        debug!("submit_order_list called: {cmd:?}");
        Ok(())
    }

    #[allow(deprecated)]
    fn modify_order(&self, cmd: ModifyOrder) -> anyhow::Result<()> {
        let grpc_client = self.grpc_client.clone();
        let account_id = self.core.account_id.to_string();
        let venue_order_id = cmd
            .venue_order_id
            .map(|id| id.to_string())
            .unwrap_or_default();
        let quantity = cmd.quantity.map(|q| q.as_f64() as i64).unwrap_or(0);
        let price = cmd.price.map(|p| p.as_f64()).map(f64_to_quotation);
        let idempotency_key = cmd.client_order_id.to_string();
        let emitter = self.emitter.clone();
        let client_order_id = cmd.client_order_id;
        let ts_event = self.clock.get_time_ns();

        // Try to get the order from cache
        let order = self.core.get_order(&client_order_id)?;

        info!(
            "Modifying order: venue_order_id={}, qty={}",
            venue_order_id, quantity,
        );

        self.spawn_task("modify_order", async move {
            let mut stub = grpc_client.orders().await?;
            let request = crate::proto::ReplaceOrderRequest {
                account_id: account_id.clone(),
                order_id_type: Some(1),
                order_id: venue_order_id.clone(),
                idempotency_key,
                quantity,
                price,
                price_type: Some(2),
                confirm_margin_trade: false,
            };
            let request = grpc_client.with_auth(tonic::Request::new(request));

            match stub.replace_order(request).await {
                Ok(response) => {
                    let resp = response.into_inner();
                    let venue_oid = VenueOrderId::new(&resp.order_id);
                    info!(
                        "Order modified: order_id={}, status={}",
                        resp.order_id, resp.execution_report_status,
                    );
                    let order_qty = order.quantity();
                    emitter.emit_order_updated(
                        &order,
                        venue_oid,
                        order_qty,
                        order.price(),
                        order.trigger_price(),
                        None,
                        ts_event,
                    );
                }
                Err(e) => {
                    error!("Failed to modify order: {e} (venue_oid={venue_order_id})");
                    emitter.emit_order_modify_rejected(
                        &order,
                        Some(VenueOrderId::new(&venue_order_id)),
                        &format!("{e}"),
                        ts_event,
                    );
                    return Err(e.into());
                }
            }
            Ok(())
        });

        Ok(())
    }

    fn batch_modify_orders(&self, cmd: BatchModifyOrders) -> anyhow::Result<()> {
        debug!("batch_modify_orders called: {cmd:?}");
        Ok(())
    }

    fn cancel_order(&self, cmd: CancelOrder) -> anyhow::Result<()> {
        let grpc_client = self.grpc_client.clone();
        let account_id = self.core.account_id.to_string();
        let venue_order_id = cmd
            .venue_order_id
            .map(|id| id.to_string())
            .unwrap_or_else(|| cmd.client_order_id.to_string());
        let emitter = self.emitter.clone();
        let client_order_id = cmd.client_order_id;
        let venue_oid = VenueOrderId::new(&venue_order_id);
        let ts_event = self.clock.get_time_ns();

        // Try to get the order from cache
        let order = self.core.get_order(&client_order_id)?;

        info!("Cancelling order: venue_order_id={}", venue_order_id);

        self.spawn_task("cancel_order", async move {
            let mut stub = grpc_client.orders().await?;
            let request = crate::proto::CancelOrderRequest {
                account_id: account_id.clone(),
                order_id: venue_order_id.clone(),
                order_id_type: Some(1),
            };
            let request = grpc_client.with_auth(tonic::Request::new(request));

            match stub.cancel_order(request).await {
                Ok(_) => {
                    info!("Order cancelled: {}", venue_order_id);
                    emitter.emit_order_canceled(&order, Some(venue_oid), ts_event);
                }
                Err(e) => {
                    error!("Failed to cancel order: {e} (venue_oid={venue_order_id})");
                    emitter.emit_order_cancel_rejected(
                        &order,
                        Some(venue_oid),
                        &format!("{e}"),
                        ts_event,
                    );
                    return Err(e.into());
                }
            }
            Ok(())
        });

        Ok(())
    }

    fn cancel_all_orders(&self, cmd: CancelAllOrders) -> anyhow::Result<()> {
        debug!("cancel_all_orders called: {cmd:?}");
        Ok(())
    }

    fn batch_cancel_orders(&self, cmd: BatchCancelOrders) -> anyhow::Result<()> {
        debug!("batch_cancel_orders called: {cmd:?}");
        Ok(())
    }

    fn query_account(&self, _cmd: QueryAccount) -> anyhow::Result<()> {
        info!("Querying account state for {}", self.core.account_id);
        self.update_account_state();
        Ok(())
    }

    fn query_order(&self, cmd: QueryOrder) -> anyhow::Result<()> {
        debug!("query_order called: {cmd:?}");
        Ok(())
    }

    async fn generate_order_status_report(
        &self,
        cmd: &GenerateOrderStatusReport,
    ) -> anyhow::Result<Option<OrderStatusReport>> {
        let account_id_str = self.core.account_id.to_string();

        info!("generate_order_status_report: account={account_id_str}");

        let mut stub = self.grpc_client.orders().await?;
        let order_id = cmd
            .venue_order_id
            .as_ref()
            .map(|id| id.to_string())
            .unwrap_or_else(|| String::from("0"));

        let request = crate::proto::GetOrderStateRequest {
            account_id: account_id_str,
            order_id,
            price_type: 1,
            order_id_type: Some(1),
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        match stub.get_order_state(request).await {
            Ok(response) => {
                let order_state = response.into_inner();
                let ts_init = self.clock.get_time_ns();
                let report =
                    convert_order_state_to_report(&order_state, self.core.account_id, ts_init);
                info!(
                    "Order status report: order_id={}, status={:?}",
                    order_state.order_id, order_state.execution_report_status,
                );
                Ok(Some(report))
            }
            Err(e) => {
                error!("Failed to get order state: {e}");
                Err(e.into())
            }
        }
    }

    async fn generate_order_status_reports(
        &self,
        _cmd: &GenerateOrderStatusReports,
    ) -> anyhow::Result<Vec<OrderStatusReport>> {
        let account_id_str = self.core.account_id.to_string();

        info!("generate_order_status_reports: account={account_id_str}");

        let mut stub = self.grpc_client.orders().await?;
        let request = crate::proto::GetOrdersRequest {
            account_id: account_id_str,
            advanced_filters: None,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_orders(request).await?;
        let orders_response = response.into_inner();
        let ts_init = self.clock.get_time_ns();
        let reports: Vec<OrderStatusReport> = orders_response
            .orders
            .iter()
            .map(|order| convert_order_state_to_report(order, self.core.account_id, ts_init))
            .collect();

        info!("Order status reports: {} orders retrieved", reports.len(),);
        Ok(reports)
    }

    async fn generate_fill_reports(
        &self,
        cmd: GenerateFillReports,
    ) -> anyhow::Result<Vec<FillReport>> {
        let account_id_str = self.core.account_id.to_string();

        info!("generate_fill_reports: account={account_id_str}");

        let mut stub = self.grpc_client.operations().await?;
        let mut all_reports: Vec<FillReport> = Vec::new();
        let ts_init = self.clock.get_time_ns();

        let from = cmd.start.map(|ts| prost_types::Timestamp {
            seconds: (ts.as_u64() / 1_000_000_000) as i64,
            nanos: (ts.as_u64() % 1_000_000_000) as i32,
        });
        let to = cmd.end.map(|ts| prost_types::Timestamp {
            seconds: (ts.as_u64() / 1_000_000_000) as i64,
            nanos: (ts.as_u64() % 1_000_000_000) as i32,
        });

        let instrument_id_str = cmd.instrument_id.as_ref().map(|id| id.symbol.to_string());

        let mut cursor: Option<String> = None;
        let limit: i32 = 1000;

        loop {
            let request = crate::proto::GetOperationsByCursorRequest {
                account_id: account_id_str.clone(),
                instrument_id: instrument_id_str.clone(),
                from,
                to,
                cursor: cursor.clone(),
                limit: Some(limit),
                operation_types: vec![],
                state: None,
                without_commissions: Some(false),
                without_trades: Some(false),
                without_overnights: Some(true),
            };
            let request = self.grpc_client.with_auth(tonic::Request::new(request));

            match stub.get_operations_by_cursor(request).await {
                Ok(response) => {
                    let resp = response.into_inner();
                    for item in &resp.items {
                        let fills = convert_operation_item_to_fill_reports(
                            item,
                            self.core.account_id,
                            ts_init,
                        );
                        all_reports.extend(fills);
                    }
                    if resp.has_next {
                        cursor = Some(resp.next_cursor);
                    } else {
                        break;
                    }
                }
                Err(e) => {
                    error!("Failed to get operations: {e}");
                    return Err(e.into());
                }
            }
        }

        info!("Fill reports: {} fills retrieved", all_reports.len(),);
        Ok(all_reports)
    }

    async fn generate_position_status_reports(
        &self,
        _cmd: &GeneratePositionStatusReports,
    ) -> anyhow::Result<Vec<PositionStatusReport>> {
        let account_id_str = self.core.account_id.to_string();

        info!("generate_position_status_reports: account={account_id_str}");

        let mut stub = self.grpc_client.operations().await?;
        let request = crate::proto::PositionsRequest {
            account_id: account_id_str,
        };
        let request = self.grpc_client.with_auth(tonic::Request::new(request));

        let response = stub.get_positions(request).await?;
        let positions = response.into_inner();
        let ts_init = self.clock.get_time_ns();
        let mut reports: Vec<PositionStatusReport> = Vec::new();

        for sec in &positions.securities {
            reports.push(convert_security_position_to_report(
                sec,
                self.core.account_id,
                ts_init,
            ));
        }
        for fut in &positions.futures {
            reports.push(convert_futures_position_to_report(
                fut,
                self.core.account_id,
                ts_init,
            ));
        }

        info!(
            "Position status reports: {} positions ({} securities, {} futures)",
            reports.len(),
            positions.securities.len(),
            positions.futures.len(),
        );
        Ok(reports)
    }

    async fn generate_mass_status(
        &self,
        _lookback_mins: Option<u64>,
    ) -> anyhow::Result<Option<ExecutionMassStatus>> {
        let account_id_str = self.core.account_id.to_string();
        let ts_init = self.clock.get_time_ns();

        info!("generate_mass_status: account={account_id_str}");

        // Aggregate all reports
        let order_reports = self
            .generate_order_status_reports(&GenerateOrderStatusReports::new(
                UUID4::new(),
                ts_init,
                false,
                None,
                None,
                None,
                None,
                None,
            ))
            .await
            .unwrap_or_default();

        let fill_reports = self
            .generate_fill_reports(GenerateFillReports::new(
                UUID4::new(),
                ts_init,
                None,
                None,
                None,
                None,
                None,
                None,
            ))
            .await
            .unwrap_or_default();

        let position_reports = self
            .generate_position_status_reports(&GeneratePositionStatusReports::new(
                UUID4::new(),
                ts_init,
                None,
                None,
                None,
                None,
                None,
            ))
            .await
            .unwrap_or_default();

        let mut mass_status = ExecutionMassStatus::new(
            self.core.client_id,
            self.core.account_id,
            self.core.venue,
            ts_init,
            Some(UUID4::new()),
        );
        mass_status.add_order_reports(order_reports);
        mass_status.add_fill_reports(fill_reports);
        mass_status.add_position_reports(position_reports);

        info!(
            "Mass status: {} orders, {} fills, {} positions",
            mass_status.order_reports().len(),
            mass_status
                .fill_reports()
                .values()
                .map(|v| v.len())
                .sum::<usize>(),
            mass_status.position_reports().len(),
        );
        Ok(Some(mass_status))
    }
}
