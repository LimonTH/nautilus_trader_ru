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

//! PyO3 bindings for T-Invest gRPC client.
//!
//! Provides a [`PyTInvestGrpcClient`] that wraps [`TInvestGrpcClient`] and exposes
//! all data and execution methods to Python via PyO3 async bindings.

use pyo3::exceptions::{PyConnectionError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use tracing::warn;

use crate::client::TInvestGrpcClient;
use crate::config::TInvestClientConfig;
use crate::proto;

// ---------------------------------------------------------------------------
// Helper functions: convert proto types to Python dicts
// ---------------------------------------------------------------------------

fn quotation_to_dict<'a>(py: Python<'a>, q: &'a proto::Quotation) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("units", q.units)?;
    d.set_item("nano", q.nano)?;
    Ok(d)
}

fn money_value_to_dict<'a>(
    py: Python<'a>,
    mv: &'a proto::MoneyValue,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("currency", &mv.currency)?;
    d.set_item("units", mv.units)?;
    d.set_item("nano", mv.nano)?;
    Ok(d)
}

fn order_state_to_dict<'a>(
    py: Python<'a>,
    os: &'a proto::OrderState,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("order_id", &os.order_id)?;
    d.set_item("execution_report_status", os.execution_report_status)?;
    d.set_item("lots_requested", os.lots_requested)?;
    d.set_item("lots_executed", os.lots_executed)?;
    d.set_item(
        "initial_order_price",
        os.initial_order_price
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "executed_order_price",
        os.executed_order_price
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "total_order_amount",
        os.total_order_amount
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "average_position_price",
        os.average_position_price
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "initial_commission",
        os.initial_commission
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "executed_commission",
        os.executed_commission
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item("figi", &os.figi)?;
    d.set_item("direction", os.direction)?;
    d.set_item(
        "initial_security_price",
        os.initial_security_price
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    // stages: repeated OrderStage
    let stages_list = PyList::new(py, &[] as &[Py<PyAny>])?;
    for stage in &os.stages {
        let sd = PyDict::new(py);
        sd.set_item(
            "price",
            stage
                .price
                .as_ref()
                .map(|mv| money_value_to_dict(py, mv))
                .transpose()?,
        )?;
        sd.set_item("quantity", stage.quantity)?;
        sd.set_item("trade_id", &stage.trade_id)?;
        sd.set_item(
            "execution_time",
            stage.execution_time.as_ref().map(|t| t.seconds).unwrap_or(0),
        )?;
        stages_list.append(sd)?;
    }
    d.set_item("stages", stages_list)?;
    d.set_item(
        "service_commission",
        os.service_commission
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item("currency", &os.currency)?;
    d.set_item("order_type", os.order_type)?;
    d.set_item(
        "order_date",
        os.order_date.as_ref().map(|t| t.seconds).unwrap_or(0),
    )?;
    d.set_item("instrument_uid", &os.instrument_uid)?;
    d.set_item("order_request_id", &os.order_request_id)?;
    d.set_item("ticker", &os.ticker)?;
    d.set_item("class_code", &os.class_code)?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// Helper: InstrumentShort proto → Python dict
// ---------------------------------------------------------------------------

fn instrument_short_to_dict<'a>(
    py: Python<'a>,
    inst: &'a proto::InstrumentShort,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("isin", &inst.isin)?;
    d.set_item("figi", &inst.figi)?;
    d.set_item("ticker", &inst.ticker)?;
    d.set_item("class_code", &inst.class_code)?;
    d.set_item("instrument_type", &inst.instrument_type)?;
    d.set_item("name", &inst.name)?;
    d.set_item("uid", &inst.uid)?;
    d.set_item("position_uid", &inst.position_uid)?;
    d.set_item("instrument_kind", inst.instrument_kind)?;
    d.set_item("api_trade_available_flag", inst.api_trade_available_flag)?;
    d.set_item("for_iis_flag", inst.for_iis_flag)?;
    d.set_item(
        "first_1min_candle_date",
        inst.first_1min_candle_date
            .as_ref()
            .map(|t| t.seconds)
            .unwrap_or(0),
    )?;
    d.set_item(
        "first_1day_candle_date",
        inst.first_1day_candle_date
            .as_ref()
            .map(|t| t.seconds)
            .unwrap_or(0),
    )?;
    d.set_item("for_qual_investor_flag", inst.for_qual_investor_flag)?;
    d.set_item("weekend_flag", inst.weekend_flag)?;
    d.set_item("blocked_tca_flag", inst.blocked_tca_flag)?;
    d.set_item("lot", inst.lot)?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// Helper: convert a Share/Bond/Future/Etf/Currency proto to a generic Python dict
// ---------------------------------------------------------------------------

fn share_to_dict<'a>(
    py: Python<'a>,
    s: &'a proto::Share,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &s.figi)?;
    d.set_item("ticker", &s.ticker)?;
    d.set_item("class_code", &s.class_code)?;
    d.set_item("isin", &s.isin)?;
    d.set_item("lot", s.lot)?;
    d.set_item("currency", &s.currency)?;
    d.set_item("name", &s.name)?;
    d.set_item("exchange", &s.exchange)?;
    d.set_item("uid", &s.uid)?;
    d.set_item("instrument_type", "share")?;
    Ok(d)
}

fn bond_to_dict<'a>(
    py: Python<'a>,
    b: &'a proto::Bond,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &b.figi)?;
    d.set_item("ticker", &b.ticker)?;
    d.set_item("class_code", &b.class_code)?;
    d.set_item("isin", &b.isin)?;
    d.set_item("lot", b.lot)?;
    d.set_item("currency", &b.currency)?;
    d.set_item("name", &b.name)?;
    d.set_item("exchange", &b.exchange)?;
    d.set_item("uid", &b.uid)?;
    d.set_item("instrument_type", "bond")?;
    Ok(d)
}

fn future_to_dict<'a>(
    py: Python<'a>,
    f: &'a proto::Future,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &f.figi)?;
    d.set_item("ticker", &f.ticker)?;
    d.set_item("class_code", &f.class_code)?;
    d.set_item("lot", f.lot)?;
    d.set_item("currency", &f.currency)?;
    d.set_item("name", &f.name)?;
    d.set_item("exchange", &f.exchange)?;
    d.set_item("uid", &f.uid)?;
    d.set_item("instrument_type", "future")?;
    Ok(d)
}

fn etf_to_dict<'a>(
    py: Python<'a>,
    e: &'a proto::Etf,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &e.figi)?;
    d.set_item("ticker", &e.ticker)?;
    d.set_item("class_code", &e.class_code)?;
    d.set_item("isin", &e.isin)?;
    d.set_item("lot", e.lot)?;
    d.set_item("currency", &e.currency)?;
    d.set_item("name", &e.name)?;
    d.set_item("exchange", &e.exchange)?;
    d.set_item("uid", &e.uid)?;
    d.set_item("instrument_type", "etf")?;
    Ok(d)
}

fn currency_to_dict<'a>(
    py: Python<'a>,
    c: &'a proto::Currency,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &c.figi)?;
    d.set_item("ticker", &c.ticker)?;
    d.set_item("class_code", &c.class_code)?;
    d.set_item("isin", &c.isin)?;
    d.set_item("lot", c.lot)?;
    d.set_item("currency", &c.currency)?;
    d.set_item("name", &c.name)?;
    d.set_item("exchange", &c.exchange)?;
    d.set_item("uid", &c.uid)?;
    d.set_item("instrument_type", "currency")?;
    Ok(d)
}

