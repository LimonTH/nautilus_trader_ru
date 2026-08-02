# T-Invest (MOEX)

[T-Invest](https://developer.tbank.ru/invest/intro/intro) (formerly Tinkoff Invest) is a brokerage API
provided by T-Bank (formerly Tinkoff) for trading on the Moscow Exchange (MOEX). It offers access to
Russian equities, bonds, ETFs, futures, options, and currencies through a gRPC API.

NautilusTrader provides a Rust-native adapter for the T-Invest API with Python bindings via PyO3.
The adapter supports live market data ingest and order execution on the Moscow Exchange.

## Overview

This adapter is implemented in Rust under `crates/adapters/tinvest` with Python bindings for use in
Python-based workflows. It uses gRPC (via [tonic](https://github.com/hyperium/tonic)) to communicate
with the T-Invest API and does not require external T-Invest client libraries.

The Python layer lives in [`nautilus_trader/adapters/tinvest`](nautilus_trader/adapters/tinvest/__init__.py)
and exposes the following public API (see [`__init__.py`](nautilus_trader/adapters/tinvest/__init__.py:16)):

- `TInvestGrpcClient`: Low-level gRPC API connectivity with authentication, retry logic, and
  connection pooling. Implemented as a Python wrapper over the PyO3 Rust client.
- `TInvestDataClient`: Market data client implementing the Nautilus `DataClient` interface
  (subscriptions, historical data requests).
- `TInvestExecutionClient`: Account management and trade execution client implementing the Nautilus
  `ExecutionClient` interface.
- `TInvestInstrumentProvider`: Instrument loading and conversion from T-Invest types to Nautilus
  instruments.
- `TInvestMarketDataStream`: Bidirectional gRPC stream for real-time market data (trades, order books,
  candles, info). Exposed via PyO3.
- `TInvestOrderStateStream`: Server-side gRPC stream for real-time order state updates. Exposed via PyO3.
- `TInvestPortfolioStream`: Server-side gRPC stream for real-time portfolio updates. Exposed via PyO3.
- `TInvestPositionsStream`: Server-side gRPC stream for real-time position updates. Exposed via PyO3.
- `TInvestLiveDataClientFactory`: Factory for T-Invest data clients (used by the trading node builder).
- `TInvestLiveExecClientFactory`: Factory for T-Invest execution clients (used by the trading node builder).

:::note
The stream classes (`TInvestMarketDataStream`, `TInvestOrderStateStream`, `TInvestPortfolioStream`,
`TInvestPositionsStream`) are PyO3 bindings over the Rust implementation and are only importable when
the `nautilus_pyo3` extension module is built. When it is unavailable, the adapter transparently falls
back to REST polling for subscriptions (see [Streaming](#streaming)).
:::

:::note
Most users will define a configuration for a live trading node (as below),
and won't need to work with these lower-level components directly.
:::

## T-Invest documentation

T-Invest provides extensive documentation for developers:

- [T-Invest API Introduction](https://developer.tbank.ru/invest/intro/intro): Main entry point for API access.
- [T-Invest gRPC API Reference](https://developer.tbank.ru/invest/api/): Complete gRPC API reference.
- [T-Invest Sandbox](https://developer.tbank.ru/invest/intro/developer/sandbox/): Sandbox environment documentation.

It's recommended you also refer to the T-Invest documentation in conjunction with this
NautilusTrader integration guide.

## Products

The T-Invest API provides access to the following instrument types on the Moscow Exchange (MOEX):

| Product Type | Supported | Notes                                    |
|--------------|-----------|------------------------------------------|
| Shares       | ✓         | Russian equities and DRs.                |
| Bonds        | ✓         | OFZ, corporate, and municipal bonds.     |
| ETFs         | ✓         | Exchange-traded funds listed on MOEX.    |
| Futures      | ✓         | Derivative futures contracts.            |
| Options      | ✓         | Derivative option contracts.             |
| Currencies   | ✓         | Currency pairs (USD/RUB, EUR/RUB, etc.). |

## Symbology

T-Invest instruments use the FIGI (Financial Instrument Global Identifier) as the primary symbol
identifier. The venue identifier is `TINVEST`.

### Instrument ID format

Format: `{FIGI}.TINVEST`

Examples:

- `BBG004730N88.TINVEST` - Sberbank share (SBER)
- `BBG004731032.TINVEST` - Gazprom share (GAZP)
- `BBG00DPM5VH1.TINVEST` - MOEX Index futures (MIX)
- `BBG00QPYJ5H0.TINVEST` - USD/RUB futures (Si)

To subscribe in your strategy:

```python
from nautilus_trader.model.identifiers import InstrumentId

instrument_id = InstrumentId.from_str("BBG004730N88.TINVEST")
```

### Instrument types

The adapter converts T-Invest instrument types to Nautilus instrument classes:

| T-Invest Type | Nautilus Instrument | Notes                                                  |
|---------------|---------------------|--------------------------------------------------------|
| `share`       | `Equity`            | Common and preferred shares.                           |
| `bond`        | `Equity`            | Represented as Equity (no BondInstrument in Nautilus). |
| `etf`         | `Equity`            | Exchange-traded funds.                                 |
| `future`      | `FuturesContract`   | Derivative futures.                                    |
| `option`      | `OptionContract`    | Derivative options with strike, expiry, and kind.      |
| `currency`    | `Equity`            | Currency instruments (not traded directly).            |

The T-Invest → Nautilus `AssetClass` mapping is defined in
[`constants.py`](nautilus_trader/adapters/tinvest/constants.py:100).

## Environments

T-Invest provides two trading environments. Configure the appropriate environment using the
`sandbox` flag in your client configuration.

| Environment    | Config          | gRPC Endpoint                            |
|----------------|-----------------|------------------------------------------|
| **Production** | `sandbox=False` | `invest-public-api.tbank.ru:443`         |
| **Sandbox**    | `sandbox=True`  | `sandbox-invest-public-api.tbank.ru:443` |

The endpoint is resolved automatically by [`TInvestClientConfig.effective_target()`](nautilus_trader/adapters/tinvest/config.py:57)
when the `target` option is not set explicitly.

### Production

The default environment for live trading with real funds.

```python
from nautilus_trader.adapters.tinvest.config import TInvestClientConfig

config = TInvestClientConfig(
    token="YOUR_API_TOKEN",
    sandbox=False,
)
```

Environment variable: `TINVEST_API_TOKEN`

### Sandbox

A test environment with simulated funds for development and testing.

```python
from nautilus_trader.adapters.tinvest.config import TInvestClientConfig

config = TInvestClientConfig(
    token="YOUR_SANDBOX_TOKEN",
    sandbox=True,
)
```

Environment variable: `TINVEST_SANDBOX_TOKEN`

#### Sandbox setup

1. Register a T-Invest developer account at [developer.tbank.ru](https://developer.tbank.ru).
2. Generate a sandbox API token in the developer dashboard.
3. Set the token as an environment variable:

   ```bash
   export TINVEST_SANDBOX_TOKEN="your_sandbox_token"
   ```

4. The sandbox account starts with zero balance. Use `SandboxPayIn` to deposit funds. The
   `TInvestGrpcClient` exposes this operation via
   [`sandbox_pay_in()`](nautilus_trader/adapters/tinvest/grpc_client.py:1397):

   ```python
   # Deposit 100,000 RUB into the sandbox account
   await client.sandbox_pay_in("RUB", 100000.0)
   ```

   Additional sandbox helpers are available on `TInvestGrpcClient`, including
   [`open_sandbox_account()`](nautilus_trader/adapters/tinvest/grpc_client.py:1359),
   [`close_sandbox_account()`](nautilus_trader/adapters/tinvest/grpc_client.py:1378) and
   [`get_sandbox_accounts()`](nautilus_trader/adapters/tinvest/grpc_client.py:1428).

:::note
There is no separate `TInvestSandboxExecutionClient` in the Python layer. Sandbox trading is enabled
by setting `sandbox=True` in the `TInvestClientConfig`; the same `TInvestExecutionClient` then routes
operations to the T-Invest sandbox services.
:::

## Authentication

T-Invest uses bearer token authentication. The API token is passed as an `Authorization: Bearer`
header on every gRPC request.

### Creating an API token

1. Log into the [T-Invest Developer Portal](https://developer.tbank.ru).
2. Navigate to **API Keys**.
3. Create a new API key with the required permissions.
4. Copy the token value.

### Environment variables

| Variable                | Description                       |
|-------------------------|-----------------------------------|
| `TINVEST_API_TOKEN`     | API token for production trading. |
| `TINVEST_SANDBOX_TOKEN` | API token for sandbox testing.    |

:::tip
We recommend using environment variables to manage your credentials.
:::

### SSL/TLS configuration

The T-Invest API requires TLS. The adapter uses the system's default root CA certificates by default.
For environments that require the Russian Trusted Root CA (e.g., when connecting from within Russia),
set the `ca_cert_path` configuration option to a PEM file containing the Russian root certificate:

```python
config = TInvestClientConfig(
    token="YOUR_API_TOKEN",
    ca_cert_path="/path/to/RussianTrustedRootCA.pem",
)
```

A Russian Trusted Root CA certificate is included in the adapter at
`crates/adapters/tinvest/certs/RussianTrustedRootCA.pem`.

## gRPC client

The `TInvestGrpcClient` manages connections to all T-Invest gRPC services. It is a Python wrapper
over the native Rust client (`PyTInvestGrpcClient` via PyO3), with automatic fallback to REST-style
requests when the native extension is unavailable.

| Service                   | Client Method          | Purpose                                               |
|---------------------------|------------------------|-------------------------------------------------------|
| `InstrumentsService`      | `request_instruments`  | Instrument metadata (shares, bonds, futures, etc.).   |
| `MarketDataService`       | `request_candles` etc. | Historical and snapshot market data.                  |
| `MarketDataStreamService` | `subscribe_*`          | Real-time market data streaming (or polling fallback).|
| `OperationsService`       | `get_portfolio` etc.   | Account portfolio, positions, and operations history. |
| `OperationsStreamService` | native streams         | Real-time portfolio and position updates.             |
| `OrdersService`           | `post_order` etc.      | Order placement, modification, and cancellation.      |
| `OrdersStreamService`     | `TInvestOrderStateStream` | Real-time order state updates.                     |
| `StopOrdersService`       | `post_stop_order` etc. | Stop-order management.                                |
| `UsersService`            | `get_accounts`         | Account information.                                  |
| `SandboxService`          | `sandbox_pay_in` etc.  | Sandbox operations (pay-in, orders, portfolio).       |

### Connection management

The client supports:

- **TLS encryption**: Required for all connections.
- **Custom CA certificates**: For Russian Trusted Root CA support.
- **Keepalive**: HTTP/2 keepalive pings to maintain long-lived connections.
- **Retry with exponential backoff**: Configurable retry for failed requests.
- **Connection pooling**: Shared channel across all service stubs (a single shared `TInvestGrpcClient`
  is reused by both the data and execution clients — see
  [`get_shared_grpc_client()`](nautilus_trader/adapters/tinvest/factories.py:42)).

### Retry policy

The client implements exponential backoff for failed requests:

- `max_retries`: Maximum retry attempts (default: 3).
- `retry_wait_ms`: Initial wait duration (default: 1,000 ms).
- Backoff doubles on each retry: `wait_ms * 2^attempt`.

## Data capability

### Subscriptions (real-time)

The adapter supports real-time market data via native bidirectional gRPC streaming (`TInvestMarketDataStream`).
When native streaming is unavailable (PyO3 not built), subscriptions fall back to REST polling inside
[`grpc_client.py`](nautilus_trader/adapters/tinvest/grpc_client.py).

| Data type          | Subscribe method         | Notes                               |
|--------------------|--------------------------|-------------------------------------|
| `TradeTick`        | `_subscribe_trade_ticks` | Real-time trade ticks.              |
| `QuoteTick`        | `_subscribe_quote_ticks` | Best bid/ask from order book depth. |
| `OrderBookDepth10` | `_subscribe_order_book_snapshot` | Top 10 levels of market depth. |
| `Bar`              | `_subscribe_bars`        | OHLCV candles (1min to 1month).     |
| `Instrument`       | `_request_instruments`   | Instruments are loaded on demand (no streaming). |

### Historical data

The `TInvestDataClient` implements historical (request/response) data through the following methods
in [`data.py`](nautilus_trader/adapters/tinvest/data.py:916):

| Request type          | Handler                                  | Behavior                                                            |
|-----------------------|------------------------------------------|---------------------------------------------------------------------|
| `RequestBars`         | [`_request_bars()`](nautilus_trader/adapters/tinvest/data.py:1016) | Maps the `BarType` spec to a T-Invest candle interval, calls `request_candles()` and emits `Bar` objects. Defaults: 30-day lookback, `limit=100`. |
| `RequestOrderBookSnapshot` | [`_request_order_book_snapshot()`](nautilus_trader/adapters/tinvest/data.py:998) | Calls `request_order_book(figi, depth)` (default `depth=10`) and processes the snapshot via `_on_order_book`. |
| `RequestTradeTicks`    | [`_request_trade_ticks()`](nautilus_trader/adapters/tinvest/data.py:976) | Calls `request_trades(figi, from_ts, to_ts)` with the request time range and emits `TradeTick` objects via `_on_trade_tick`. |
| `RequestQuoteTicks`    | [`_request_quote_ticks()`](nautilus_trader/adapters/tinvest/data.py:928) | Fetches the current order book and synthesizes a `QuoteTick` from the best bid/ask. |
| `RequestInstruments`   | [`_request_instruments()`](nautilus_trader/adapters/tinvest/data.py:917) | Loads all instruments via the instrument provider and caches them. |

The underlying gRPC requests are implemented on `TInvestGrpcClient`:

| Data type    | Method                                | Notes                        |
|--------------|---------------------------------------|------------------------------|
| `QuoteTick`  | [`request_order_book()`](nautilus_trader/adapters/tinvest/grpc_client.py:220) | Current order book snapshot. |
| `TradeTick`  | [`request_trades()`](nautilus_trader/adapters/tinvest/grpc_client.py:241) | Recent trade history.        |
| `Bar`        | [`request_candles()`](nautilus_trader/adapters/tinvest/grpc_client.py:180) | Historical OHLCV candles.    |
| `Instrument` | [`request_instruments()`](nautilus_trader/adapters/tinvest/grpc_client.py:142) | All instrument definitions.  |
| `Instrument` | [`request_instrument()`](nautilus_trader/adapters/tinvest/grpc_client.py:157) | Single instrument by FIGI.   |

### Supported bar intervals

The T-Invest candle interval mapping is defined in
[`constants.py`](nautilus_trader/adapters/tinvest/constants.py:35). Candles are requested with the
`LAST` price type, so the resulting `BarSpec` strings carry the `-LAST` suffix.

| Interval   | T-Invest CandleInterval | BarSpec          |
|------------|-------------------------|------------------|
| 1 minute   | 1                       | `1-MINUTE-LAST`  |
| 2 minutes  | 6                       | `2-MINUTE-LAST`  |
| 3 minutes  | 7                       | `3-MINUTE-LAST`  |
| 5 minutes  | 2                       | `5-MINUTE-LAST`  |
| 10 minutes | 8                       | `10-MINUTE-LAST` |
| 15 minutes | 3                       | `15-MINUTE-LAST` |
| 30 minutes | 9                       | `30-MINUTE-LAST` |
| 1 hour     | 4                       | `1-HOUR-LAST`    |
| 2 hours    | 10                      | `2-HOUR-LAST`    |
| 4 hours    | 11                      | `4-HOUR-LAST`    |
| 1 day      | 5                       | `1-DAY-LAST`     |
| 1 week     | 12                      | `1-WEEK-LAST`    |
| 1 month    | 13                      | `1-MONTH-LAST`   |

## Orders capability

### Order types

| Order Type          | Supported | Notes                                          |
|---------------------|-----------|------------------------------------------------|
| `MARKET`            | ✓         | Immediate execution at market price.           |
| `LIMIT`             | ✓         | Execution at specified price or better.        |
| `STOP_MARKET`       | ✓         | Routed to the stop-order API (`PostStopOrder`).|
| `STOP_LIMIT`        | ✓         | Routed to the stop-order API (`PostStopOrder`).|
| `MARKET_IF_TOUCHED` | ✓         | Routed to the stop-order API (`PostStopOrder`).|
| `LIMIT_IF_TOUCHED`  | ✓         | Routed to the stop-order API (`PostStopOrder`).|

The set of Nautilus order types routed to `PostStopOrder` is defined in
[`constants.py`](nautilus_trader/adapters/tinvest/constants.py:87).

### Execution instructions

| Instruction   | Supported | Notes                            |
|---------------|-----------|----------------------------------|
| `post_only`   | -         | *Not supported by T-Invest API.* |
| `reduce_only` | -         | *Not supported by T-Invest API.* |

### Time in force

| Time in force | Supported | Notes                         |
|---------------|-----------|-------------------------------|
| `GTC`         | ✓         | Good Till Canceled (default). |
| `DAY`         | -         | *Not supported.*              |
| `IOC`         | -         | *Not supported.*              |
| `FOK`         | -         | *Not supported.*              |
| `GTD`         | -         | *Not supported.*              |

### Stop orders

The adapter provides access to T-Invest's stop-order API through `TInvestGrpcClient`
([`post_stop_order()`](nautilus_trader/adapters/tinvest/grpc_client.py:1171)):

| Stop Order Type | T-Invest Type | Notes               |
|-----------------|---------------|---------------------|
| Take Profit     | 1             | `stop_order_type=1` |
| Stop Loss       | 2             | `stop_order_type=2` |
| Stop Limit      | 3             | `stop_order_type=3` |

Stop orders support expiration types:

| Expiration Type  | T-Invest Value | Notes               |
|------------------|----------------|---------------------|
| Good Till Cancel | 1              | `expiration_type=1` |
| Good Till Date   | 2              | `expiration_type=2` |

### Order operations

| Operation         | Supported | Notes                                     |
|-------------------|-----------|-------------------------------------------|
| Submit order      | ✓         | Single order submission via `_submit_order`. |
| Modify order      | ✓         | Order modification via `_modify_order`.   |
| Cancel order      | ✓         | Single order cancellation via `_cancel_order`. |
| Cancel all orders | ✓         | Implemented in `_cancel_all_orders`.      |
| Batch submit      | ✓         | Implemented in `_submit_order_list`.      |
| Batch cancel      | -         | *Not implemented.*                        |

### Position management

| Feature          | Supported | Notes                                |
|------------------|-----------|--------------------------------------|
| Query positions  | ✓         | Securities, futures, and currencies. |
| Query portfolio  | ✓         | Total portfolio value and positions. |
| Position mode    | -         | Netting only.                        |
| Leverage control | -         | *Not supported.*                     |
| Margin mode      | -         | *Not supported.*                     |

### Order querying

| Feature              | Supported | Notes                             |
|----------------------|-----------|-----------------------------------|
| Query open orders    | ✓         | List all active orders.           |
| Query order state    | ✓         | Single order state by ID.         |
| Order status updates | ✓         | Real-time via `TInvestOrderStateStream`. |
| Trade history        | ✓         | Via `get_operations_by_cursor`.   |
| Fill reports         | ✓         | Via `generate_fill_reports`.      |

## Streaming

The adapter provides real-time streaming via gRPC server-side and bidirectional streams. The stream
classes are PyO3 bindings over the Rust implementation and are exposed through the adapter's
[`__init__.py`](nautilus_trader/adapters/tinvest/__init__.py:26).

### Market data stream (bidirectional)

The `TInvestMarketDataStream` manages a bidirectional gRPC stream for real-time market data:

- Subscribe/unsubscribe to trade ticks.
- Subscribe/unsubscribe to order book (depth) updates.
- Subscribe/unsubscribe to instrument info (trading status).
- Subscribe/unsubscribe to candle updates.

### Order state stream (server-side)

The `TInvestOrderStateStream` provides real-time order state updates for an account:

- Order submission confirmations.
- Order fill updates.
- Order cancellation events.
- Order rejection events.

Trade (fill) notifications are delivered within this stream.

### Portfolio stream (server-side)

The `TInvestPortfolioStream` provides real-time portfolio updates:

- Position changes.
- Portfolio value updates.
- Balance changes.

### Positions stream (server-side)

The `TInvestPositionsStream` provides real-time position updates:

- Securities positions.
- Futures positions.
- Options positions.

:::note
When the PyO3 native stream classes are unavailable, execution state is reconciled via explicit
report generation (`generate_order_status_reports`, `generate_fill_reports`,
`generate_position_status_reports`) and polling.
:::

## Rate limiting

T-Invest applies rate limits to API requests. The adapter implements retry with exponential backoff
to handle rate limit responses gracefully.

| Limit Type          | Default       | Notes                                     |
|---------------------|---------------|-------------------------------------------|
| Requests per second | Not published | T-Invest may throttle excessive requests. |
| Concurrent streams  | Not published | Manage stream connections carefully.      |

The adapter's retry mechanism helps mitigate transient rate limit errors:

- `max_retries`: 3 (configurable).
- `retry_wait_ms`: 1,000 ms initial (configurable).
- Backoff: doubles on each retry.

## Configuration

### Client configuration options

The `TInvestClientConfig` provides the following configuration options:

| Option                  | Default                          | Description                                          |
|-------------------------|----------------------------------|------------------------------------------------------|
| `token`                 | Required                         | T-Invest API token.                                  |
| `target`                | *auto-resolved*                  | gRPC endpoint (host:port). Defaults to the production or sandbox endpoint based on `sandbox`. |
| `sandbox`               | `False`                          | Use sandbox environment when `true`.                 |
| `connection_timeout_ms` | `5,000`                          | Connection timeout in milliseconds.                  |
| `keepalive_ms`          | `10,000`                         | HTTP/2 keepalive interval in milliseconds.           |
| `max_message_size`      | `67,108,864`                     | Maximum gRPC message size in bytes (64 MB).          |
| `max_retries`           | `3`                              | Maximum retry attempts for failed requests.          |
| `retry_wait_ms`         | `1,000`                          | Initial retry wait duration in milliseconds.         |
| `ca_cert_path`          | `None`                           | Path to custom CA certificate bundle (PEM format).   |

`TInvestClientConfig` also provides the [`effective_target()`](nautilus_trader/adapters/tinvest/config.py:57)
method and a [`to_pyo3()`](nautilus_trader/adapters/tinvest/config.py:64) converter used to build the
native Rust configuration.

### Data client configuration options

The `TInvestDataClientConfig` provides the following configuration options:

| Option                             | Default  | Description                                     |
|------------------------------------|----------|-------------------------------------------------|
| `tinvest`                          | Required | `TInvestClientConfig` for gRPC connection.      |
| `instrument_provider`              | `None`   | `InstrumentProviderConfig` for the provider.    |
| `update_instruments_interval_mins` | `None`   | Interval in minutes between instrument updates. |

### Execution client configuration options

The `TInvestExecClientConfig` provides the following configuration options:

| Option                 | Default  | Description                                                             |
|------------------------|----------|-------------------------------------------------------------------------|
| `tinvest`              | Required | `TInvestClientConfig` for gRPC connection.                              |
| `account_id`           | `None`   | Account ID for trading (auto-resolved when not set).                    |
| `instrument_provider`  | `None`   | `InstrumentProviderConfig` for the provider.                            |
| `use_bestprice_orders` | `False`  | Submit Nautilus `MARKET` orders as T-Invest `ORDER_TYPE_BESTPRICE`.     |
| `use_async_orders`     | `False`  | Submit orders via `PostOrderAsync` (fire-and-forget).                   |

### Instrument provider configuration options

The `TInvestInstrumentProviderConfig` provides the following configuration options:

| Option     | Default  | Description                                      |
|------------|----------|--------------------------------------------------|
| `load_all` | `True`   | Load all available instruments from T-Invest API.|

### Configuration example

Below is an example configuration for a live trading node using T-Invest data and execution clients:

```python
from nautilus_trader.adapters.tinvest import TINVEST
from nautilus_trader.adapters.tinvest import TInvestClientConfig
from nautilus_trader.adapters.tinvest import TInvestDataClientConfig
from nautilus_trader.adapters.tinvest import TInvestExecClientConfig
from nautilus_trader.adapters.tinvest import TInvestLiveDataClientFactory
from nautilus_trader.adapters.tinvest import TInvestLiveExecClientFactory
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode

# T-Invest gRPC client configuration
tinvest_config = TInvestClientConfig(
    token="YOUR_API_TOKEN",  # Or use TINVEST_API_TOKEN env var
    sandbox=False,  # Set to True for sandbox testing
)

# Data client configuration
data_config = TInvestDataClientConfig(
    tinvest=tinvest_config,
    update_instruments_interval_mins=60,
)

# Execution client configuration
exec_config = TInvestExecClientConfig(
    tinvest=tinvest_config,
    account_id="TINVEST-0000000000",  # Will be auto-resolved if not set
)

# Trading node configuration
config = TradingNodeConfig(
    trader_id="TRADER-001",
    data_clients={
        TINVEST: data_config,
    },
    exec_clients={
        TINVEST: exec_config,
    },
)

# Create and build the trading node
node = TradingNode(config=config)
node.add_data_client_factory(TINVEST, TInvestLiveDataClientFactory)
node.add_exec_client_factory(TINVEST, TInvestLiveExecClientFactory)
node.build()
```

### API credentials

There are two options for supplying your credentials to the T-Invest clients.
Either pass the corresponding `token` value to the configuration objects, or
set the following environment variables:

- `TINVEST_API_TOKEN`: API token for production trading.
- `TINVEST_SANDBOX_TOKEN`: API token for sandbox testing.

:::tip
We recommend using environment variables to manage your credentials.
:::

When starting the trading node, you'll receive immediate confirmation of whether your
credentials are valid and have trading permissions.

## Instrument provider

The `TInvestInstrumentProvider` loads instrument definitions from the T-Invest API via gRPC.
It queries all instrument types (shares, bonds, futures, ETFs, currencies, options) and converts
them to Nautilus instrument objects.

### Loading all instruments

```python
from nautilus_trader.adapters.tinvest.providers import TInvestInstrumentProvider
from nautilus_trader.adapters.tinvest.config import TInvestInstrumentProviderConfig

provider = TInvestInstrumentProvider(
    clock=clock,
    grpc_client=grpc_client,
    config=TInvestInstrumentProviderConfig(load_all=True),
)

await provider.load_all()
```

### Instrument conversion

The provider converts T-Invest instrument types to Nautilus instruments:

- **Shares**: Converted to `Equity` with FIGI as symbol, RUB currency, and 2-decimal price precision.
- **Bonds**: Converted to `Equity` (Nautilus has no BondInstrument).
- **ETFs**: Converted to `Equity`.
- **Futures**: Converted to `FuturesContract` with underlying asset reference.
- **Options**: Converted to `OptionContract` with strike price, expiration, and option kind (call/put).
- **Currencies**: Converted to `Equity` (not traded directly).

Price precision is computed dynamically from the `min_price_increment` field, clamped to a maximum of
16 decimal places. Default precision and increment for Russian instruments are defined in
[`constants.py`](nautilus_trader/adapters/tinvest/constants.py:111).

## Examples

Ready-to-run example scripts are provided under
[`python/examples/tinvest/`](python/examples/tinvest/data_tester.py):

### Data tester

[`python/examples/tinvest/data_tester.py`](python/examples/tinvest/data_tester.py) builds a live node
with the `TInvestDataClient` and attaches the built-in `DataTester` actor. It exercises
subscriptions (quotes, trades, book deltas) and historical data requests (bars, trades, book snapshot).

```bash
# Production (requires TINVEST_API_TOKEN)
python python/examples/tinvest/data_tester.py --run

# Sandbox (requires TINVEST_SANDBOX_TOKEN)
python python/examples/tinvest/data_tester.py --sandbox --run
```

Command-line options:

| Option        | Default                | Description                          |
|---------------|------------------------|--------------------------------------|
| `--sandbox`   | `False`                | Use the T-Invest sandbox environment.|
| `--instrument`| `BBG004730N88.TINVEST` | Instrument ID (FIGI.TINVEST).        |
| `--trader-id` | `TESTER-001`           | Trader ID for the node.              |
| `--run`       | `False`                | Actually connect and run the node.   |

### Execution tester

[`python/examples/tinvest/exec_tester.py`](python/examples/tinvest/exec_tester.py) builds a live node
with `TInvestDataClient` + `TInvestExecutionClient` and attaches the `ExecTester` strategy. It runs in
dry-run mode by default; pass `--live-orders` to send real orders (use the sandbox).

```bash
# Dry-run in the sandbox
python python/examples/tinvest/exec_tester.py --sandbox --run

# Real orders (sandbox only!)
python python/examples/tinvest/exec_tester.py --sandbox --live-orders --run
```

Command-line options:

| Option        | Default                | Description                                  |
|---------------|------------------------|----------------------------------------------|
| `--sandbox`   | `False`                | Use the T-Invest sandbox environment.        |
| `--instrument`| `BBG004730N88.TINVEST` | Instrument ID (FIGI.TINVEST).                |
| `--account-id`| `TINVEST-001`          | T-Invest account ID.                         |
| `--quantity`  | `1`                    | Order quantity in lots (integer).            |
| `--trader-id` | `TESTER-001`           | Trader ID for the node.                      |
| `--bestprice` | `False`                | Use `ORDER_TYPE_BESTPRICE` for `MARKET` orders. |
| `--live-orders` | `False`              | Send real orders (disable dry-run mode).     |
| `--run`       | `False`                | Actually connect and run the node.           |

:::warning
Both examples are test scripts with no alpha advantage. They are not intended for live trading
with real money. Always use `--sandbox` when testing order placement.
:::

## Unit tests

The adapter is covered by 274 unit tests under
[`tests/unit_tests/adapters/tinvest/`](tests/unit_tests/adapters/tinvest/test_config.py). Because the
T-Invest API is not available in CI, all tests use mocks (`unittest.mock`).

| Test file                                                            | Focus                                    | Tests |
|----------------------------------------------------------------------|------------------------------------------|-------|
| [`test_config.py`](tests/unit_tests/adapters/tinvest/test_config.py) | Configuration classes and conversions.   | 21    |
| [`test_common.py`](tests/unit_tests/adapters/tinvest/test_common.py) | Venue/client-id constants.               | 4     |
| [`test_data.py`](tests/unit_tests/adapters/tinvest/test_data.py)     | Data client, subscriptions, callbacks, native stream processing, historical requests. | 60 |
| [`test_execution.py`](tests/unit_tests/adapters/tinvest/test_execution.py) | Order submission/management, reports, account state, native streams. | 89 |
| [`test_factories.py`](tests/unit_tests/adapters/tinvest/test_factories.py) | Shared gRPC client singleton and factories. | 8  |
| [`test_grpc_client.py`](tests/unit_tests/adapters/tinvest/test_grpc_client.py) | gRPC wrapper methods, polling, subscriptions, execution methods. | 44 |
| [`test_providers.py`](tests/unit_tests/adapters/tinvest/test_providers.py) | Price precision, instrument conversion, instrument provider. | 48 |

Run all adapter tests:

```bash
pytest tests/unit_tests/adapters/tinvest/ -v
```

Run a specific module with coverage:

```bash
pytest tests/unit_tests/adapters/tinvest/test_providers.py --cov=nautilus_trader.adapters.tinvest -v
```

## Implementation notes

- **gRPC transport**: All communication uses gRPC over TLS. The adapter uses the `tonic` Rust gRPC
  framework.
- **Bearer authentication**: API tokens are sent as `Authorization: Bearer` headers on every request.
- **FIGI symbology**: Instruments are identified by FIGI (Financial Instrument Global Identifier).
- **Price precision**: Price precision is computed dynamically from the `min_price_increment` field
  returned by the API, with a maximum of 16 decimal places.
- **Lot-based quantities**: Order quantities are specified in lots, not individual units.
- **Account auto-resolution**: The execution client can auto-resolve the account ID from the
  T-Invest API if not explicitly configured (see
  [`_resolve_account_id()`](nautilus_trader/adapters/tinvest/execution.py:1210)).
- **Shared gRPC client**: A single `TInvestGrpcClient` is shared between the data and execution
  clients to avoid opening two TCP connections (see
  [`get_shared_grpc_client()`](nautilus_trader/adapters/tinvest/factories.py:42)).
- **Native streaming with polling fallback**: Real-time subscriptions use native PyO3 streams when
  available, otherwise REST polling.
- **Constants module**: Adapter-wide constants (candle mapping, order-type mapping, instrument
  mapping, price defaults) are centralized in
  [`constants.py`](nautilus_trader/adapters/tinvest/constants.py) (internal-only, not re-exported).
- **Sandbox support**: Sandbox trading is enabled via `sandbox=True` in the `TInvestClientConfig`;
  the sandbox service is exposed through `TInvestGrpcClient`.
- **Streaming**: Real-time data and order updates are delivered via gRPC server-side and
  bidirectional streaming.
- **Russian Trusted Root CA**: A PEM certificate is included for environments that require it.

## Contributing

:::info
For additional features or to contribute to the T-Invest adapter, please see our
[contributing guide](https://github.com/nautechsystems/nautilus_trader/blob/develop/CONTRIBUTING.md).
:::
