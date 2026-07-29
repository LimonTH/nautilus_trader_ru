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

use serde::{Deserialize, Serialize};

/// Default T-Invest API target URL (production).
pub const DEFAULT_TARGET: &str = "invest-public-api.tbank.ru:443";

/// Default T-Invest Sandbox API target URL.
pub const DEFAULT_SANDBOX_TARGET: &str = "sandbox-invest-public-api.tbank.ru:443";

/// Default connection timeout in milliseconds.
pub const DEFAULT_CONNECTION_TIMEOUT_MS: u64 = 30_000;

/// Default keepalive interval in milliseconds.
pub const DEFAULT_KEEPALIVE_MS: u64 = 60_000;

/// Configuration for the T-Invest gRPC client.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
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
pub struct TInvestClientConfig {
    /// API token for T-Invest API authentication.
    pub token: String,
    /// Target gRPC endpoint (host:port).
    pub target: String,
    /// Whether to use the sandbox environment.
    pub sandbox: bool,
    /// Connection timeout in milliseconds.
    pub connection_timeout_ms: u64,
    /// Keepalive interval in milliseconds.
    pub keepalive_ms: u64,
    /// Maximum gRPC message size in bytes.
    pub max_message_size: usize,
    /// Maximum number of retry attempts for failed requests.
    pub max_retries: u32,
    /// Initial retry wait duration in milliseconds.
    pub retry_wait_ms: u64,
    /// Optional trader ID (required for execution client).
    pub trader_id: Option<String>,
    /// Optional account ID (required for execution client).
    pub account_id: Option<String>,
    /// Optional path to a custom CA certificate bundle (PEM format).
    /// Required for connecting to T-Invest API with Russian Trusted Root CA certificates.
    pub ca_cert_path: Option<String>,
}

impl Default for TInvestClientConfig {
    fn default() -> Self {
        Self {
            token: String::new(),
            target: DEFAULT_TARGET.to_string(),
            sandbox: false,
            connection_timeout_ms: DEFAULT_CONNECTION_TIMEOUT_MS,
            keepalive_ms: DEFAULT_KEEPALIVE_MS,
            max_message_size: 16_777_216, // 16 MB
            max_retries: 3,
            retry_wait_ms: 2_000,
            trader_id: None,
            account_id: None,
            ca_cert_path: None,
        }
    }
}

impl TInvestClientConfig {
    /// Returns the effective target URL based on sandbox flag.
    pub fn effective_target(&self) -> &str {
        if self.sandbox {
            DEFAULT_SANDBOX_TARGET
        } else {
            &self.target
        }
    }
}