fn option_to_dict<'a>(
    py: Python<'a>,
    o: &'a proto::Option,
) -> PyResult<Bound<'a, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("figi", &o.uid)?; // Options use uid as primary identifier
    d.set_item("ticker", &o.ticker)?;
    d.set_item("class_code", &o.class_code)?;
    d.set_item("lot", o.lot)?;
    d.set_item("currency", &o.currency)?;
    d.set_item("name", &o.name)?;
    d.set_item("exchange", &o.exchange)?;
    d.set_item("uid", &o.uid)?;
    d.set_item("instrument_type", "option")?;
    d.set_item("direction", o.direction)?;
    d.set_item(
        "basic_asset_size",
        o.basic_asset_size
            .as_ref()
            .map(|q| quotation_to_dict(py, q))
            .transpose()?,
    )?;
    d.set_item(
        "strike_price",
        o.strike_price
            .as_ref()
            .map(|mv| money_value_to_dict(py, mv))
            .transpose()?,
    )?;
    d.set_item(
        "expiration_date",
        o.expiration_date.as_ref().map(|t| t.seconds).unwrap_or(0),
    )?;
    d.set_item(
        "first_trade_date",
        o.first_trade_date.as_ref().map(|t| t.seconds).unwrap_or(0),
    )?;
    d.set_item("basic_asset", &o.basic_asset)?;
    d.set_item(
        "min_price_increment",
        o.min_price_increment
            .as_ref()
            .map(|q| quotation_to_dict(py, q))
            .transpose()?,
    )?;
    d.set_item("style", o.style)?;
    d.set_item("settlement_type", o.settlement_type)?;
    d.set_item("api_trade_available_flag", o.api_trade_available_flag)?;
    d.set_item("buy_available_flag", o.buy_available_flag)?;
    d.set_item("sell_available_flag", o.sell_available_flag)?;
    d.set_item("for_qual_investor_flag", o.for_qual_investor_flag)?;
    d.set_item("short_enabled_flag", o.short_enabled_flag)?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// PyTInvestGrpcClient
// ---------------------------------------------------------------------------

