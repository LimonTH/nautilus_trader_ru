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

//! PyO3 bindings for T-Invest configuration types.

use pyo3::prelude::*;

use crate::config::TInvestClientConfig;

/// Configuration for the T-Invest gRPC client.
#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl TInvestClientConfig {
    #[new]
    pub fn py_new(
        token: String,
        target: Option<String>,
        sandbox: Option<bool>,
        connection_timeout_ms: Option<u64>,
        keepalive_ms: Option<u64>,
        max_message_size: Option<usize>,
        max_retries: Option<u32>,
        retry_wait_ms: Option<u64>,
        trader_id: Option<String>,
        account_id: Option<String>,
        ca_cert_path: Option<String>,
    ) -> Self {
        Self {
            token,
            target: target.unwrap_or_else(|| crate::config::DEFAULT_TARGET.to_string()),
            sandbox: sandbox.unwrap_or(false),
            connection_timeout_ms: connection_timeout_ms
                .unwrap_or(crate::config::DEFAULT_CONNECTION_TIMEOUT_MS),
            keepalive_ms: keepalive_ms.unwrap_or(crate::config::DEFAULT_KEEPALIVE_MS),
            max_message_size: max_message_size.unwrap_or(16_777_216),
            max_retries: max_retries.unwrap_or(3),
            retry_wait_ms: retry_wait_ms.unwrap_or(2_000),
            trader_id,
            account_id,
            ca_cert_path,
        }
    }

    #[getter]
    pub fn token(&self) -> String {
        self.token.clone()
    }

    #[getter]
    pub fn target(&self) -> String {
        self.target.clone()
    }

    #[getter]
    pub fn sandbox(&self) -> bool {
        self.sandbox
    }

    #[getter]
    pub fn connection_timeout_ms(&self) -> u64 {
        self.connection_timeout_ms
    }

    #[getter]
    pub fn keepalive_ms(&self) -> u64 {
        self.keepalive_ms
    }

    #[getter]
    pub fn ca_cert_path(&self) -> Option<String> {
        self.ca_cert_path.clone()
    }
}