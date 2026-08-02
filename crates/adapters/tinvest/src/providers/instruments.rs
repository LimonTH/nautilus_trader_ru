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

//! Instrument provider for T-Invest API.

use std::collections::HashMap;

use nautilus_core::UnixNanos;
use nautilus_model::identifiers::InstrumentId;
use nautilus_model::instruments::{Instrument, any::InstrumentAny};

use crate::client::TInvestGrpcClient;
use crate::common::convert::{
    convert_bond_to_instrument, convert_currency_to_instrument, convert_etf_to_instrument,
    convert_future_to_instrument, convert_share_to_instrument,
};
use crate::proto::InstrumentsRequest;

/// Loads and caches instrument definitions from T-Invest API.
#[derive(Debug)]
pub struct TInvestInstrumentProvider {
    grpc_client: TInvestGrpcClient,
    instruments: HashMap<InstrumentId, InstrumentAny>,
}

impl TInvestInstrumentProvider {
    pub fn new(grpc_client: TInvestGrpcClient) -> Self {
        Self {
            grpc_client,
            instruments: HashMap::new(),
        }
    }

    /// Load all available instruments from T-Invest API.
    pub async fn load_all(&mut self) -> anyhow::Result<()> {
        let ts_init = UnixNanos::default();
        let request = InstrumentsRequest {
            instrument_status: Some(1), // INSTRUMENT_STATUS_BASE
            instrument_exchange: None,
        };
        let mut stub = self.grpc_client.instruments().await?;

        // Load shares
        tracing::info!("Loading shares from T-Invest API...");
        let shares_response = stub
            .shares(self.grpc_client.with_auth(tonic::Request::new(request)))
            .await?;
        for share in &shares_response.get_ref().instruments {
            let instrument = convert_share_to_instrument(share, ts_init.as_u64());
            self.instruments.insert(instrument.id(), instrument);
        }
        tracing::info!(
            "Loaded {} shares",
            shares_response.get_ref().instruments.len()
        );

        // Load bonds
        tracing::info!("Loading bonds from T-Invest API...");
        let bonds_response = stub
            .bonds(self.grpc_client.with_auth(tonic::Request::new(request)))
            .await?;
        for bond in &bonds_response.get_ref().instruments {
            let instrument = convert_bond_to_instrument(bond, ts_init.as_u64());
            self.instruments.insert(instrument.id(), instrument);
        }
        tracing::info!(
            "Loaded {} bonds",
            bonds_response.get_ref().instruments.len()
        );

        // Load futures
        tracing::info!("Loading futures from T-Invest API...");
        let futures_response = stub
            .futures(self.grpc_client.with_auth(tonic::Request::new(request)))
            .await?;
        for future in &futures_response.get_ref().instruments {
            let instrument = convert_future_to_instrument(future, ts_init.as_u64());
            self.instruments.insert(instrument.id(), instrument);
        }
        tracing::info!(
            "Loaded {} futures",
            futures_response.get_ref().instruments.len()
        );

        // Load ETFs
        tracing::info!("Loading ETFs from T-Invest API...");
        let etfs_response = stub
            .etfs(self.grpc_client.with_auth(tonic::Request::new(request)))
            .await?;
        for etf in &etfs_response.get_ref().instruments {
            let instrument = convert_etf_to_instrument(etf, ts_init.as_u64());
            self.instruments.insert(instrument.id(), instrument);
        }
        tracing::info!("Loaded {} ETFs", etfs_response.get_ref().instruments.len());

        // Load currencies
        tracing::info!("Loading currencies from T-Invest API...");
        let currencies_response = stub
            .currencies(self.grpc_client.with_auth(tonic::Request::new(request)))
            .await?;
        for currency in &currencies_response.get_ref().instruments {
            let instrument = convert_currency_to_instrument(currency, ts_init.as_u64());
            self.instruments.insert(instrument.id(), instrument);
        }
        tracing::info!(
            "Loaded {} currencies",
            currencies_response.get_ref().instruments.len()
        );

        tracing::info!(
            "T-Invest instrument provider loaded {} instruments total",
            self.instruments.len()
        );

        Ok(())
    }

    /// Get a cached instrument by ID.
    pub fn get(&self, instrument_id: &InstrumentId) -> Option<&InstrumentAny> {
        self.instruments.get(instrument_id)
    }

    /// Get all cached instruments.
    pub fn all(&self) -> &HashMap<InstrumentId, InstrumentAny> {
        &self.instruments
    }

    /// Get the number of cached instruments.
    pub fn len(&self) -> usize {
        self.instruments.len()
    }

    /// Returns true if no instruments are cached.
    pub fn is_empty(&self) -> bool {
        self.instruments.is_empty()
    }
}
