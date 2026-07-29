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

#![cfg(feature = "python")]

use nautilus_tinvest::{
    config::TInvestClientConfig,
    python,
};
use pyo3::{Py, Python, types::PyModule};
use rstest::rstest;

#[rstest]
fn test_tinvest_python_module_registers() {
    Python::initialize();

    Python::attach(|py| {
        // Register module in sys.modules so #[pymodule] can initialize classes properly
        let module = PyModule::new(py, "tinvest").expect("TInvest module should be created");
        let sys = PyModule::import(py, "sys").expect("sys module should be importable");
        sys.call_method1("modules", ())
            .expect("sys.modules should be accessible")
            .set_item("nautilus_trader.core.nautilus_pyo3.tinvest", &module)
            .expect("module should be registered in sys.modules");

        python::tinvest(py, &module).expect("TInvest Python module should register");

        // Verify classes are registered in the module
        let config_class = module.getattr("TInvestClientConfig");
        assert!(
            config_class.is_ok(),
            "TInvestClientConfig should be registered in the module: {:?}",
            config_class.err(),
        );

        let grpc_class = module.getattr("TInvestGrpcClient");
        assert!(
            grpc_class.is_ok(),
            "TInvestGrpcClient should be registered in the module: {:?}",
            grpc_class.err(),
        );
    });
}

#[rstest]
fn test_tinvest_client_config_py_conversion() {
    Python::initialize();

    Python::attach(|py| {
        let config = TInvestClientConfig {
            token: "test_token".to_string(),
            target: "invest-public-api.tbank.ru:443".to_string(),
            sandbox: true,
            connection_timeout_ms: 30_000,
            keepalive_ms: 60_000,
            max_message_size: 16_777_216,
            max_retries: 3,
            retry_wait_ms: 2_000,
        };

        let py_config = Py::new(py, config.clone())
            .expect("TInvestClientConfig should convert to Python object");

        let extracted: TInvestClientConfig = py_config
            .extract(py)
            .expect("TInvestClientConfig should extract from Python object");

        assert_eq!(extracted.token, "test_token");
        assert_eq!(extracted.sandbox, true);
        assert_eq!(extracted.target, "invest-public-api.tbank.ru:443");
    });
}
