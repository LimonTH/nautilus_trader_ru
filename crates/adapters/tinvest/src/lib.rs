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

//! [NautilusTrader](https://nautilustrader.io) adapter for
//! [T-Invest API](https://developer.tbank.ru/invest/intro/intro) (MOEX).
//!
//! The `nautilus-tinvest` crate wraps the T-Invest gRPC API and connects it to
//! NautilusTrader's live data, execution, and instrument loading infrastructure.
//!
//! # NautilusTrader
//!
//! [NautilusTrader](https://nautilustrader.io) is an open-source, production-grade, Rust-native
//! engine for multi-asset, multi-venue trading systems.
//!
//! The system spans research, deterministic simulation, and live execution within a single
//! event-driven architecture, providing research-to-live semantic parity.
//!
//! # Feature flags
//!
//! This crate provides feature flags to control source code inclusion during compilation,
//! depending on the intended use case (Rust-only builds vs. Python bindings through PyO3).
//!
//! - `python`: Enables PyO3 bindings for configs, enums, and factories.
//! - `extension-module`: Builds as a Python extension module (used together with `python`).

#![warn(rustc::all)]
#![deny(unsafe_code)]
#![allow(
    clippy::collapsible_if,
    clippy::if_not_else,
    clippy::uninlined_format_args,
    clippy::map_unwrap_or,
    clippy::redundant_clone,
    clippy::ignored_unit_patterns,
    clippy::items_after_statements,
    clippy::bool_to_int_with_if,
    clippy::cloned_instead_of_copied,
    clippy::option_if_let_else,
    clippy::type_complexity,
    clippy::await_holding_lock,
    clippy::module_inception,
    clippy::result_large_err,
    clippy::implicit_clone,
    clippy::single_char_pattern,
    clippy::bind_instead_of_map,
    clippy::explicit_iter_loop,
    clippy::too_many_arguments,
    clippy::missing_errors_doc,
    clippy::doc_overindented_list_items,
    clippy::needless_borrows_for_generic_args
)]
#![deny(nonstandard_style)]
#![deny(missing_debug_implementations)]
#![deny(clippy::missing_panics_doc)]
#![deny(rustdoc::broken_intra_doc_links)]

/// Generated T-Invest API proto types and service stubs.
pub mod proto {
    #![allow(unused_imports, clippy::all, clippy::pedantic, clippy::nursery)]
    tonic::include_proto!("tinkoff.public.invest.api.contract.v1");
}

pub mod common;
pub mod config;
pub mod client;
pub mod enums;
pub mod data;
pub mod execution;
pub mod factories;
pub mod providers;
pub mod sandbox;
pub mod stream;

#[cfg(feature = "python")]
pub mod python;