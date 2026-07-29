# T-Invest (MOEX)

<<<<<<< Updated upstream
[T-Invest](https://www.tinkoff.ru/invest/) is a brokerage platform by Tinkoff Bank that provides
access to the Moscow Exchange (MOEX). The adapter supports equities, bonds, futures, and options
on Russian and international markets.

This integration supports live market data ingest and order execution with T-Invest.

## Examples

You can find live example scripts in the [examples/live/tinvest](https://github.com/nautechsystems/nautilus_trader/tree/develop/examples/live/tinvest/) directory.

## Overview

This guide assumes a trader is setting up for both live market data feeds, and trade execution.
The T-Invest adapter includes multiple components, which can be used together or separately
depending on the use case.

- `TinvestHttpClient`: Low-level HTTP API connectivity.
- `TinvestMarketDataStream`: WebSocket market data stream.
- `TinvestInstrumentProvider`: Instrument parsing and loading functionality.
- `TinvestDataClient`: A market data feed manager.
- `TinvestExecutionClient`: An account management and trade execution gateway.
- `TinvestLiveDataClientFactory`: Factory for T-Invest data clients (used by the trading node builder).
- `TinvestLiveExecClientFactory`: Factory for T-Invest execution clients (used by the trading node builder).

:::note
Most users will define a configuration for a live trading node (as below),
and won't need to necessarily work with these lower level components directly.
=======
[T-Invest](https://developer.tbank.ru/invest/intro/intro) (formerly Tinkoff Invest) is a brokerage API
provided by T-Bank (formerly Tinkoff) for trading on the Moscow Exchange (MOEX). It offers access to
Russian equities, bonds, ETFs, futures, options, and currencies through a gRPC API.

NautilusTrader provides a Rust-native adapter for the T-Invest API with Python bindings via PyO3.
The adapter supports live market data ingest and order execution on the Moscow Exchange.

## Overview

This adapter is implemented in Rust under `crates/adapters/tinvest` with Python bindings for use in
Python-based workflows. It uses gRPC (via [tonic](https://github.com/hyperium/tonic)) to communicate
with the T-Invest API and does not require external T-Invest client libraries.

The T-Invest adapter includes multiple components, which can be used together or separately depending
on the use case:

- `TInvestGrpcClient`: Low-level gRPC API connectivity with authentication, retry logic, and
  connection pooling.
- `TInvestLiveMarketDataClient`: Market data feed manager implementing the `DataClient` trait.
- `TInvestLiveExecutionClient`: Account management and trade execution gateway implementing the
  `ExecutionClient` trait.
- `TInvestSandboxExecutionClient`: Sandbox execution client for testing without real funds.
- `TInvestMarketDataStream`: Bidirectional gRPC stream for real-time market data (trades, order books,
  candles, info).
- `TInvestOrderStateStream`: Server-side gRPC stream for real-time order state updates.
- `TInvestTradesStream`: Server-side gRPC stream for real-time trade updates.
- `TInvestPositionsStream`: Server-side gRPC stream for real-time position updates.
- `TInvestPortfolioStream`: Server-side gRPC stream for real-time portfolio updates.
- `TInvestDataClientFactory`: Factory for T-Invest data clients (used by the trading node builder).
- `TInvestExecutionClientFactory`: Factory for T-Invest execution clients (used by the trading node builder).

:::note
Most users will define a configuration for a live trading node (as below),
and won't need to work with these lower-level components directly.
>>>>>>> Stashed changes
:::

## T-Invest documentation

<<<<<<< Updated upstream
T-Invest provides documentation for developers which can be found at the
[T-Invest API documentation](https://tinkoff.github.io/investAPI/).
It's recommended you also refer to the T-Invest API documentation in conjunction with this
=======
T-Invest provides extensive documentation for developers:

- [T-Invest API Introduction](https://developer.tbank.ru/invest/intro/intro): Main entry point for API access.
- [T-Invest gRPC API Reference](https://developer.tbank.ru/invest/api/): Complete gRPC API reference.
- [T-Invest Sandbox](https://developer.tbank.ru/invest/intro/developer/sandbox/): Sandbox environment documentation.

It's recommended you also refer to the T-Invest documentation in conjunction with this
>>>>>>> Stashed changes
NautilusTrader integration guide.

## Products

<<<<<<< Updated upstream
The adapter supports the following instrument types available on MOEX:

| Venue category | Examples | Nautilus asset class |
| -------------- | -------- | --------------------- |
| Equities       | `YNDX`  | Equity                |
| Bonds          | `RU000A1038V6` | Fixed Income    |
| Futures        | `Si-6.24` | Future             |
| Options        | `SiH400000GA` | Option          |

The adapter represents T-Invest instruments using standard NautilusTrader domain types:
`Equity`, `Future`, and `OptionContract`.

## Symbology

The adapter preserves T-Invest `figi` and `ticker` symbols and appends the Nautilus venue
identifier `.TINVEST`. Perpetual contracts do not exist on MOEX; futures have fixed expiration dates.

| Instrument    | T-Invest FIGI/Ticker | Nautilus InstrumentId |
| ------------- | -------------------- | --------------------- |
| Yandex equity | `BBG006L8G4H1` / `YNDX` | `YNDX.TINVEST`      |
| Si futures    | `FUT_SI_0624` / `Si-6.24` | `Si-6.24.TINVEST`   |
| Option        | Option FIGI | `SiH400000GA.TINVEST` |

The venue identifier is `TINVEST`. To construct a Nautilus `InstrumentId`:
=======
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
>>>>>>> Stashed changes

```python
from nautilus_trader.model.identifiers import InstrumentId

<<<<<<< Updated upstream
instrument_id = InstrumentId.from_str("YNDX.TINVEST")
```

## Environments

T-Invest provides two trading environments. Configure the appropriate environment using the
`environment` parameter in your client configuration.

| Environment    | Config                                 | Description                            |
| -------------- | -------------------------------------- | -------------------------------------- |
| **Sandbox**    | `environment=TinvestEnvironment.SANDBOX`    | Test environment with simulated funds. |
| **Production** | `environment=TinvestEnvironment.PRODUCTION` | Live trading with real funds.          |

### Sandbox

The default environment for development and testing with simulated funds.
All sandbox endpoints are resolved automatically when `environment=TinvestEnvironment.SANDBOX`.

#### 1. Create a sandbox account

Follow the [T-Invest documentation](https://tinkoff.github.io/investAPI/) to obtain API access.
You need a Tinkoff Open API sandbox account.

#### 2. Create API tokens

Use the T-Invest sandbox UI to generate API tokens.
Store the `token` securely.

#### 3. Set environment variables

```bash
export TINVEST_API_TOKEN="your-sandbox-token"
```

#### 4. Configure the trading node

```python
config = TradingNodeConfig(
    ...,  # Omitted
    data_clients={
        TINVEST: TinvestDataClientConfig(
            environment=TinvestEnvironment.SANDBOX,
            instrument_provider=InstrumentProviderConfig(load_all=True),
        ),
    },
    exec_clients={
        TINVEST: TinvestExecClientConfig(
            environment=TinvestEnvironment.SANDBOX,
            instrument_provider=InstrumentProviderConfig(load_all=True),
        ),
    },
)
```

### Production

For live trading with real funds. Requires a verified T-Invest account.

```python
config = TinvestExecClientConfig(
    environment=TinvestEnvironment.PRODUCTION,
)
```

:::warning
Ensure you are using the correct environment before placing orders.
Sandbox is the default to prevent accidental live trading.
:::

## Market data

The adapter provides real-time market data via WebSocket subscriptions, with HTTP endpoints
for historical data backfill.

### Data types

| T-Invest Data        | Nautilus Data Type   | Notes                                                     |
| -------------------- | -------------------- | ---------------------------------------------------------- |
| Order book (L1)      | `QuoteTick`          | Best bid/ask top‑of‑book from L1 book subscription.        |
| Order book (L2)      | `OrderBookDelta`     | Aggregated price levels.                                   |
| Trades               | `TradeTick`          | Real‑time trade events from trade‑only WebSocket subscription. |
| Bars/candles         | `Bar`                | OHLCV data (total volume only, no buy/sell breakdown).     |
| Instrument status    | `InstrumentStatus`   | State changes (open, halted, closed) from subscription.    |

### WebSocket subscription behavior

T-Invest market data WebSocket subscriptions use one active stream per account. The adapter
manages subscriptions automatically based on the configured instrument universe.

### Bar intervals

| Interval | Description |
| -------- | ----------- |
| `1m`     | 1-minute    |
| `5m`     | 5-minute    |
| `15m`    | 15-minute   |
| `1h`     | 1-hour      |
| `1d`     | 1-day       |

## Orders capability

### Nautilus order types

| Order Type             | Supported | Notes                                           |
| ---------------------- | --------- | ----------------------------------------------- |
| `MARKET`               | ✓         | Adapter‑simulated with an aggressive IOC price. |
| `LIMIT`                | ✓         | Standard limit order.                           |
| `STOP_LIMIT`           | -         | *Not supported*.                                |
| `LIMIT_IF_TOUCHED`     | -         | *Not supported*.                                |
| `STOP_MARKET`          | -         | *Not supported*.                                |
| `MARKET_IF_TOUCHED`    | -         | *Not supported*.                                |
| `TRAILING_STOP_MARKET` | -         | *Not supported*.                                |

### Execution instructions

| Instruction      | Supported | Notes                                                         |
| ---------------- | --------- | ------------------------------------------------------------- |
| `post_only`      | ✓         | Maker‑only; rejected if the order would take.                 |
| `reduce_only`    | -         | Rejected locally; T-Invest exposes no reduce‑only field.      |
| `quote_quantity` | -         | Rejected locally; the adapter wire path encodes base only.    |
| `display_qty`    | -         | Rejected locally; the adapter wire path has no display field. |

### Time in force

| Time in Force  | Supported | Notes                            |
| -------------- | --------- | -------------------------------- |
| `GTC`          | ✓         | Good Till Canceled.              |
| `GTD`          | -         | Rejected locally by the adapter. |
| `DAY`          | ✓         | Valid until end of trading day.  |
| `IOC`          | ✓         | Immediate or Cancel.             |
| `FOK`          | ✓         | Fill or Kill.                    |

### Advanced order features

| Feature            | Supported | Notes                                                              |
| ------------------ | --------- | ------------------------------------------------------------------ |
| Order modification | ✓         | Supports order replacement.                                        |
| Cancel order       | ✓         | Single order cancellation.                                         |
| Cancel all orders  | ✓         | Cancel all open orders.                                            |
| Batch cancel       | -         | The adapter sends individual cancels.                              |
| Order lists        | -         | *Not supported*.                                                   |

### Position management

| Feature         | Supported | Notes                                |
| --------------- | --------- | ------------------------------------ |
| Query positions | ✓         | Real‑time position updates.          |
| Position mode   | -         | Netting mode only.                   |
| Cross margin    | -         | Not applicable to equities trading.  |

### Order querying

| Feature              | Supported | Notes                                                   |
| -------------------- | --------- | ------------------------------------------------------- |
| Query open orders    | ✓         | List all active orders.                                 |
| Query single order   | ✓         | By venue order ID or client order ID (any order state). |
| Order status reports | ✓         | Open‑order checks and historical startup mass status.   |
| Fill reports         | ✓         | Execution and fill history.                             |

## Authentication

T-Invest uses bearer token authentication:

1. API token is passed via the `Authorization` header.
2. The adapter requests session tokens and reuses them for REST and WebSocket requests.
3. Sandbox tokens are validated automatically.

## Configuration

### Data client configuration options

| Option                             | Default   | Description                                                         |
| ---------------------------------- | --------- | ------------------------------------------------------------------- |
| `token`                            | `None`    | API token; loaded from `TINVEST_API_TOKEN` env var when omitted.        |
| `environment`                      | `SANDBOX` | Trading environment (`SANDBOX` or `PRODUCTION`).                    |
| `base_url_http`                    | `None`    | Override for the REST base URL.                                     |
| `base_url_ws`                      | `None`    | Override for the market data WebSocket URL.                         |
| `proxy_url`                        | `None`    | Optional proxy URL for HTTP and WebSocket transports.               |
| `update_instruments_interval_mins` | `60`      | Interval (minutes) between instrument catalog refreshes.            |

### Execution client configuration options

| Option                             | Default   | Description                                                         |
| ---------------------------------- | --------- | ------------------------------------------------------------------- |
| `token`                            | `None`    | API token; loaded from `TINVEST_API_TOKEN` env var when omitted.        |
| `environment`                      | `SANDBOX` | Trading environment (`SANDBOX` or `PRODUCTION`).                    |
| `base_url_http`                   | `None`    | Override for the REST base URL.                                     |
| `base_url_ws`                      | `None`    | Override for the orders WebSocket URL.                              |
| `proxy_url`                        | `None`    | Optional proxy URL for HTTP and WebSocket transports.               |
| `update_instruments_interval_mins` | `60`      | Interval (minutes) between instrument catalog refreshes.            |

The most common use case is to configure a live `TradingNode` to include T-Invest
data and execution clients. To achieve this, add a `TINVEST` section to your client
configuration(s):

```python
from nautilus_trader.adapters.tinvest import TINVEST
from nautilus_trader.adapters.tinvest import TinvestDataClientConfig
from nautilus_trader.adapters.tinvest import TinvestEnvironment
from nautilus_trader.adapters.tinvest import TinvestExecClientConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import TradingNodeConfig

config = TradingNodeConfig(
    ...,  # Omitted
    data_clients={
        TINVEST: TinvestDataClientConfig(
            environment=TinvestEnvironment.SANDBOX,
            instrument_provider=InstrumentProviderConfig(load_all=True),
        ),
    },
    exec_clients={
        TINVEST: TinvestExecClientConfig(
            environment=TinvestEnvironment.SANDBOX,
            instrument_provider=InstrumentProviderConfig(load_all=True),
        ),
    },
)
```

Then, create a `TradingNode` and add the client factories:

```python
from nautilus_trader.adapters.tinvest import TINVEST
from nautilus_trader.adapters.tinvest import TinvestLiveDataClientFactory
from nautilus_trader.adapters.tinvest import TinvestLiveExecClientFactory
from nautilus_trader.live.node import TradingNode

# Instantiate the live trading node with a configuration
node = TradingNode(config=config)

# Register the client factories with the node
node.add_data_client_factory(TINVEST, TinvestLiveDataClientFactory)
node.add_exec_client_factory(TINVEST, TinvestLiveExecClientFactory)

# Finally build the node
=======
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

## Environments

T-Invest provides two trading environments. Configure the appropriate environment using the
`sandbox` flag in your client configuration.

| Environment    | Config          | gRPC Endpoint                            |
|----------------|-----------------|------------------------------------------|
| **Production** | `sandbox=False` | `invest-public-api.tbank.ru:443`         |
| **Sandbox**    | `sandbox=True`  | `sandbox-invest-public-api.tbank.ru:443` |

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

4. The sandbox account starts with zero balance. Use `SandboxPayIn` to deposit funds:

   ```python
   # Deposit 100,000 RUB into the sandbox account
   await client.sandbox_pay_in("RUB", 100000.0)
   ```

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

The `TInvestGrpcClient` manages connections to all T-Invest gRPC services:

| Service                   | Client Method          | Purpose                                               |
|---------------------------|------------------------|-------------------------------------------------------|
| `InstrumentsService`      | `instruments()`        | Instrument metadata (shares, bonds, futures, etc.).   |
| `MarketDataService`       | `market_data()`        | Historical and snapshot market data.                  |
| `MarketDataStreamService` | `market_data_stream()` | Real-time market data streaming.                      |
| `OperationsService`       | `operations()`         | Account portfolio, positions, and operations history. |
| `OperationsStreamService` | `operations_stream()`  | Real-time portfolio and position updates.             |
| `OrdersService`           | `orders()`             | Order placement, modification, and cancellation.      |
| `OrdersStreamService`     | `orders_stream()`      | Real-time order state and trade updates.              |
| `StopOrdersService`       | `stop_orders()`        | Stop-order management.                                |
| `UsersService`            | `users()`              | Account information.                                  |
| `SandboxService`          | `sandbox()`            | Sandbox operations (pay-in, orders, portfolio).       |

### Connection management

The client supports:

- **TLS encryption**: Required for all connections.
- **Custom CA certificates**: For Russian Trusted Root CA support.
- **Keepalive**: HTTP/2 keepalive pings to maintain long-lived connections.
- **Retry with exponential backoff**: Configurable retry for failed requests.
- **Connection pooling**: Shared channel across all service stubs.

### Retry policy

The client implements exponential backoff for failed requests:

- `max_retries`: Maximum retry attempts (default: 3).
- `retry_wait_ms`: Initial wait duration (default: 2,000 ms).
- Backoff doubles on each retry: `wait_ms * 2^attempt`.

## Data capability

### Subscriptions (real-time)

The adapter supports real-time market data via bidirectional gRPC streaming:

| Data type          | Stream Method            | Notes                               |
|--------------------|--------------------------|-------------------------------------|
| `TradeTick`        | `subscribe_trades()`     | Real-time trade ticks.              |
| `QuoteTick`        | `subscribe_order_book()` | Best bid/ask from order book depth. |
| `OrderBookDepth10` | `subscribe_order_book()` | Top 10 levels of market depth.      |
| `Bar`              | `subscribe_candles()`    | OHLCV candles (1min to 1month).     |
| `InstrumentStatus` | `subscribe_info()`       | Trading status updates.             |

### Requests (historical)

| Data type    | Endpoint                           | Notes                        |
|--------------|------------------------------------|------------------------------|
| `QuoteTick`  | `GetOrderBook`                     | Current order book snapshot. |
| `TradeTick`  | `GetLastTrades`                    | Recent trade history.        |
| `Bar`        | `GetCandles`                       | Historical OHLCV candles.    |
| `Instrument` | `Shares`, `Bonds`, `Futures`, etc. | Instrument definitions.      |
| `LastPrice`  | `GetLastPrices`                    | Current last prices.         |
| `ClosePrice` | `GetClosePrices`                   | Previous day close prices.   |

### Supported bar intervals

| Interval   | T-Invest CandleInterval | BarSpec     |
|------------|-------------------------|-------------|
| 1 minute   | 1                       | `1-MINUTE`  |
| 2 minutes  | 6                       | `2-MINUTE`  |
| 3 minutes  | 7                       | `3-MINUTE`  |
| 5 minutes  | 2                       | `5-MINUTE`  |
| 10 minutes | 8                       | `10-MINUTE` |
| 15 minutes | 3                       | `15-MINUTE` |
| 30 minutes | 9                       | `30-MINUTE` |
| 1 hour     | 4                       | `1-HOUR`    |
| 2 hours    | 10                      | `2-HOUR`    |
| 4 hours    | 11                      | `4-HOUR`    |
| 1 day      | 5                       | `1-DAY`     |
| 1 week     | 12                      | `1-WEEK`    |
| 1 month    | 13                      | `1-MONTH`   |

## Orders capability

### Order types

| Order Type    | Supported | Notes                                          |
|---------------|-----------|------------------------------------------------|
| `MARKET`      | ✓         | Immediate execution at market price.           |
| `LIMIT`       | ✓         | Execution at specified price or better.        |
| `STOP_MARKET` | -         | *Not supported natively; use stop-orders API.* |
| `STOP_LIMIT`  | -         | *Not supported natively; use stop-orders API.* |

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

The adapter provides access to T-Invest's stop-order API through the `TInvestGrpcClient`:

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
| Submit order      | ✓         | Single order submission via `post_order`. |
| Modify order      | ✓         | Order modification via `replace_order`.   |
| Cancel order      | ✓         | Single order cancellation.                |
| Cancel all orders | -         | *Not implemented.*                        |
| Batch submit      | -         | *Not implemented.*                        |
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
| Order status updates | ✓         | Real-time via `OrderStateStream`. |
| Trade history        | ✓         | Via `GetOperationsByCursor`.      |
| Fill reports         | ✓         | Via `generate_fill_reports`.      |

## Streaming

The adapter provides real-time streaming via gRPC server-side and bidirectional streams:

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

### Trades stream (server-side)

The `TInvestTradesStream` provides real-time trade updates:

- Executed trade notifications.
- Trade details (price, quantity, direction).

## Rate limiting

T-Invest applies rate limits to API requests. The adapter implements retry with exponential backoff
to handle rate limit responses gracefully.

| Limit Type          | Default       | Notes                                     |
|---------------------|---------------|-------------------------------------------|
| Requests per second | Not published | T-Invest may throttle excessive requests. |
| Concurrent streams  | Not published | Manage stream connections carefully.      |

The adapter's retry mechanism helps mitigate transient rate limit errors:

- `max_retries`: 3 (configurable).
- `retry_wait_ms`: 2,000 ms initial (configurable).
- Backoff: doubles on each retry.

## Configuration

### Client configuration options

The `TInvestClientConfig` provides the following configuration options:

| Option                  | Default                          | Description                                          |
|-------------------------|----------------------------------|------------------------------------------------------|
| `token`                 | Required                         | T-Invest API token.                                  |
| `target`                | `invest-public-api.tbank.ru:443` | gRPC endpoint (host:port).                           |
| `sandbox`               | `false`                          | Use sandbox environment when `true`.                 |
| `connection_timeout_ms` | `30,000`                         | Connection timeout in milliseconds.                  |
| `keepalive_ms`          | `60,000`                         | HTTP/2 keepalive interval in milliseconds.           |
| `max_message_size`      | `16,777,216`                     | Maximum gRPC message size in bytes (16 MB).          |
| `max_retries`           | `3`                              | Maximum retry attempts for failed requests.          |
| `retry_wait_ms`         | `2,000`                          | Initial retry wait duration in milliseconds.         |
| `trader_id`             | `None`                           | Optional trader ID (required for execution client).  |
| `account_id`            | `None`                           | Optional account ID (required for execution client). |
| `ca_cert_path`          | `None`                           | Path to custom CA certificate bundle (PEM format).   |

### Data client configuration options

The `TInvestDataClientConfig` provides the following configuration options:

| Option                             | Default  | Description                                     |
|------------------------------------|----------|-------------------------------------------------|
| `tinvest`                          | Required | `TInvestClientConfig` for gRPC connection.      |
| `update_instruments_interval_mins` | `None`   | Interval in minutes between instrument updates. |

### Execution client configuration options

The `TInvestExecClientConfig` provides the following configuration options:

| Option       | Default  | Description                                |
|--------------|----------|--------------------------------------------|
| `tinvest`    | Required | `TInvestClientConfig` for gRPC connection. |
| `account_id` | `None`   | Account ID for trading.                    |

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
    account_id="TINVEST-0000000000",  # Will be auto-resolved
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
>>>>>>> Stashed changes
node.build()
```

### API credentials

There are two options for supplying your credentials to the T-Invest clients.
Either pass the corresponding `token` value to the configuration objects, or
set the following environment variables:

<<<<<<< Updated upstream
- `TINVEST_API_TOKEN`
=======
- `TINVEST_API_TOKEN`: API token for production trading.
- `TINVEST_SANDBOX_TOKEN`: API token for sandbox testing.
>>>>>>> Stashed changes

:::tip
We recommend using environment variables to manage your credentials.
:::

When starting the trading node, you'll receive immediate confirmation of whether your
credentials are valid and have trading permissions.

<<<<<<< Updated upstream
## Implementation notes

- **MOEX instruments**: The adapter handles equities, bonds, futures, and options listed on MOEX.
- **Instrument loading**: The adapter refreshes the instrument catalog on a configurable interval
  to pick up new listings and delistings.
- **Rate limiting**: The adapter respects T-Invest rate limits with automatic retries.
- **Market orders**: T-Invest does not support native market orders. The adapter uses a preview
  endpoint to determine the take-through price and submits an aggressive IOC limit order.
- **Order modification**: T-Invest supports atomic order replacement. The adapter maps `modify_order`
  to the venue's replace mechanism.
- **Instrument fee rates**: T-Invest reports maker and taker rates per account, so the
  adapter resolves them after authenticating and applies them to every instrument. The execution
  client fails to connect if that lookup fails, rather than reporting zero fees for the process
  lifetime. A data client configured without credentials cannot read the rates and reports zero fees.
- **Fill commissions**: Real-time fill events from REST do not include fee data.
  Commission is reported as zero for streaming fills. During reconciliation, the REST
  endpoint provides accurate fee information.
=======
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

## Implementation notes

- **gRPC transport**: All communication uses gRPC over TLS. The adapter uses the `tonic` Rust gRPC
  framework.
- **Bearer authentication**: API tokens are sent as `Authorization: Bearer` headers on every request.
- **FIGI symbology**: Instruments are identified by FIGI (Financial Instrument Global Identifier).
- **Price precision**: Price precision is computed dynamically from the `min_price_increment` field
  returned by the API, with a maximum of 16 decimal places.
- **Lot-based quantities**: Order quantities are specified in lots, not individual units.
- **Account auto-resolution**: The execution client can auto-resolve the account ID from the
  T-Invest API if not explicitly configured.
- **Sandbox support**: The adapter provides a separate `TInvestSandboxExecutionClient` for testing
  with simulated funds.
- **Streaming**: Real-time data and order updates are delivered via gRPC server-side and
  bidirectional streaming.
- **Russian Trusted Root CA**: A PEM certificate is included for environments that require it.
>>>>>>> Stashed changes

## Contributing

:::info
For additional features or to contribute to the T-Invest adapter, please see our
[contributing guide](https://github.com/nautechsystems/nautilus_trader/blob/develop/CONTRIBUTING.md).
:::