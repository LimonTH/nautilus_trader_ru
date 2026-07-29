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

//! PyO3 bindings for native gRPC streaming.
//!
//! Provides Python classes that wrap the thread-based native stream types from
//! [`crate::stream::native`] and bridge data into Python's asyncio event loop
//! via [`asyncio.Queue`].

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use tracing::{error, info, warn};

use crate::client::TInvestGrpcClient;
use crate::python::factories::PyTInvestGrpcClient;
use crate::stream::native::{
    NativeMarketDataStream, NativeOrderStateStream, NativePortfolioStream, NativePositionsStream,
};

// -------------------------------------------------------------------------------------------
// Helper: create an asyncio.Queue and a putter callback
// -------------------------------------------------------------------------------------------

fn create_async_queue(
    py: Python<'_>,
    _event_loop: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let asyncio = py.import("asyncio")?;
    let queue = asyncio.call_method0("Queue")?;
    let queue_obj: Py<PyAny> = queue.clone().unbind();

    let locals = PyDict::new(py);
    locals.set_item("_queue", &queue)?;
    let putter: Py<PyAny> = py
        .eval(c"lambda data: _queue.put_nowait(data)", Some(&locals), None)?
        .unbind();

    Ok((queue_obj, putter))
}

fn make_data_callback(
    queue: Py<PyAny>,
    event_loop: Py<PyAny>,
) -> Box<dyn Fn(Py<PyDict>) + Send + 'static> {
    Box::new(move |data: Py<PyDict>| {
        let result = Python::attach(|py| {
            let locals = PyDict::new(py);
            let _ = locals.set_item("_queue", queue.bind(py));
            let putter = py
                .eval(c"lambda d: _queue.put_nowait(d)", Some(&locals), None)
                .map(|v| v.unbind());
            match putter {
                Ok(putter) => {
                    let loop_ref = event_loop.bind(py);
                    loop_ref.call_method1("call_soon_threadsafe", (putter, data)).map(|_| ())
                }
                Err(e) => Err(e),
            }
        });
        if let Err(e) = result {
            error!("Stream callback error: {e}");
        }
    })
}

