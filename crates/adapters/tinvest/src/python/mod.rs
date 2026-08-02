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

//! PyO3 module for T-Invest adapter bindings.

pub mod config;
pub mod factories;
pub mod stream;

use nautilus_common::factories::{ClientConfig, DataClientFactory, ExecutionClientFactory};
use nautilus_core::python::{to_pyruntime_err, to_pyvalue_err};
use nautilus_system::get_global_pyo3_registry;
use pyo3::prelude::*;

use crate::config::TInvestClientConfig;
use crate::factories::{TINVEST, TInvestDataClientFactory, TInvestExecutionClientFactory};
use crate::python::factories::PyTInvestGrpcClient;
use crate::python::stream::{
    PyTInvestMarketDataStream, PyTInvestOrderStateStream, PyTInvestPortfolioStream,
    PyTInvestPositionsStream,
};

// ---------------------------------------------------------------------------
// Factory extractors (bridges from Python PyAny to Rust trait objects)
// ---------------------------------------------------------------------------

#[expect(clippy::needless_pass_by_value)]
fn extract_tinvest_data_factory(
    py: Python<'_>,
    factory: Py<PyAny>,
) -> PyResult<Box<dyn DataClientFactory>> {
    match factory.extract::<TInvestDataClientFactory>(py) {
        Ok(f) => Ok(Box::new(f)),
        Err(e) => Err(to_pyvalue_err(format!(
            "Failed to extract TInvestDataClientFactory: {e}"
        ))),
    }
}

#[expect(clippy::needless_pass_by_value)]
fn extract_tinvest_exec_factory(
    py: Python<'_>,
    factory: Py<PyAny>,
) -> PyResult<Box<dyn ExecutionClientFactory>> {
    match factory.extract::<TInvestExecutionClientFactory>(py) {
        Ok(f) => Ok(Box::new(f)),
        Err(e) => Err(to_pyvalue_err(format!(
            "Failed to extract TInvestExecutionClientFactory: {e}"
        ))),
    }
}

#[expect(clippy::needless_pass_by_value)]
fn extract_tinvest_config(py: Python<'_>, config: Py<PyAny>) -> PyResult<Box<dyn ClientConfig>> {
    match config.extract::<TInvestClientConfig>(py) {
        Ok(c) => Ok(Box::new(c)),
        Err(e) => Err(to_pyvalue_err(format!(
            "Failed to extract TInvestClientConfig: {e}"
        ))),
    }
}

/// Loaded as `nautilus_pyo3.tinvest`.
///
/// # Errors
///
/// Returns an error if any bindings fail to register with the Python module.
#[pymodule]
pub fn tinvest(_: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TInvestClientConfig>()?;
    m.add_class::<PyTInvestGrpcClient>()?;
    m.add_class::<TInvestDataClientFactory>()?;
    m.add_class::<TInvestExecutionClientFactory>()?;

    // Native streaming classes
    m.add_class::<PyTInvestMarketDataStream>()?;
    m.add_class::<PyTInvestOrderStateStream>()?;
    m.add_class::<PyTInvestPortfolioStream>()?;
    m.add_class::<PyTInvestPositionsStream>()?;

    let registry = get_global_pyo3_registry();

    // Register data factory extractor
    if let Err(e) =
        registry.register_factory_extractor(TINVEST.to_string(), extract_tinvest_data_factory)
    {
        return Err(to_pyruntime_err(format!(
            "Failed to register T-Invest data factory extractor: {e}"
        )));
    }

    // Register execution factory extractor
    if let Err(e) =
        registry.register_exec_factory_extractor(TINVEST.to_string(), extract_tinvest_exec_factory)
    {
        return Err(to_pyruntime_err(format!(
            "Failed to register T-Invest exec factory extractor: {e}"
        )));
    }

    // Register config extractor
    if let Err(e) = registry
        .register_config_extractor("TInvestClientConfig".to_string(), extract_tinvest_config)
    {
        return Err(to_pyruntime_err(format!(
            "Failed to register T-Invest config extractor: {e}"
        )));
    }

    Ok(())
}
