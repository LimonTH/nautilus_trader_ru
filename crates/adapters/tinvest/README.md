# nautilus-tinvest

[![build](https://github.com/nautechsystems/nautilus_trader/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/nautechsystems/nautilus_trader/actions/workflows/build.yml)
[![Documentation](https://img.shields.io/docsrs/nautilus-tinvest)](https://docs.rs/nautilus-tinvest/latest/nautilus-tinvest/)
[![crates.io version](https://img.shields.io/crates/v/nautilus-tinvest.svg)](https://crates.io/crates/nautilus-tinvest)
![license](https://img.shields.io/github/license/nautechsystems/nautilus_trader?color=blue)
[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?logo=discord&logoColor=white)](https://discord.gg/NautilusTrader)

[NautilusTrader](https://nautilustrader.io) adapter for the [T-Invest API](https://developer.tbank.ru/invest/intro/intro) (MOEX).

The `nautilus-tinvest` crate provides Rust client bindings (gRPC), data models, and conversion
utilities that wrap the official **T-Invest API** (Т-Инвестиции, formerly Tinkoff Invest).

## NautilusTrader

[NautilusTrader](https://nautilustrader.io) is an open-source, production-grade, Rust-native
engine for multi-asset, multi-venue trading systems.

The system spans research, deterministic simulation, and live execution within a single
event-driven architecture, providing research-to-live semantic parity.

## Feature flags

This crate provides feature flags to control source code inclusion during compilation:

- `python`: Enables Python bindings from [PyO3](https://pyo3.rs).
- `extension-module`: Builds as a Python extension module.

[High-precision mode](https://nautilustrader.io/docs/nightly/getting_started/installation#precision-mode) (128-bit value types) is enabled by default.

## Requirements

- A T-Invest API token (production or sandbox). See the [T-Invest developer portal](https://developer.tbank.ru).
- TLS access to `invest-public-api.tbank.ru:443` (production) or `sandbox-invest-public-api.tbank.ru:443` (sandbox).
  A Russian Trusted Root CA bundle is bundled for environments that require it.

## Documentation

See [the docs](https://docs.rs/nautilus-tinvest) and the [integration guide](https://nautilustrader.io/docs/latest/integrations/tinvest/) for more detailed usage.

## License

The source code for NautilusTrader is available on GitHub under the [GNU Lesser General Public License v3.0](https://www.gnu.org/licenses/lgpl-3.0.en.html).

---