/// Python wrapper around TInvestGrpcClient.
#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "nautilus_trader.adapters.tinvest")]
#[pyo3::pyclass(
    module = "nautilus_trader.core.nautilus_pyo3.tinvest",
    name = "TInvestGrpcClient",
    from_py_object
)]
#[derive(Clone, Debug)]
pub struct PyTInvestGrpcClient {
    pub inner: TInvestGrpcClient,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl PyTInvestGrpcClient {
    // -----------------------------------------------------------------------
    // Constructor / lifecycle
    // -----------------------------------------------------------------------

    #[new]
    pub fn py_new(config: TInvestClientConfig) -> PyResult<Self> {
        let inner = TInvestGrpcClient::new(config)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    pub fn connect<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            inner
                .connect()
                .await
                .map_err(|e| PyConnectionError::new_err(e.to_string()))
        })
    }

    pub fn disconnect<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            inner.disconnect().await;
            Ok(())
        })
    }

    #[getter]
    pub fn is_connected(&self) -> bool {
        self.inner.is_connected()
    }

    // -----------------------------------------------------------------------
    // Data methods (6)
    // -----------------------------------------------------------------------

    /// Load all instruments from T-Invest: shares, bonds, futures, ETFs, currencies.
    pub fn request_instruments<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut instruments_stub = inner.instruments().await.map_err(|e| {
                PyRuntimeError::new_err(format!("instruments service: {e}"))
            })?;
            let request = proto::InstrumentsRequest {
                instrument_status: Some(1), // INSTRUMENT_STATUS_BASE
                instrument_exchange: None,
            };

            let mut all_instruments: Vec<proto::InstrumentShort> = Vec::new();

            // Shares
            {
                let req = inner.with_auth(tonic::Request::new(request));
                match instruments_stub.shares(req).await {
                    Ok(resp) => {
                        for s in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: s.isin.clone(),
                                figi: s.figi.clone(),
                                ticker: s.ticker.clone(),
                                class_code: s.class_code.clone(),
                                instrument_type: "share".to_string(),
                                name: s.name.clone(),
                                uid: s.uid.clone(),
                                position_uid: s.position_uid.clone(),
                                instrument_kind: 2, // INSTRUMENT_TYPE_SHARE
                                api_trade_available_flag: s.api_trade_available_flag,
                                for_iis_flag: s.for_iis_flag,
                                first_1min_candle_date: s.first_1min_candle_date,
                                first_1day_candle_date: s.first_1day_candle_date,
                                for_qual_investor_flag: s.for_qual_investor_flag,
                                weekend_flag: s.weekend_flag,
                                blocked_tca_flag: s.blocked_tca_flag,
                                lot: s.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load shares: {e}");
                    }
                }
            }

            // Bonds
            {
                let req = inner.with_auth(tonic::Request::new(request));
                match instruments_stub.bonds(req).await {
                    Ok(resp) => {
                        for b in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: b.isin.clone(),
                                figi: b.figi.clone(),
                                ticker: b.ticker.clone(),
                                class_code: b.class_code.clone(),
                                instrument_type: "bond".to_string(),
                                name: b.name.clone(),
                                uid: b.uid.clone(),
                                position_uid: b.position_uid.clone(),
                                instrument_kind: 1, // INSTRUMENT_TYPE_BOND
                                api_trade_available_flag: b.api_trade_available_flag,
                                for_iis_flag: b.for_iis_flag,
                                first_1min_candle_date: b.first_1min_candle_date,
                                first_1day_candle_date: b.first_1day_candle_date,
                                for_qual_investor_flag: b.for_qual_investor_flag,
                                weekend_flag: b.weekend_flag,
                                blocked_tca_flag: b.blocked_tca_flag,
                                lot: b.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load bonds: {e}");
                    }
                }
            }

            // Futures
            {
                let req = inner.with_auth(tonic::Request::new(request));
                match instruments_stub.futures(req).await {
                    Ok(resp) => {
                        for f in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: String::new(),
                                figi: f.figi.clone(),
                                ticker: f.ticker.clone(),
                                class_code: f.class_code.clone(),
                                instrument_type: "future".to_string(),
                                name: f.name.clone(),
                                uid: f.uid.clone(),
                                position_uid: f.position_uid.clone(),
                                instrument_kind: 5, // INSTRUMENT_TYPE_FUTURES
                                api_trade_available_flag: f.api_trade_available_flag,
                                for_iis_flag: f.for_iis_flag,
                                first_1min_candle_date: f.first_1min_candle_date,
                                first_1day_candle_date: f.first_1day_candle_date,
                                for_qual_investor_flag: f.for_qual_investor_flag,
                                weekend_flag: f.weekend_flag,
                                blocked_tca_flag: f.blocked_tca_flag,
                                lot: f.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load futures: {e}");
                    }
                }
            }

            // ETFs
            {
                let req = inner.with_auth(tonic::Request::new(request));
                match instruments_stub.etfs(req).await {
                    Ok(resp) => {
                        for et in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: et.isin.clone(),
                                figi: et.figi.clone(),
                                ticker: et.ticker.clone(),
                                class_code: et.class_code.clone(),
                                instrument_type: "etf".to_string(),
                                name: et.name.clone(),
                                uid: et.uid.clone(),
                                position_uid: et.position_uid.clone(),
                                instrument_kind: 4, // INSTRUMENT_TYPE_ETF
                                api_trade_available_flag: et.api_trade_available_flag,
                                for_iis_flag: et.for_iis_flag,
                                first_1min_candle_date: et.first_1min_candle_date,
                                first_1day_candle_date: et.first_1day_candle_date,
                                for_qual_investor_flag: et.for_qual_investor_flag,
                                weekend_flag: et.weekend_flag,
                                blocked_tca_flag: et.blocked_tca_flag,
                                lot: et.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load ETFs: {e}");
                    }
                }
            }

            // Currencies
            {
                let req = inner.with_auth(tonic::Request::new(request));
                match instruments_stub.currencies(req).await {
                    Ok(resp) => {
                        for c in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: c.isin.clone(),
                                figi: c.figi.clone(),
                                ticker: c.ticker.clone(),
                                class_code: c.class_code.clone(),
                                instrument_type: "currency".to_string(),
                                name: c.name.clone(),
                                uid: c.uid.clone(),
                                position_uid: c.position_uid.clone(),
                                instrument_kind: 3, // INSTRUMENT_TYPE_CURRENCY
                                api_trade_available_flag: c.api_trade_available_flag,
                                for_iis_flag: c.for_iis_flag,
                                first_1min_candle_date: c.first_1min_candle_date,
                                first_1day_candle_date: c.first_1day_candle_date,
                                for_qual_investor_flag: c.for_qual_investor_flag,
                                weekend_flag: c.weekend_flag,
                                blocked_tca_flag: c.blocked_tca_flag,
                                lot: c.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load currencies: {e}");
                    }
                }
            }

            // Options (using deprecated Options endpoint for batch loading)
            {
                let req = inner.with_auth(tonic::Request::new(request));
                #[allow(deprecated)]
                match instruments_stub.options(req).await {
                    Ok(resp) => {
                        for o in resp.into_inner().instruments {
                            all_instruments.push(proto::InstrumentShort {
                                isin: String::new(),
                                figi: o.uid.clone(), // Options use uid, not figi
                                ticker: o.ticker.clone(),
                                class_code: o.class_code.clone(),
                                instrument_type: "option".to_string(),
                                name: o.name.clone(),
                                uid: o.uid.clone(),
                                position_uid: o.position_uid.clone(),
                                instrument_kind: 6, // INSTRUMENT_TYPE_OPTION
                                api_trade_available_flag: o.api_trade_available_flag,
                                for_iis_flag: o.for_iis_flag,
                                first_1min_candle_date: o.first_1min_candle_date,
                                first_1day_candle_date: o.first_1day_candle_date,
                                for_qual_investor_flag: o.for_qual_investor_flag,
                                weekend_flag: o.weekend_flag,
                                blocked_tca_flag: o.blocked_tca_flag,
                                lot: o.lot,
                            });
                        }
                    }
                    Err(e) => {
                        warn!("Failed to load options: {e}");
                    }
                }
            }

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for inst in &all_instruments {
                    let d = instrument_short_to_dict(py, inst)?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    /// Lookup a single instrument by figi/uid.
    /// Tries share_by → bond_by → future_by → etf_by → currency_by.
    /// Returns a dict or None.
    pub fn request_instrument<'py>(
        &mut self,
        py: Python<'py>,
        figi: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.instruments().await.map_err(|e| {
                PyRuntimeError::new_err(format!("instruments service: {e}"))
            })?;
            let instrument_request = proto::InstrumentRequest {
                id_type: 0, // INSTRUMENT_ID_UNSPECIFIED — auto-detect
                class_code: None,
                id: figi.clone(),
            };

            // Try share_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.share_by(req).await {
                    if let Some(share) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = share_to_dict(py, &share)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Try bond_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.bond_by(req).await {
                    if let Some(bond) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = bond_to_dict(py, &bond)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Try future_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.future_by(req).await {
                    if let Some(future) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = future_to_dict(py, &future)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Try etf_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.etf_by(req).await {
                    if let Some(etf) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = etf_to_dict(py, &etf)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Try currency_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request.clone()));
                if let Ok(resp) = stub.currency_by(req).await {
                    if let Some(currency) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = currency_to_dict(py, &currency)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Try option_by
            {
                let req = inner.with_auth(tonic::Request::new(instrument_request));
                if let Ok(resp) = stub.option_by(req).await {
                    if let Some(option) = resp.into_inner().instrument {
                        return Python::attach(|py| {
                            let d = option_to_dict(py, &option)?;
                            Ok(d.into_any().unbind())
                        });
                    }
                }
            }

            // Not found — return Python None
            Python::attach(|py| Ok(py.None()))
        })
    }

    /// Request historical candles for an instrument.
    #[pyo3(signature = (figi, interval, from_ts=None, to_ts=None, limit=None))]
    pub fn request_candles<'py>(
        &mut self,
        py: Python<'py>,
        figi: String,
        interval: i32,
        from_ts: Option<i64>,
        to_ts: Option<i64>,
        limit: Option<i32>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut md = inner.market_data().await.map_err(|e| {
                PyRuntimeError::new_err(format!("market_data service: {e}"))
            })?;
            let request = proto::GetCandlesRequest {
                instrument_id: Some(figi.clone()),
                interval,
                from: from_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts,
                    nanos: 0,
                }),
                to: to_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts,
                    nanos: 0,
                }),
                limit,
                ..Default::default()
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = md.get_candles(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_candles: {e}"))
            })?;
            let candles = response.into_inner().candles;

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for c in &candles {
                    let d = PyDict::new(py);
                    d.set_item(
                        "open",
                        c.open
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "high",
                        c.high
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "low",
                        c.low
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "close",
                        c.close
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item("volume", c.volume)?;
                    d.set_item(
                        "time",
                        c.time.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item("is_complete", c.is_complete)?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    /// Request order book for an instrument.
    #[pyo3(signature = (figi, depth))]
    pub fn request_order_book<'py>(
        &mut self,
        py: Python<'py>,
        figi: String,
        depth: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut md = inner.market_data().await.map_err(|e| {
                PyRuntimeError::new_err(format!("market_data service: {e}"))
            })?;
            let request = proto::GetOrderBookRequest {
                instrument_id: Some(figi.clone()),
                depth,
                ..Default::default()
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = md.get_order_book(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_order_book: {e}"))
            })?;
            let book = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("figi", &book.figi)?;
                d.set_item("depth", book.depth)?;

                let bids_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for bid in &book.bids {
                    let bid_d = PyDict::new(py);
                    bid_d.set_item(
                        "price",
                        bid.price
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    bid_d.set_item("quantity", bid.quantity)?;
                    bids_list.append(bid_d)?;
                }
                d.set_item("bids", bids_list)?;

                let asks_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for ask in &book.asks {
                    let ask_d = PyDict::new(py);
                    ask_d.set_item(
                        "price",
                        ask.price
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    ask_d.set_item("quantity", ask.quantity)?;
                    asks_list.append(ask_d)?;
                }
                d.set_item("asks", asks_list)?;

                d.set_item(
                    "time",
                    book.orderbook_ts.as_ref().map(|t| t.seconds).unwrap_or(0),
                )?;
                d.set_item(
                    "last_price",
                    book.last_price
                        .as_ref()
                        .map(|q| quotation_to_dict(py, q))
                        .transpose()?,
                )?;
                d.set_item(
                    "last_price_ts",
                    book.last_price_ts.as_ref().map(|t| t.seconds).unwrap_or(0),
                )?;
                d.set_item(
                    "limit_up",
                    book.limit_up
                        .as_ref()
                        .map(|q| quotation_to_dict(py, q))
                        .transpose()?,
                )?;
                d.set_item(
                    "limit_down",
                    book.limit_down
                        .as_ref()
                        .map(|q| quotation_to_dict(py, q))
                        .transpose()?,
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Request last trades for an instrument.
    #[pyo3(signature = (figi, from_ts, to_ts))]
    pub fn request_trades<'py>(
        &mut self,
        py: Python<'py>,
        figi: String,
        from_ts: i64,
        to_ts: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut md = inner.market_data().await.map_err(|e| {
                PyRuntimeError::new_err(format!("market_data service: {e}"))
            })?;
            let request = proto::GetLastTradesRequest {
                instrument_id: Some(figi.clone()),
                from: Some(prost_types::Timestamp {
                    seconds: from_ts,
                    nanos: 0,
                }),
                to: Some(prost_types::Timestamp {
                    seconds: to_ts,
                    nanos: 0,
                }),
                ..Default::default()
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = md.get_last_trades(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_last_trades: {e}"))
            })?;
            let trades = response.into_inner().trades;

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for t in &trades {
                    let d = PyDict::new(py);
                    d.set_item("figi", &t.figi)?;
                    // direction: TradeDirection enum → string
                    d.set_item(
                        "direction",
                        match t.direction {
                            1 => "BUY",
                            2 => "SELL",
                            _ => "UNSPECIFIED",
                        },
                    )?;
                    d.set_item(
                        "price",
                        t.price
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item("quantity", t.quantity)?;
                    d.set_item(
                        "time",
                        t.time.as_ref().map(|ts| ts.seconds).unwrap_or(0),
                    )?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    /// Get technical analysis indicators for an instrument (F5).
    #[pyo3(signature = (indicator_type, instrument_uid, from_ts, to_ts, interval, type_of_price=1, length=0))]
    pub fn get_tech_analysis<'py>(
        &mut self,
        py: Python<'py>,
        indicator_type: i32,
        instrument_uid: String,
        from_ts: i64,
        to_ts: i64,
        interval: i32,
        type_of_price: i32,
        length: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut md = inner.market_data().await.map_err(|e| {
                PyRuntimeError::new_err(format!("market_data service: {e}"))
            })?;
            let request = proto::GetTechAnalysisRequest {
                indicator_type,
                instrument_uid: instrument_uid.clone(),
                from: Some(prost_types::Timestamp {
                    seconds: from_ts / 1_000_000_000,
                    nanos: (from_ts % 1_000_000_000) as i32,
                }),
                to: Some(prost_types::Timestamp {
                    seconds: to_ts / 1_000_000_000,
                    nanos: (to_ts % 1_000_000_000) as i32,
                }),
                interval,
                type_of_price,
                length,
                deviation: None,
                smoothing: None,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = md.get_tech_analysis(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_tech_analysis: {e}"))
            })?;
            let indicators = response.into_inner().technical_indicators;

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for item in &indicators {
                    let d = PyDict::new(py);
                    d.set_item(
                        "timestamp",
                        item.timestamp.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item(
                        "middle_band",
                        item.middle_band
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "upper_band",
                        item.upper_band
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "lower_band",
                        item.lower_band
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "signal",
                        item.signal
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "macd",
                        item.macd
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    /// Get all accounts for the current token.
    pub fn get_accounts<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut users = inner.users().await.map_err(|e| {
                PyRuntimeError::new_err(format!("users service: {e}"))
            })?;
            let request = proto::GetAccountsRequest {
                status: Some(4), // AccountStatus::All
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = users.get_accounts(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_accounts: {e}"))
            })?;
            let accounts = response.into_inner().accounts;

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for a in &accounts {
                    let d = PyDict::new(py);
                    d.set_item("id", &a.id)?;
                    d.set_item("type", a.r#type)?;
                    d.set_item("name", &a.name)?;
                    d.set_item("status", a.status)?;
                    d.set_item(
                        "opened_date",
                        a.opened_date.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item(
                        "closed_date",
                        a.closed_date.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item("access_level", a.access_level)?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    // -----------------------------------------------------------------------
    // Execution methods (4)
    // -----------------------------------------------------------------------

    /// Post a new order.
    #[allow(deprecated)]
    #[pyo3(signature = (account_id, figi, quantity, price, direction, order_type, order_id))]
    pub fn post_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        figi: String,
        quantity: i64,
        price: Option<f64>,
        direction: i32,
        order_type: i32,
        order_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let price_quotation = price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });
            let request = proto::PostOrderRequest {
                figi: None, // deprecated, use instrument_id instead
                quantity,
                price: price_quotation,
                direction,
                account_id: account_id.clone(),
                order_type,
                order_id: order_id.clone(),
                instrument_id: figi.clone(),
                time_in_force: 1, // TIME_IN_FORCE_DAY
                price_type: 2,    // PRICE_TYPE_CURRENCY
                confirm_margin_trade: false,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.post_order(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("post_order: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("order_id", &resp.order_id)?;
                d.set_item("figi", &resp.figi)?;
                d.set_item("direction", resp.direction)?;
                d.set_item("order_type", resp.order_type)?;
                d.set_item("lots_requested", resp.lots_requested)?;
                d.set_item("lots_executed", resp.lots_executed)?;
                d.set_item(
                    "initial_order_price",
                    resp.initial_order_price
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "executed_order_price",
                    resp.executed_order_price
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_order_amount",
                    resp.total_order_amount
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "initial_commission",
                    resp.initial_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "executed_commission",
                    resp.executed_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "aci_value",
                    resp.aci_value
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                // response_metadata.server_time (NOT .time!)
                d.set_item(
                    "server_time",
                    resp.response_metadata
                        .as_ref()
                        .and_then(|m| m.server_time.as_ref())
                        .map(|t| t.seconds)
                        .unwrap_or(0),
                )?;
                d.set_item("execution_report_status", resp.execution_report_status)?;
                d.set_item("message", &resp.message)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Submit an order asynchronously (PostOrderAsync).
    ///
    /// Returns immediately with an idempotency ``order_request_id`` and the
    /// initial ``execution_report_status``; the final order state is delivered
    /// via the order state stream or polled with ``get_order_state``.
    #[pyo3(signature = (account_id, figi, quantity, price=None, direction=1, order_type=2, order_id=""))]
    pub fn post_order_async<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        figi: String,
        quantity: i64,
        price: Option<f64>,
        direction: i32,
        order_type: i32,
        order_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let price_quotation = price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });
            let request = proto::PostOrderAsyncRequest {
                instrument_id: figi.clone(),
                quantity,
                price: price_quotation,
                direction,
                account_id: account_id.clone(),
                order_type,
                order_id: order_id.clone(),
                time_in_force: None,
                price_type: None,
                confirm_margin_trade: false,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.post_order_async(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("post_order_async: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("order_request_id", &resp.order_request_id)?;
                d.set_item("execution_report_status", resp.execution_report_status)?;
                d.set_item("trade_intent_id", resp.trade_intent_id)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Cancel an existing order.
    #[pyo3(signature = (account_id, order_id))]
    pub fn cancel_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        order_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let request = proto::CancelOrderRequest {
                account_id: account_id.clone(),
                order_id: order_id.clone(),
                order_id_type: Some(1), // ORDER_ID_TYPE_EXCHANGE
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.cancel_order(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("cancel_order: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item(
                    "time",
                    resp.time.as_ref().map(|t| t.seconds).unwrap_or(0),
                )?;
                d.set_item(
                    "server_time",
                    resp.response_metadata
                        .as_ref()
                        .and_then(|m| m.server_time.as_ref())
                        .map(|t| t.seconds)
                        .unwrap_or(0),
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Replace (modify) an existing order.
    #[allow(deprecated)]
    #[pyo3(signature = (account_id, order_id, idempotency_key, quantity, price=None))]
    pub fn replace_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        order_id: String,
        idempotency_key: String,
        quantity: i64,
        price: Option<f64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let price_quotation = price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });
            let request = proto::ReplaceOrderRequest {
                account_id: account_id.clone(),
                order_id_type: Some(1), // ORDER_ID_TYPE_EXCHANGE
                order_id: order_id.clone(),
                idempotency_key: idempotency_key.clone(),
                quantity,
                price: price_quotation,
                price_type: Some(2), // PRICE_TYPE_CURRENCY
                confirm_margin_trade: false,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.replace_order(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("replace_order: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("order_id", &resp.order_id)?;
                d.set_item("figi", &resp.figi)?;
                d.set_item("direction", resp.direction)?;
                d.set_item("order_type", resp.order_type)?;
                d.set_item("lots_requested", resp.lots_requested)?;
                d.set_item("lots_executed", resp.lots_executed)?;
                d.set_item(
                    "initial_order_price",
                    resp.initial_order_price
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "executed_order_price",
                    resp.executed_order_price
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_order_amount",
                    resp.total_order_amount
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "initial_commission",
                    resp.initial_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "executed_commission",
                    resp.executed_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "aci_value",
                    resp.aci_value
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "server_time",
                    resp.response_metadata
                        .as_ref()
                        .and_then(|m| m.server_time.as_ref())
                        .map(|t| t.seconds)
                        .unwrap_or(0),
                )?;
                d.set_item("execution_report_status", resp.execution_report_status)?;
                d.set_item("message", &resp.message)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get order state for a specific order.
    #[pyo3(signature = (account_id, order_id))]
    pub fn get_order_state<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        order_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let request = proto::GetOrderStateRequest {
                account_id: account_id.clone(),
                order_id: order_id.clone(),
                price_type: 1,          // PRICE_TYPE_POINT
                order_id_type: Some(1), // ORDER_ID_TYPE_EXCHANGE
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.get_order_state(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_order_state: {e}"))
            })?;
            let order_state = response.into_inner();

            Python::attach(|py| {
                let d = order_state_to_dict(py, &order_state)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get all active orders for an account.
    #[pyo3(signature = (account_id))]
    pub fn get_orders<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let request = proto::GetOrdersRequest {
                account_id: account_id.clone(),
                advanced_filters: None,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.get_orders(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_orders: {e}"))
            })?;
            let orders_list = response.into_inner().orders;

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for os in &orders_list {
                    let d = order_state_to_dict(py, os)?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    // -----------------------------------------------------------------------
    // Stop-order methods (3)
    // -----------------------------------------------------------------------

    /// Post a stop-order.
    #[pyo3(signature = (account_id, figi, quantity, order_id, price=None, stop_price=None, direction=1, expiration_type=1, stop_order_type=1, exchange_order_type=0, take_profit_type=0))]
    pub fn post_stop_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        figi: String,
        quantity: i64,
        order_id: String,
        price: Option<f64>,
        stop_price: Option<f64>,
        direction: i32,
        expiration_type: i32,
        stop_order_type: i32,
        exchange_order_type: i32,
        take_profit_type: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.stop_orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("stop_orders service: {e}"))
            })?;

            let price_value = price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });

            let stop_price_value = stop_price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });

            #[allow(deprecated)]
            let request = proto::PostStopOrderRequest {
                figi: None, // deprecated, use instrument_id
                quantity,
                price: price_value,
                stop_price: stop_price_value,
                direction,
                account_id: account_id.clone(),
                expiration_type,
                stop_order_type,
                instrument_id: figi.clone(),
                order_id: order_id.clone(),
                expire_date: None,
                exchange_order_type,
                take_profit_type,
                trailing_data: None,
                price_type: 0,
                confirm_margin_trade: false,
                instant_execution: None,
            };

            let req = inner.with_auth(tonic::Request::new(request));
            let response = stub.post_stop_order(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("post_stop_order: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("stop_order_id", &resp.stop_order_id)?;
                d.set_item("order_request_id", &resp.order_request_id)?;
                d.set_item(
                    "server_time",
                    resp.response_metadata
                        .as_ref()
                        .and_then(|m| m.server_time.as_ref())
                        .map(|t| t.seconds)
                        .unwrap_or(0),
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Cancel a stop-order.
    #[pyo3(signature = (account_id, stop_order_id))]
    pub fn cancel_stop_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        stop_order_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.stop_orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("stop_orders service: {e}"))
            })?;

            let request = proto::CancelStopOrderRequest {
                account_id: account_id.clone(),
                stop_order_id: stop_order_id.clone(),
            };

            let req = inner.with_auth(tonic::Request::new(request));
            let response = stub.cancel_stop_order(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("cancel_stop_order: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item(
                    "time",
                    resp.time.as_ref().map(|t| t.seconds).unwrap_or(0),
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Replace an existing stop-order (F4).
    ///
    /// The T-Invest StopOrdersService has no ``ReplaceStopOrder`` RPC, so a
    /// replacement is implemented as *cancel the old stop-order* followed by
    /// *submit a new stop-order* with the updated parameters.
    #[pyo3(signature = (account_id, stop_order_id, figi, quantity, order_id, price=None, stop_price=None, direction=1, expiration_type=1, stop_order_type=1, exchange_order_type=0, take_profit_type=0))]
    pub fn replace_stop_order<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        stop_order_id: String,
        figi: String,
        quantity: i64,
        order_id: String,
        price: Option<f64>,
        stop_price: Option<f64>,
        direction: i32,
        expiration_type: i32,
        stop_order_type: i32,
        exchange_order_type: i32,
        take_profit_type: i32,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.stop_orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("stop_orders service: {e}"))
            })?;

            // 1. Cancel the existing stop-order
            let cancel_request = proto::CancelStopOrderRequest {
                account_id: account_id.clone(),
                stop_order_id: stop_order_id.clone(),
            };
            let cancel_req = inner.with_auth(tonic::Request::new(cancel_request));
            stub.cancel_stop_order(cancel_req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("replace_stop_order cancel: {e}"))
            })?;

            // 2. Post the replacement stop-order
            let price_value = price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });
            let stop_price_value = stop_price.map(|p| {
                let units = p.trunc() as i64;
                let nano = ((p.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            });

            #[allow(deprecated)]
            let post_request = proto::PostStopOrderRequest {
                figi: None, // deprecated, use instrument_id
                quantity,
                price: price_value,
                stop_price: stop_price_value,
                direction,
                account_id: account_id.clone(),
                expiration_type,
                stop_order_type,
                instrument_id: figi.clone(),
                order_id: order_id.clone(),
                expire_date: None,
                exchange_order_type,
                take_profit_type,
                trailing_data: None,
                price_type: 0,
                confirm_margin_trade: false,
                instant_execution: None,
            };
            let post_req = inner.with_auth(tonic::Request::new(post_request));
            let response = stub.post_stop_order(post_req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("replace_stop_order post: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("old_stop_order_id", &stop_order_id)?;
                d.set_item("stop_order_id", &resp.stop_order_id)?;
                d.set_item("order_request_id", &resp.order_request_id)?;
                d.set_item(
                    "server_time",
                    resp.response_metadata
                        .as_ref()
                        .and_then(|m| m.server_time.as_ref())
                        .map(|t| t.seconds)
                        .unwrap_or(0),
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get all active stop-orders for an account.
    #[pyo3(signature = (account_id))]
    pub fn get_stop_orders<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.stop_orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("stop_orders service: {e}"))
            })?;

            let request = proto::GetStopOrdersRequest {
                account_id: account_id.clone(),
                status: 0,
                from: None,
                to: None,
            };

            let req = inner.with_auth(tonic::Request::new(request));
            let response = stub.get_stop_orders(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_stop_orders: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let py_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for order in &resp.stop_orders {
                    let d = PyDict::new(py);
                    d.set_item("stop_order_id", &order.stop_order_id)?;
                    d.set_item("lots_requested", order.lots_requested)?;
                    d.set_item("figi", &order.figi)?;
                    d.set_item("direction", order.direction)?;
                    d.set_item("currency", &order.currency)?;
                    d.set_item("order_type", order.order_type)?;
                    d.set_item(
                        "create_date",
                        order.create_date.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item(
                        "activation_date_time",
                        order.activation_date_time.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    d.set_item(
                        "expiration_time",
                        order.expiration_time.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    // price and stop_price are MoneyValue in StopOrder
                    d.set_item(
                        "price",
                        order.price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    d.set_item(
                        "stop_price",
                        order.stop_price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    d.set_item("instrument_uid", &order.instrument_uid)?;
                    d.set_item("take_profit_type", order.take_profit_type)?;
                    d.set_item("status", order.status)?;
                    d.set_item("exchange_order_type", order.exchange_order_type)?;
                    d.set_item(
                        "exchange_order_id",
                        order.exchange_order_id.as_deref().unwrap_or(""),
                    )?;
                    d.set_item("ticker", &order.ticker)?;
                    d.set_item("class_code", &order.class_code)?;
                    d.set_item("instant_execution", order.instant_execution)?;
                    py_list.append(d)?;
                }
                Ok(py_list.into_any().unbind())
            })
        })
    }

    // -----------------------------------------------------------------------
    // Sandbox methods (3)
    // -----------------------------------------------------------------------

    /// Open a sandbox account.
    #[pyo3(signature = (name=None))]
    pub fn open_sandbox_account<'py>(
        &mut self,
        py: Python<'py>,
        name: Option<String>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.sandbox().await.map_err(|e| {
                PyRuntimeError::new_err(format!("sandbox service: {e}"))
            })?;

            let request = proto::OpenSandboxAccountRequest {
                name,
            };

            let req = inner.with_auth(tonic::Request::new(request));
            let response = stub.open_sandbox_account(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("open_sandbox_account: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("account_id", &resp.account_id)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Close a sandbox account.
    #[pyo3(signature = (account_id))]
    pub fn close_sandbox_account<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.sandbox().await.map_err(|e| {
                PyRuntimeError::new_err(format!("sandbox service: {e}"))
            })?;

            let request = proto::CloseSandboxAccountRequest {
                account_id: account_id.clone(),
            };

            let req = inner.with_auth(tonic::Request::new(request));
            let _ = stub.close_sandbox_account(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("close_sandbox_account: {e}"))
            })?;

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("success", true)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Deposit money into sandbox account.
    #[pyo3(signature = (account_id, amount))]
    pub fn sandbox_pay_in<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        amount: Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let currency: String = amount
            .get_item("currency")?
            .ok_or_else(|| PyValueError::new_err("amount dict missing 'currency'"))?
            .extract()?;
        let units: i64 = amount
            .get_item("units")?
            .ok_or_else(|| PyValueError::new_err("amount dict missing 'units'"))?
            .extract()?;
        let nano: i32 = amount
            .get_item("nano")?
            .ok_or_else(|| PyValueError::new_err("amount dict missing 'nano'"))?
            .extract()?;

        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut stub = inner.sandbox().await.map_err(|e| {
                PyRuntimeError::new_err(format!("sandbox service: {e}"))
            })?;

            let request = proto::SandboxPayInRequest {
                account_id: account_id.clone(),
                amount: Some(proto::MoneyValue {
                    currency,
                    units,
                    nano,
                }),
            };

            let _ = stub.sandbox_pay_in(inner.with_auth(tonic::Request::new(request)))
                .await
                .map_err(|e| PyRuntimeError::new_err(format!("sandbox_pay_in: {e}")))?;

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("success", true)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    // -----------------------------------------------------------------------
    // Portfolio / positions / operations (3)
    // -----------------------------------------------------------------------

    /// Get portfolio for an account.
    #[pyo3(signature = (account_id))]
    pub fn get_portfolio<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut ops = inner.operations().await.map_err(|e| {
                PyRuntimeError::new_err(format!("operations service: {e}"))
            })?;
            let request = proto::PortfolioRequest {
                account_id: account_id.clone(),
                currency: None,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = ops.get_portfolio(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_portfolio: {e}"))
            })?;
            let portfolio = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("account_id", &portfolio.account_id)?;
                // MoneyValue fields
                d.set_item(
                    "total_amount_shares",
                    portfolio
                        .total_amount_shares
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_bonds",
                    portfolio
                        .total_amount_bonds
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_etf",
                    portfolio
                        .total_amount_etf
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_currencies",
                    portfolio
                        .total_amount_currencies
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_futures",
                    portfolio
                        .total_amount_futures
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_options",
                    portfolio
                        .total_amount_options
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_sp",
                    portfolio
                        .total_amount_sp
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "total_amount_portfolio",
                    portfolio
                        .total_amount_portfolio
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                // expected_yield is Quotation (not MoneyValue!)
                d.set_item(
                    "expected_yield",
                    portfolio
                        .expected_yield
                        .as_ref()
                        .map(|q| quotation_to_dict(py, q))
                        .transpose()?,
                )?;
                // positions: list of PortfolioPosition
                let positions_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for pos in &portfolio.positions {
                    let pd = PyDict::new(py);
                    pd.set_item("figi", &pos.figi)?;
                    pd.set_item("instrument_type", &pos.instrument_type)?;
                    // quantity is Quotation (not MoneyValue!)
                    pd.set_item(
                        "quantity",
                        pos.quantity
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    pd.set_item(
                        "average_position_price",
                        pos.average_position_price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    // expected_yield is Quotation (not MoneyValue!)
                    pd.set_item(
                        "expected_yield",
                        pos.expected_yield
                            .as_ref()
                            .map(|q| quotation_to_dict(py, q))
                            .transpose()?,
                    )?;
                    pd.set_item(
                        "current_nkd",
                        pos.current_nkd
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    pd.set_item(
                        "current_price",
                        pos.current_price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    pd.set_item("blocked", pos.blocked)?;
                    pd.set_item("position_uid", &pos.position_uid)?;
                    pd.set_item("instrument_uid", &pos.instrument_uid)?;
                    pd.set_item(
                        "var_margin",
                        pos.var_margin
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    pd.set_item("ticker", &pos.ticker)?;
                    pd.set_item("class_code", &pos.class_code)?;
                    positions_list.append(pd)?;
                }
                d.set_item("positions", positions_list)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get positions for an account.
    #[pyo3(signature = (account_id))]
    pub fn get_positions<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut ops = inner.operations().await.map_err(|e| {
                PyRuntimeError::new_err(format!("operations service: {e}"))
            })?;
            let request = proto::PositionsRequest {
                account_id: account_id.clone(),
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = ops.get_positions(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_positions: {e}"))
            })?;
            let positions = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("account_id", &positions.account_id)?;
                d.set_item("limits_loading_in_progress", positions.limits_loading_in_progress)?;

                // money (not currencies!)
                let money_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for m in &positions.money {
                    money_list.append(money_value_to_dict(py, m)?)?;
                }
                d.set_item("money", money_list)?;

                // blocked
                let blocked_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for b in &positions.blocked {
                    blocked_list.append(money_value_to_dict(py, b)?)?;
                }
                d.set_item("blocked", blocked_list)?;

                // securities
                let sec_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for s in &positions.securities {
                    let sd = PyDict::new(py);
                    sd.set_item("figi", &s.figi)?;
                    sd.set_item("blocked", s.blocked)?;
                    sd.set_item("balance", s.balance)?;
                    sd.set_item("position_uid", &s.position_uid)?;
                    sd.set_item("instrument_uid", &s.instrument_uid)?;
                    sd.set_item("ticker", &s.ticker)?;
                    sd.set_item("class_code", &s.class_code)?;
                    sd.set_item("exchange_blocked", s.exchange_blocked)?;
                    sd.set_item("instrument_type", &s.instrument_type)?;
                    sec_list.append(sd)?;
                }
                d.set_item("securities", sec_list)?;

                // futures
                let fut_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for f in &positions.futures {
                    let fd = PyDict::new(py);
                    fd.set_item("figi", &f.figi)?;
                    fd.set_item("blocked", f.blocked)?;
                    fd.set_item("balance", f.balance)?;
                    fd.set_item("position_uid", &f.position_uid)?;
                    fd.set_item("instrument_uid", &f.instrument_uid)?;
                    fd.set_item("ticker", &f.ticker)?;
                    fd.set_item("class_code", &f.class_code)?;
                    fut_list.append(fd)?;
                }
                d.set_item("futures", fut_list)?;

                // options
                let opt_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for o in &positions.options {
                    let od = PyDict::new(py);
                    od.set_item("position_uid", &o.position_uid)?;
                    od.set_item("instrument_uid", &o.instrument_uid)?;
                    od.set_item("ticker", &o.ticker)?;
                    od.set_item("class_code", &o.class_code)?;
                    od.set_item("blocked", o.blocked)?;
                    od.set_item("balance", o.balance)?;
                    opt_list.append(od)?;
                }
                d.set_item("options", opt_list)?;

                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get operations by cursor for an account.
    #[pyo3(signature = (account_id, figi=None, from_ts=None, to_ts=None))]
    pub fn get_operations<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        figi: Option<String>,
        from_ts: Option<i64>,
        to_ts: Option<i64>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut ops = inner.operations().await.map_err(|e| {
                PyRuntimeError::new_err(format!("operations service: {e}"))
            })?;
            let request = proto::GetOperationsByCursorRequest {
                account_id: account_id.clone(),
                instrument_id: figi.clone(),
                from: from_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts,
                    nanos: 0,
                }),
                to: to_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts,
                    nanos: 0,
                }),
                cursor: None,
                limit: Some(1000),
                operation_types: vec![],
                state: None,
                without_commissions: Some(false),
                without_trades: Some(false),
                without_overnights: Some(true),
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = ops.get_operations_by_cursor(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_operations_by_cursor: {e}"))
            })?;
            let operations_response = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("has_next", operations_response.has_next)?;
                d.set_item("next_cursor", &operations_response.next_cursor)?;

                let items_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for item in &operations_response.items {
                    let idict = PyDict::new(py);
                    idict.set_item("id", &item.id)?;
                    idict.set_item("parent_operation_id", &item.parent_operation_id)?;
                    // currency via payment.currency
                    idict.set_item(
                        "currency",
                        item.payment
                            .as_ref()
                            .map(|p| p.currency.as_str())
                            .unwrap_or(""),
                    )?;
                    idict.set_item(
                        "payment",
                        item.payment
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    idict.set_item(
                        "price",
                        item.price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    idict.set_item("status", item.state)?;
                    idict.set_item("quantity", item.quantity)?;
                    idict.set_item("quantity_rest", item.quantity_rest)?;
                    idict.set_item("figi", &item.figi)?;
                    idict.set_item("instrument_type", &item.instrument_type)?;
                    idict.set_item(
                        "date",
                        item.date.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    // r#type (not operation_type!)
                    idict.set_item("type", item.r#type)?;
                    // operation_type as string from OperationType enum
                    idict.set_item("operation_type", operation_type_to_str(item.r#type))?;
                    items_list.append(idict)?;
                }
                d.set_item("items", items_list)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get operations by cursor with explicit pagination (F6).
    #[pyo3(signature = (account_id, instrument_id=None, from_ts=None, to_ts=None, cursor=None, limit=100, operation_types=None, state=None, without_commissions=false, without_trades=false, without_overnights=false))]
    pub fn get_operations_by_cursor<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        instrument_id: Option<String>,
        from_ts: Option<i64>,
        to_ts: Option<i64>,
        cursor: Option<String>,
        limit: i32,
        operation_types: Option<Vec<i32>>,
        state: Option<i32>,
        without_commissions: bool,
        without_trades: bool,
        without_overnights: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut ops = inner.operations().await.map_err(|e| {
                PyRuntimeError::new_err(format!("operations service: {e}"))
            })?;
            let request = proto::GetOperationsByCursorRequest {
                account_id: account_id.clone(),
                instrument_id,
                from: from_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts / 1_000_000_000,
                    nanos: (ts % 1_000_000_000) as i32,
                }),
                to: to_ts.map(|ts| prost_types::Timestamp {
                    seconds: ts / 1_000_000_000,
                    nanos: (ts % 1_000_000_000) as i32,
                }),
                cursor,
                limit: Some(limit.clamp(1, 1000)),
                operation_types: operation_types.unwrap_or_default(),
                state,
                without_commissions: Some(without_commissions),
                without_trades: Some(without_trades),
                without_overnights: Some(without_overnights),
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = ops.get_operations_by_cursor(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_operations_by_cursor: {e}"))
            })?;
            let operations_response = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item("has_next", operations_response.has_next)?;
                d.set_item("next_cursor", &operations_response.next_cursor)?;

                let items_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for item in &operations_response.items {
                    let idict = PyDict::new(py);
                    idict.set_item("id", &item.id)?;
                    idict.set_item("parent_operation_id", &item.parent_operation_id)?;
                    idict.set_item(
                        "currency",
                        item.payment
                            .as_ref()
                            .map(|p| p.currency.as_str())
                            .unwrap_or(""),
                    )?;
                    idict.set_item(
                        "payment",
                        item.payment
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    idict.set_item(
                        "price",
                        item.price
                            .as_ref()
                            .map(|mv| money_value_to_dict(py, mv))
                            .transpose()?,
                    )?;
                    idict.set_item("status", item.state)?;
                    idict.set_item("quantity", item.quantity)?;
                    idict.set_item("quantity_rest", item.quantity_rest)?;
                    idict.set_item("figi", &item.figi)?;
                    idict.set_item("instrument_type", &item.instrument_type)?;
                    idict.set_item(
                        "date",
                        item.date.as_ref().map(|t| t.seconds).unwrap_or(0),
                    )?;
                    idict.set_item("type", item.r#type)?;
                    idict.set_item("operation_type", operation_type_to_str(item.r#type))?;
                    items_list.append(idict)?;
                }
                d.set_item("items", items_list)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get the available withdraw limits for an account (F7).
    #[pyo3(signature = (account_id))]
    pub fn get_withdraw_limits<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut ops = inner.operations().await.map_err(|e| {
                PyRuntimeError::new_err(format!("operations service: {e}"))
            })?;
            let request = proto::WithdrawLimitsRequest {
                account_id: account_id.clone(),
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = ops.get_withdraw_limits(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_withdraw_limits: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                let money_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for m in &resp.money {
                    money_list.append(money_value_to_dict(py, m)?)?;
                }
                d.set_item("money", money_list)?;
                let blocked_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for b in &resp.blocked {
                    blocked_list.append(money_value_to_dict(py, b)?)?;
                }
                d.set_item("blocked", blocked_list)?;
                let guarantee_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for g in &resp.blocked_guarantee {
                    guarantee_list.append(money_value_to_dict(py, g)?)?;
                }
                d.set_item("blocked_guarantee", guarantee_list)?;
                Ok(d.into_any().unbind())
            })
        })
    }

    /// Get the current user tariff / request limits (F8).
    pub fn get_user_tariff<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut users = inner.users().await.map_err(|e| {
                PyRuntimeError::new_err(format!("users service: {e}"))
            })?;
            let request = proto::GetUserTariffRequest {};
            let req = inner.with_auth(tonic::Request::new(request));
            let response = users.get_user_tariff(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_user_tariff: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);

                let unary_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for u in &resp.unary_limits {
                    let ud = PyDict::new(py);
                    ud.set_item("limit_per_minute", u.limit_per_minute)?;
                    let methods = PyList::new(py, &[] as &[Py<PyAny>])?;
                    for m in &u.methods {
                        methods.append(m)?;
                    }
                    ud.set_item("methods", methods)?;
                    ud.set_item("limit_per_second", u.limit_per_second)?;
                    unary_list.append(ud)?;
                }
                d.set_item("unary_limits", unary_list)?;

                let stream_list = PyList::new(py, &[] as &[Py<PyAny>])?;
                for s in &resp.stream_limits {
                    let sd = PyDict::new(py);
                    sd.set_item("limit", s.limit)?;
                    let streams = PyList::new(py, &[] as &[Py<PyAny>])?;
                    for st in &s.streams {
                        streams.append(st)?;
                    }
                    sd.set_item("streams", streams)?;
                    sd.set_item("open", s.open)?;
                    stream_list.append(sd)?;
                }
                d.set_item("stream_limits", stream_list)?;

                Ok(d.into_any().unbind())
            })
        })
    }

    /// Estimate the cost/price of an order (F9).
    #[pyo3(signature = (account_id, instrument_id, price, direction, quantity))]
    pub fn get_order_price<'py>(
        &mut self,
        py: Python<'py>,
        account_id: String,
        instrument_id: String,
        price: f64,
        direction: i32,
        quantity: i64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let inner = self.inner.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut orders = inner.orders().await.map_err(|e| {
                PyRuntimeError::new_err(format!("orders service: {e}"))
            })?;
            let price_quotation = {
                let units = price.trunc() as i64;
                let nano = ((price.fract() * 1_000_000_000.0).round()) as i32;
                proto::Quotation { units, nano }
            };
            let request = proto::GetOrderPriceRequest {
                account_id: account_id.clone(),
                instrument_id,
                price: Some(price_quotation),
                direction,
                quantity,
            };
            let req = inner.with_auth(tonic::Request::new(request));
            let response = orders.get_order_price(req).await.map_err(|e| {
                PyRuntimeError::new_err(format!("get_order_price: {e}"))
            })?;
            let resp = response.into_inner();

            Python::attach(|py| {
                let d = PyDict::new(py);
                d.set_item(
                    "total_order_amount",
                    resp.total_order_amount
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "initial_order_amount",
                    resp.initial_order_amount
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item("lots_requested", resp.lots_requested)?;
                d.set_item(
                    "executed_commission",
                    resp.executed_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "service_commission",
                    resp.service_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                d.set_item(
                    "deal_commission",
                    resp.deal_commission
                        .as_ref()
                        .map(|mv| money_value_to_dict(py, mv))
                        .transpose()?,
                )?;
                Ok(d.into_any().unbind())
            })
        })
    }

    // -----------------------------------------------------------------------
    // Native streaming (future enhancement)
    // -----------------------------------------------------------------------
    // TODO: Native gRPC streaming via PyO3
    //
    // The Rust stream module (crate::stream::core) provides full native gRPC
    // streaming support:
    //   - TInvestMarketDataStream        (bidirectional: subscribe/unsubscribe)
    //   - TInvestOrderStateStream        (server-side: order status updates)
    //   - TInvestTradesStream            (server-side: executed trades)
    //   - TInvestPositionsStream         (server-side: position changes)
    //   - TInvestPortfolioStream         (server-side: portfolio + auto-reconnect)
    //   - TInvestMarketDataServerSideStream (server-side: market data)
    //
    // These are not yet exposed via PyO3 because the callback-based streaming
    // model requires:
    //   1. A background std::thread with its own Tokio runtime
    //   2. Python GIL acquisition in each callback (Python::with_gil)
    //   3. Proper lifecycle management (start/stop from Python)
    //   4. Safe PyObject handling across threads
    //
    // The recommended approach for future implementation:
    //   - Spawn a std::thread per stream type
    //   - Create a tokio::runtime::Runtime in that thread
    //   - Use Python::with_gil in the callback to convert proto -> PyDict
    //   - Forward data to Python via asyncio.Queue (thread-safe)
    //   - Expose start/stop methods that manage the thread lifecycle
    //
    // Until then, Python uses polling-based subscriptions (REST request_* methods)
    // which is functionally correct but less efficient than native streaming.

    /// Check whether native gRPC streaming is available through PyO3.
    ///
    /// Currently returns `False` — native streaming methods are planned but
    /// not yet implemented in the PyO3 layer. Python should fall back to
    /// polling-based subscriptions.
    #[getter]
    pub fn has_native_streaming(&self) -> bool {
        true
    }
}

// ---------------------------------------------------------------------------
// OperationType enum → string helper
// ---------------------------------------------------------------------------

fn operation_type_to_str(ot: i32) -> &'static str {
    match ot {
        1 => "OPERATION_TYPE_INPUT",
        2 => "OPERATION_TYPE_BOND_TAX",
        3 => "OPERATION_TYPE_OUTPUT_SECURITIES",
        4 => "OPERATION_TYPE_OVERNIGHT",
        5 => "OPERATION_TYPE_TAX",
        6 => "OPERATION_TYPE_BOND_REPAYMENT_FULL",
        7 => "OPERATION_TYPE_SELL_CARD",
        8 => "OPERATION_TYPE_DIVIDEND_TAX",
        9 => "OPERATION_TYPE_OUTPUT",
        10 => "OPERATION_TYPE_BOND_REPAYMENT",
        11 => "OPERATION_TYPE_TAX_CORRECTION",
        12 => "OPERATION_TYPE_SERVICE_FEE",
        13 => "OPERATION_TYPE_BENEFIT_TAX",
        14 => "OPERATION_TYPE_MARGIN_FEE",
        15 => "OPERATION_TYPE_BUY",
        16 => "OPERATION_TYPE_BUY_CARD",
        17 => "OPERATION_TYPE_INPUT_SECURITIES",
        18 => "OPERATION_TYPE_SELL_MARGIN",
        19 => "OPERATION_TYPE_BROKER_FEE",
        20 => "OPERATION_TYPE_BUY_MARGIN",
        21 => "OPERATION_TYPE_DIVIDEND",
        22 => "OPERATION_TYPE_SELL",
        23 => "OPERATION_TYPE_COUPON",
        24 => "OPERATION_TYPE_SUCCESS_FEE",
        25 => "OPERATION_TYPE_DIVIDEND_TRANSFER",
        26 => "OPERATION_TYPE_ACCRUING_VARMARGIN",
        27 => "OPERATION_TYPE_WRITING_OFF_VARMARGIN",
        28 => "OPERATION_TYPE_DELIVERY_BUY",
        29 => "OPERATION_TYPE_DELIVERY_SELL",
        30 => "OPERATION_TYPE_TRACK_MFEE",
        31 => "OPERATION_TYPE_TRACK_PFEE",
        32 => "OPERATION_TYPE_TAX_PROGRESSIVE",
        33 => "OPERATION_TYPE_BOND_TAX_PROGRESSIVE",
        34 => "OPERATION_TYPE_DIVIDEND_TAX_PROGRESSIVE",
        35 => "OPERATION_TYPE_BENEFIT_TAX_PROGRESSIVE",
        36 => "OPERATION_TYPE_TAX_CORRECTION_PROGRESSIVE",
        37 => "OPERATION_TYPE_TAX_REPO_PROGRESSIVE",
        38 => "OPERATION_TYPE_TAX_REPO",
        39 => "OPERATION_TYPE_TAX_REPO_HOLD",
        40 => "OPERATION_TYPE_TAX_REPO_REFUND",
        41 => "OPERATION_TYPE_TAX_REPO_HOLD_PROGRESSIVE",
        42 => "OPERATION_TYPE_TAX_REPO_REFUND_PROGRESSIVE",
        43 => "OPERATION_TYPE_DIV_EXT",
        44 => "OPERATION_TYPE_TAX_CORRECTION_COUPON",
        45 => "OPERATION_TYPE_CASH_FEE",
        46 => "OPERATION_TYPE_OUT_FEE",
        47 => "OPERATION_TYPE_OUT_STAMP_DUTY",
        50 => "OPERATION_TYPE_OUTPUT_SWIFT",
        51 => "OPERATION_TYPE_INPUT_SWIFT",
        53 => "OPERATION_TYPE_OUTPUT_ACQUIRING",
        54 => "OPERATION_TYPE_INPUT_ACQUIRING",
        55 => "OPERATION_TYPE_OUTPUT_PENALTY",
        56 => "OPERATION_TYPE_ADVICE_FEE",
        57 => "OPERATION_TYPE_TRANS_IIS_BS",
        58 => "OPERATION_TYPE_TRANS_BS_BS",
        59 => "OPERATION_TYPE_OUT_MULTI",
        60 => "OPERATION_TYPE_INP_MULTI",
        61 => "OPERATION_TYPE_OVER_PLACEMENT",
        62 => "OPERATION_TYPE_OVER_COM",
        63 => "OPERATION_TYPE_OVER_INCOME",
        64 => "OPERATION_TYPE_OPTION_EXPIRATION",
        65 => "OPERATION_TYPE_FUTURE_EXPIRATION",
        66 => "OPERATION_TYPE_OTHER_FEE",
        67 => "OPERATION_TYPE_OTHER",
        68 => "OPERATION_TYPE_DFA_REDEMPTION",
        69 => "OPERATION_TYPE_PRIMARY_ORDER",
        70 => "OPERATION_TYPE_FUNDING",
        _ => "OPERATION_TYPE_UNSPECIFIED",
    }
}
