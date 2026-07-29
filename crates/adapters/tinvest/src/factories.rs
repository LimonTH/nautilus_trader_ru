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

//! Factory functions for creating T-Invest clients.
//!
//! Implements [`DataClientFactory`] and [`ExecutionClientFactory`] so that the
//! live system kernel can construct [`TInvestLiveMarketDataClient`] and
//! [`TInvestLiveExecutionClient`] from configuration objects alone.

use std::{any::Any, cell::RefCell, rc::Rc};

use nautilus_common::{
    cache::CacheView,
    clients::{DataClient, ExecutionClient},
    clock::Clock,
    factories::{ClientConfig, DataClientFactory, ExecutionClientFactory},
};
use nautilus_model::identifiers::{AccountId, ClientId, TraderId};

use crate::config::TInvestClientConfig;
use crate::data::core::TInvestLiveMarketDataClient;
use crate::execution::core::TInvestLiveExecutionClient;

/// Venue identifier constant.
pub const TINVEST: &str = "TINVEST";

// ---------------------------------------------------------------------------
// ClientConfig impl
// ---------------------------------------------------------------------------

impl ClientConfig for TInvestClientConfig {
    fn as_any(&self) -> &dyn Any {
        self
    }
}

// ---------------------------------------------------------------------------
// DataClientFactory
// ---------------------------------------------------------------------------

/// Factory for creating T-Invest live market data clients.
#[derive(Debug, Clone)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(
        module = "nautilus_trader.core.nautilus_pyo3.tinvest",
        from_py_object
    )
)]
#[cfg_attr(
    feature = "python",
    pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")
)]
pub struct TInvestDataClientFactory;

impl TInvestDataClientFactory {
    #[must_use]
    pub const fn new() -> Self {
        Self
    }
}

impl Default for TInvestDataClientFactory {
    fn default() -> Self {
        Self::new()
    }
}

impl DataClientFactory for TInvestDataClientFactory {
    fn create(
        &self,
        name: &str,
        config: &dyn ClientConfig,
        _cache: CacheView,
        _clock: Rc<RefCell<dyn Clock>>,
    ) -> anyhow::Result<Box<dyn DataClient>> {
        let tinvest_config = config
            .as_any()
            .downcast_ref::<TInvestClientConfig>()
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "Invalid config type for TInvestDataClientFactory. \
                     Expected TInvestClientConfig, was {config:?}",
                )
            })?
            .clone();

        let client_id = ClientId::from(name);
        let grpc_client = crate::client::TInvestGrpcClient::new(tinvest_config)?;
        let client = TInvestLiveMarketDataClient::new(client_id, grpc_client);
        Ok(Box::new(client))
    }

    fn name(&self) -> &'static str {
        TINVEST
    }

    fn config_type(&self) -> &'static str {
        "TInvestClientConfig"
    }
}

// ---------------------------------------------------------------------------
// ExecutionClientFactory
// ---------------------------------------------------------------------------

/// Factory for creating T-Invest live execution clients.
#[derive(Debug, Clone)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(
        module = "nautilus_trader.core.nautilus_pyo3.tinvest",
        from_py_object
    )
)]
#[cfg_attr(
    feature = "python",
    pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")
)]
pub struct TInvestExecutionClientFactory;

impl TInvestExecutionClientFactory {
    #[must_use]
    pub const fn new() -> Self {
        Self
    }
}

impl Default for TInvestExecutionClientFactory {
    fn default() -> Self {
        Self::new()
    }
}

impl ExecutionClientFactory for TInvestExecutionClientFactory {
    fn create(
        &self,
        name: &str,
        config: &dyn ClientConfig,
        _cache: CacheView,
    ) -> anyhow::Result<Box<dyn ExecutionClient>> {
        let tinvest_config = config
            .as_any()
            .downcast_ref::<TInvestClientConfig>()
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "Invalid config type for TInvestExecutionClientFactory. \
                     Expected TInvestClientConfig, was {config:?}",
                )
            })?
            .clone();

        let trader_id = tinvest_config
            .trader_id
            .as_deref()
            .map(TraderId::new)
            .unwrap_or_else(|| TraderId::new("TRADER-000"));

        let account_id = tinvest_config
            .account_id
            .as_deref()
            .map(AccountId::new)
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "TInvestClientConfig.account_id is required for execution client"
                )
            })?;

        let client_id = ClientId::from(name);
        let grpc_client = crate::client::TInvestGrpcClient::new(tinvest_config)?;
        let client = TInvestLiveExecutionClient::new(
            trader_id,
            client_id,
            account_id,
            None, // base_currency
            grpc_client,
        );
        Ok(Box::new(client))
    }

    fn name(&self) -> &'static str {
        TINVEST
    }

    fn config_type(&self) -> &'static str {
        "TInvestClientConfig"
    }
}