// -------------------------------------------------------------------------------------------
// PyTInvestMarketDataStream
// -------------------------------------------------------------------------------------------

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")]
#[pyo3::pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.tinvest",
    name = "TInvestMarketDataStream"
)]
#[derive(Debug)]
#[allow(dead_code)]
pub struct PyTInvestMarketDataStream {
    inner: Option<NativeMarketDataStream>,
    #[pyo3(get)]
    queue: Py<PyAny>,
    event_loop: Py<PyAny>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl PyTInvestMarketDataStream {
    #[new]
    pub fn py_new(client: Py<PyAny>, event_loop: Bound<'_, PyAny>) -> PyResult<Self> {
        let grpc_client: TInvestGrpcClient = extract_grpc_client(&client)?;
        let event_loop_obj: Py<PyAny> = event_loop.clone().unbind();
        let (queue, _putter) = create_async_queue(event_loop.py(), &event_loop)?;
        let on_data = make_data_callback(queue.clone_ref(event_loop.py()), event_loop_obj.clone_ref(event_loop.py()));
        let native = NativeMarketDataStream::new(grpc_client, on_data);

        Ok(Self {
            inner: Some(native),
            queue,
            event_loop: event_loop_obj,
        })
    }

    #[pyo3(signature = (instrument_ids, subscription_type))]
    pub fn subscribe(
        slf: &Bound<'_, Self>,
        instrument_ids: Vec<String>,
        subscription_type: String,
    ) -> PyResult<()> {
        let this = slf.borrow();
        let inner = this.inner.as_ref().ok_or_else(|| {
            PyRuntimeError::new_err("Stream already stopped")
        })?;

        match subscription_type.as_str() {
            "trades" => inner.subscribe_trades(&instrument_ids),
            "orderbook" => inner.subscribe_order_book(&instrument_ids, 20),
            "info" => inner.subscribe_info(&instrument_ids),
            "candles" => {
                warn!("Candle subscription via bidirectional stream is not supported");
            }
            other => {
                return Err(PyRuntimeError::new_err(format!(
                    "Unknown subscription_type: {other}"
                )));
            }
        }
        Ok(())
    }

    #[pyo3(signature = (instrument_ids, subscription_type))]
    pub fn unsubscribe(
        slf: &Bound<'_, Self>,
        instrument_ids: Vec<String>,
        subscription_type: String,
    ) -> PyResult<()> {
        let this = slf.borrow();
        let inner = this.inner.as_ref().ok_or_else(|| {
            PyRuntimeError::new_err("Stream already stopped")
        })?;

        match subscription_type.as_str() {
            "trades" => inner.unsubscribe_trades(&instrument_ids),
            "orderbook" => inner.unsubscribe_order_book(&instrument_ids, 20),
            other => {
                return Err(PyRuntimeError::new_err(format!(
                    "Unknown subscription_type: {other}"
                )));
            }
        }
        Ok(())
    }

    pub fn stop(slf: Bound<'_, Self>) -> PyResult<()> {
        let mut this = slf.borrow_mut(); if let Some(native) = this.inner.take() {
            native.stop();
            info!("PyTInvestMarketDataStream: stopped");
        }
        Ok(())
    }

    #[getter]
    pub fn is_active(&self) -> bool {
        self.inner.as_ref().is_some_and(|s| s.is_active())
    }
}

impl Drop for PyTInvestMarketDataStream {
    fn drop(&mut self) {
        if let Some(native) = self.inner.take() {
            native.stop();
        }
    }
}

// -------------------------------------------------------------------------------------------
// PyTInvestOrderStateStream
// -------------------------------------------------------------------------------------------

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")]
#[pyo3::pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.tinvest",
    name = "TInvestOrderStateStream"
)]
#[derive(Debug)]
pub struct PyTInvestOrderStateStream {
    inner: Option<NativeOrderStateStream>,
    #[pyo3(get)]
    queue: Py<PyAny>,
    event_loop: Py<PyAny>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl PyTInvestOrderStateStream {
    #[new]
    pub fn py_new(client: Py<PyAny>, event_loop: Bound<'_, PyAny>) -> PyResult<Self> {
        let _grpc_client = extract_grpc_client(&client)?;
        let event_loop_obj: Py<PyAny> = event_loop.clone().unbind();
        let (queue, _putter) = create_async_queue(event_loop.py(), &event_loop)?;

        Ok(Self {
            inner: None,
            queue,
            event_loop: event_loop_obj,
        })
    }

    pub fn start(
        slf: &Bound<'_, Self>,
        client: Py<PyAny>,
        accounts: Vec<String>,
    ) -> PyResult<()> {
        let mut this = slf.borrow_mut();
        if this.inner.is_some() {
            return Err(PyRuntimeError::new_err("Stream already started"));
        }
        let grpc_client = extract_grpc_client(&client)?;
        let on_data = make_data_callback(
            this.queue.clone_ref(slf.py()),
            this.event_loop.clone_ref(slf.py()),
        );
        let native = NativeOrderStateStream::new(grpc_client, accounts, on_data);
        this.inner = Some(native);
        Ok(())
    }

    pub fn stop(slf: Bound<'_, Self>) -> PyResult<()> {
        let mut this = slf.borrow_mut(); if let Some(native) = this.inner.take() {
            native.stop();
            info!("PyTInvestOrderStateStream: stopped");
        }
        Ok(())
    }

    #[getter]
    pub fn is_active(&self) -> bool {
        self.inner.as_ref().is_some_and(|s| s.is_active())
    }
}

impl Drop for PyTInvestOrderStateStream {
    fn drop(&mut self) {
        if let Some(native) = self.inner.take() {
            native.stop();
        }
    }
}

// -------------------------------------------------------------------------------------------
// PyTInvestPortfolioStream
// -------------------------------------------------------------------------------------------

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")]
#[pyo3::pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.tinvest",
    name = "TInvestPortfolioStream"
)]
#[derive(Debug)]
pub struct PyTInvestPortfolioStream {
    inner: Option<NativePortfolioStream>,
    #[pyo3(get)]
    queue: Py<PyAny>,
    event_loop: Py<PyAny>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl PyTInvestPortfolioStream {
    #[new]
    pub fn py_new(client: Py<PyAny>, event_loop: Bound<'_, PyAny>) -> PyResult<Self> {
        let _grpc_client = extract_grpc_client(&client)?;
        let event_loop_obj: Py<PyAny> = event_loop.clone().unbind();
        let (queue, _putter) = create_async_queue(event_loop.py(), &event_loop)?;

        Ok(Self {
            inner: None,
            queue,
            event_loop: event_loop_obj,
        })
    }

    pub fn start(
        slf: &Bound<'_, Self>,
        client: Py<PyAny>,
        accounts: Vec<String>,
    ) -> PyResult<()> {
        let mut this = slf.borrow_mut();
        if this.inner.is_some() {
            return Err(PyRuntimeError::new_err("Stream already started"));
        }
        let grpc_client = extract_grpc_client(&client)?;
        let on_data = make_data_callback(
            this.queue.clone_ref(slf.py()),
            this.event_loop.clone_ref(slf.py()),
        );
        let native = NativePortfolioStream::new(grpc_client, accounts, on_data);
        this.inner = Some(native);
        Ok(())
    }

    pub fn stop(slf: Bound<'_, Self>) -> PyResult<()> {
        let mut this = slf.borrow_mut(); if let Some(native) = this.inner.take() {
            native.stop();
            info!("PyTInvestPortfolioStream: stopped");
        }
        Ok(())
    }

    #[getter]
    pub fn is_active(&self) -> bool {
        self.inner.as_ref().is_some_and(|s| s.is_active())
    }
}

impl Drop for PyTInvestPortfolioStream {
    fn drop(&mut self) {
        if let Some(native) = self.inner.take() {
            native.stop();
        }
    }
}

// -------------------------------------------------------------------------------------------
// PyTInvestPositionsStream
// -------------------------------------------------------------------------------------------

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")]
#[pyo3::pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.tinvest",
    name = "TInvestPositionsStream"
)]
#[derive(Debug)]
pub struct PyTInvestPositionsStream {
    inner: Option<NativePositionsStream>,
    #[pyo3(get)]
    queue: Py<PyAny>,
    event_loop: Py<PyAny>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl PyTInvestPositionsStream {
    #[new]
    pub fn py_new(client: Py<PyAny>, event_loop: Bound<'_, PyAny>) -> PyResult<Self> {
        let _grpc_client = extract_grpc_client(&client)?;
        let event_loop_obj: Py<PyAny> = event_loop.clone().unbind();
        let (queue, _putter) = create_async_queue(event_loop.py(), &event_loop)?;

        Ok(Self {
            inner: None,
            queue,
            event_loop: event_loop_obj,
        })
    }

    pub fn start(
        slf: &Bound<'_, Self>,
        client: Py<PyAny>,
        accounts: Vec<String>,
    ) -> PyResult<()> {
        let mut this = slf.borrow_mut();
        if this.inner.is_some() {
            return Err(PyRuntimeError::new_err("Stream already started"));
        }
        let grpc_client = extract_grpc_client(&client)?;
        let on_data = make_data_callback(
            this.queue.clone_ref(slf.py()),
            this.event_loop.clone_ref(slf.py()),
        );
        let native = NativePositionsStream::new(grpc_client, accounts, on_data);
        this.inner = Some(native);
        Ok(())
    }

    pub fn stop(slf: Bound<'_, Self>) -> PyResult<()> {
        let mut this = slf.borrow_mut(); if let Some(native) = this.inner.take() {
            native.stop();
            info!("PyTInvestPositionsStream: stopped");
        }
        Ok(())
    }

    #[getter]
    pub fn is_active(&self) -> bool {
        self.inner.as_ref().is_some_and(|s| s.is_active())
    }
}

impl Drop for PyTInvestPositionsStream {
    fn drop(&mut self) {
        if let Some(native) = self.inner.take() {
            native.stop();
        }
    }
}

// -------------------------------------------------------------------------------------------
// Helper: extract TInvestGrpcClient from Python object
// -------------------------------------------------------------------------------------------

fn extract_grpc_client(client: &Py<PyAny>) -> PyResult<TInvestGrpcClient> {
    Python::attach(|py| {
        let py_client: PyTInvestGrpcClient = client
            .extract::<PyTInvestGrpcClient>(py)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to extract PyTInvestGrpcClient: {e}")))?;
        Ok(py_client.inner.clone())
    })
}
