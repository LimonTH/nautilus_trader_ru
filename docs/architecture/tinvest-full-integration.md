# Архитектура: полная интеграция адаптера T-Invest (MOEX) в NautilusTrader

- Статус: АКТУАЛИЗИРОВАН (прогресс по этапам T0–T1 отражён; ожидает T2/T3)
- Автор: 🏗️ Architect
- Версия: 0.2
- Дата: 2026

## 1. Контекст и цели

Пользователь форкнул [`nautilus_trader`](https://github.com/nautechsystems/nautilus_trader) и ведёт
локальную разработку адаптера для российского брокера **Т-Инвестиции (T-Invest / MOEX)**.
Локальная работа ведётся в ветке `feature-tinvest` и содержит уже значительный объём кода
(Rust-ядро + Python-обвязка через PyO3). Ветка не запушена в GitHub-форк
(`origin = https://github.com/LimonTH/nautilus_trader_ru`).

### 1.1. Три цели задачи

1. **Синхронизировать git**: локальный `develop` отстаёт от `origin/develop` на 94 коммита;
   привести ветки в согласованное состояние и выгрузить работу на GitHub-форк.
2. **Завершить полную интеграцию** с API T-Invest: поддержать «всё, что возможно» из gRPC-контрактов
   (11 сервисов), в терминах возможностей NautilusTrader (данные, исполнение, портфель, песочница).
3. **Залить результат в отдельную ветку** GitHub-форка.

### 1.2. Принятые решения заказчика (зафиксированы)

| # | Вопрос | Решение |
|---|--------|---------|
| R1 | Судьба `libs/` (клоны invest-contracts, invest-java) | **Не включать в ветку вообще**. Proto уже скопированы в `crates/adapters/tinvest/proto/` |
| R2 | Git-стратегия | Обновить `develop` → `origin/develop`; **merge** `develop` в `feature-tinvest` (без переписывания истории); запушить как `feature-tinvest` |
| R3 | Объём интеграции | **Максимум**: все инструменты, маркетдата (вкл. тех.индикаторы), заявки (рыночные/лимитные/лучшая цена/асинхронные/замена/отмена), стоп-заявки, портфель/позиции/операции, стримы, песочница |

### 1.3. Критерии готовности (DoD) — итоговые

- [ ] `develop` синхронизирован с `origin/develop` (0 коммитов отставания), рабочее дерево чистое.
- [ ] Ветка `feature-tinvest` смержена со свежим `develop` без конфликтов; история не переписана.
- [ ] Удалены из индекса gitlink-записи `libs/invest-contracts`, `libs/invest-java` (без `.gitmodules` — сломанные субмодули); сами папки не отслеживаются.
- [ ] Устранены закоммиченные merge-маркеры (`<<<<<<<`, `=======`, `>>>>>>>`) в 3 файлах:
  `pyproject.toml`, `python/pyproject.toml`, `docs/integrations/tinvest.md`.
- [ ] `cargo build` / `cargo clippy` для `nautilus-tinvest` проходят без ошибок.
- [ ] Python unit-тесты `python/tests/unit/adapters/tinvest/` и integration-тесты зелёные.
- [ ] Реализован полный функционал согласно Gap-анализу (раздел 6).
- [ ] Документация `docs/integrations/tinvest.md` и `docs/api_reference/adapters/tinvest.md` обновлены и не содержат маркеров конфликтов.
- [ ] Ветка `feature-tinvest` запушена в `origin` (GitHub-форк).

---

## 2. Терминология

| Термин | Значение |
|--------|----------|
| T-Invest API | gRPC API брокера Т-Инвестиции (бывш. Tinkoff Invest API), эндпоинт `invest-public-api.tbank.ru:443`, песочница `sandbox-invest-public-api.tbank.ru:443` |
| FIGI | Financial Instrument Global Identifier — первичный идентификатор инструмента в T-Invest |
| Quotation | Прототип `{units: int64, nano: int32}` — десятичное число с фиксированной точностью |
| MoneyValue | Прототип `{currency, units, nano}` — денежная сумма |
| Venue | В Nautilus — торговая площадка; для адаптера `TINVEST` |
| InstrumentId | `{symbol}.TINVEST`, где `symbol` = FIGI |
| gRPC-сервис | Один из 11 сервисов контракта (см. раздел 5) |
| Native stream | Поток, реализованный в Rust (PyO3), а не в Python |

---

## 3. Обзор существующей архитектуры (feature-tinvest)

### 3.1. Стек и интеграционные точки

- **Rust-ядро**: `crates/adapters/tinvest` (crate `nautilus-tinvest`).
  - gRPC-клиент на `tonic` + `prost`; proto-контракты скопированы локально в `crates/adapters/tinvest/proto/`
    (8 `*.proto` + `google/api/field_behavior.proto`).
  - `build.rs` генерирует код через `tonic_build::configure()`, `build_server(false)`.
  - Реализует трейты Nautilus: `DataClientFactory`, `ExecutionClientFactory`, `ClientConfig`.
  - Зарегистрирован в корневом `Cargo.toml` (workspace member) и в `crates/pyo3` (feature `python`).
  - PyO3-модуль `tinvest` экспортируется в `nautilus_trader.core.nautilus_pyo3.tinvest`.
- **Python-обвязка**: `nautilus_trader/adapters/tinvest/`.
  - Конфиги, `TInvestGrpcClient` (unary + polling), `TInvestDataClient`, `TInvestExecutionClient`,
    `TInvestInstrumentProvider`, фабрики, конвертеры.
  - Файлы `.pyi` в `python/nautilus_trader/adapters/tinvest/`.
- **Тесты**: `python/tests/unit/adapters/tinvest/` (9 файлов, ~8–14 KB каждый),
  `python/tests/integration_tests/adapters/tinvest/` (2 файла).
- **Документация**: `docs/integrations/tinvest.md` (895 строк, **содержит merge-маркеры — дефект**),
  `docs/api_reference/adapters/tinvest.md`.
- **Пример**: `examples/live/tinvest_live.py`.
- **Конфигурация окружения**: `.env.example` (`TINVEST_TOKEN`, `TINVEST_SANDBOX`).

### 3.2. Карта модулей Rust

```
crates/adapters/tinvest/
├── Cargo.toml, build.rs
├── certs/RussianTrustedRootCA.pem        # корневой CA для TLS к tbank.ru
├── proto/                                # локальные копии gRPC-контрактов
├── src/
│   ├── lib.rs                            # re-export proto, модули, feature flags
│   ├── client.rs                         # TInvestGrpcClient: connect/disconnect/auth/retry, стабы 10 сервисов
│   ├── config.rs                         # TInvestClientConfig (+ Default, effective_target)
│   ├── enums.rs                          # (пусто/минимально) маппинг перечислений
│   ├── common/{mod,types,convert}.rs     # конвертеры proto <-> nautilus-типы
│   ├── data/{mod,core}.rs                # TInvestLiveMarketDataClient
│   ├── execution/{mod,core}.rs           # TInvestLiveExecutionClient
│   ├── providers/{mod,instruments}.rs    # TInvestInstrumentProvider (load_all)
│   ├── sandbox/{mod,core}.rs             # TInvestSandboxExecutionClient
│   ├── stream/{mod,core,native}.rs       # NativeMarketDataStream + макросы стримов
│   ├── factories.rs                      # DataClientFactory / ExecutionClientFactory
│   └── python/{mod,config,factories,stream}.rs  # PyO3-биндинги
└── tests/python.rs                       # pyo3-тест
```

### 3.3. Текущий охват публичного API (по результатам аудита)

**Rust:**

| Модуль | Публичный API (реализовано) |
|--------|------------------------------|
| `client.rs` | `connect`, `disconnect`, `is_connected`, `with_auth`, `with_retry`; стабы: `instruments`, `market_data`, `market_data_stream`, `operations`, `operations_stream`, `orders`, `orders_stream`, `stop_orders`, `users`, `sandbox` (**нет** `signals`) |
| `data/core.rs` | `get_last_prices`, `get_trading_status`, `get_close_prices`, `start_market_data_stream` |
| `execution/core.rs` | `get_portfolio`, `get_operations`, `get_max_lots`, `start_order_state_stream`, `update_account_state` |
| `providers/instruments.rs` | `load_all`, `get`, `all`, `len`, `is_empty` |
| `stream/native.rs` | `subscribe_trades`, `unsubscribe_trades`, `subscribe_order_book`, `unsubscribe_order_book`, `subscribe_info`, `stop`, `is_active`; макрос для `OrderState/Portfolio/Positions/Trades`-стримов |
| `sandbox/core.rs` | `sandbox_pay_in`, `get_sandbox_portfolio`, `get_sandbox_positions`, `sandbox_get_last_prices`, `sandbox_get_portfolio`, `sandbox_get_operations` |
| `convert.rs` | `to_instrument_id`, `quotation_to_price/quantity`, `money_value_to_money`, `timestamp_to_unix_nanos`, `convert_share/bond/future/currency/etf/option_to_instrument`, `convert_candle_to_bar_data`, `convert_trade_to_trade_data`, `order_status/side/type` маппинги, `convert_order_state_to_report`, `convert_operation_item_to_fill_reports`, `convert_security/futures_position_to_report`, `convert_proto_trade_to_tick`, `convert_proto_candle_to_bar`, `convert_proto_orderbook_to_quote_tick` |

**Python `grpc_client.py`:** `request_instruments`, `request_instrument`, `request_candles`,
`request_order_book`, `request_trades`, `subscribe/unsubscribe` (order_book, trades, candles через polling),
`post_order`, `cancel_order`, `replace_order`, `get_order_state`, `get_orders`, `get_portfolio`,
`get_positions`, `get_operations`, `get_accounts`, `post_stop_order`, `cancel_stop_order`,
`get_stop_orders`, `open/close_sandbox_account`, `sandbox_pay_in`.

**Python `data.py`:** полный `LiveMarketDataClient`: подписки на order book deltas/snapshot,
quote ticks, trade ticks, bars, instrument status/close; native stream loop; запросы
`_request_quote_ticks/_request_trade_ticks/_request_bars`.

**Python `execution.py`:** полный `LiveExecutionClient`: `_submit_order`, `_submit_order_list`,
`_modify_order`, `_cancel_order`, `_cancel_all_orders`, `_query_account`, генерация отчётов
(order status / fills / positions / mass status), обработка native streams
(order_state / portfolio / positions).

**Python `providers.py`:** конвертация share/etf/bond/future/currency/option → Nautilus-инструменты.

---

## 4. Целевая архитектура

### 4.1. Принципы

1. **Rust-core, тонкий Python-слой** — вся «тяжёлая» работа (gRPC, стримы, конвертация) в Rust
   (аналогично адаптерам bybit/deribit/polymarket). Python использует PyO3-биндинги
   (`nautilus_pyo3.tinvest`) и не дублирует логику.
2. **Один gRPC-клиент** `TInvestGrpcClient` — единственная точка входа к API; держит пул стабов,
   авторизацию, retry/backoff, TLS (включая Russian Trusted Root CA).
3. **Покрытие 11 сервисов** контракта по принципу «всё, что имеет смысл в Nautilus».
4. **Стриминг предпочтительнее polling**: market data через bidi-стрим (`MarketDataStream`),
   исполнение/портфель через server-side стримы (`OrdersStreamService`, `OperationsStreamService`).
   Поллинг остаётся fallback'ом для unary-методов и для сред без native streaming.
5. **Конвертация в одном месте** (`convert.rs` / `providers.py`) — единый словарь маппинга типов.
6. **Не включать `libs/`** в репозиторий; proto живут только в `crates/adapters/tinvest/proto/`.
7. **Полнота без потери стабильности**: фичи, не имеющие смысла в Nautilus
   (новости, бренды, активы-справочники, сигналы как отдельная сущность), помечаются
   `NOT_APPLICABLE` и не блокируют DoD (см. Gap-анализ).

### 4.2. Компонентная схема (целевое состояние)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        NautilusTrader Engine                          │
│  DataEngine ◄── TInvestDataClient ──► TInvestInstrumentProvider        │
│  ExecEngine  ◄── TInvestExecutionClient ──► TInvestSandboxExecClient   │
└──────────────┬───────────────────────────────────────▲─────────────────┘
               │ PyO3 (nautilus_pyo3.tinvest)          │ события/отчёты
┌──────────────▼───────────────────────────────────────┴─────────────────┐
│                       Rust-ядро (crates/adapters/tinvest)              │
│  TInvestGrpcClient ──► стабы 11 gRPC-сервисов (tonic)                  │
│  NativeMarketDataStream / OrderStateStream / PortfolioStream /         │
│  PositionsStream / OperationsStream / TradesStream                     │
│  convert.rs (proto ◄─► nautilus-типы)                                  │
└──────────────┬─────────────────────────────────────────────────────────┘
               │ TLS + Russian Trusted Root CA, auth-токен, retry/backoff
┌──────────────▼─────────────────────────────────────────────────────────┐
│            T-Invest API (gRPC, invest-public-api.tbank.ru:443)         │
│  11 сервисов: Users, Instruments, MarketData, Orders, StopOrders,      │
│  Operations, Sandbox, Signals, MarketDataStream, OrdersStream,         │
│  OperationsStream                                                     │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.3. Потоки данных

**Данные (маркетдата):**
1. Стратегия подписывается → `DataEngine` → `TInvestDataClient._subscribe_*`.
2. Клиент маппит запрос на `MarketDataRequest` (subscribe/unsubscribe) и отправляет в bidi-стрим.
3. Входящие `MarketDataResponse` (trades / orderbook / candle / last_price / info) конвертируются
   в Nautilus-события (`TradeTick`, `QuoteTick`, `Bar`, `InstrumentStatus`, `InstrumentClose`).
4. Unary-запросы истории (`GetCandles`, `GetLastPrices`, `GetOrderBook`) — через `request_*`.
5. Тех.индикаторы — через `GetTechAnalysis` (если нужен внешний источник) либо штатные индикаторы Nautilus.

**Исполнение:**
1. Команды движка (`SubmitOrder`, `ModifyOrder`, `CancelOrder`, `CancelAllOrders`) → `TInvestExecutionClient`.
2. Маппинг на `PostOrderRequest` / `ReplaceOrderRequest` / `CancelOrderRequest`.
3. Состояние заявок и сделок — через `OrdersStreamService.OrderStateStream` / `TradesStream`
   + отчёты (`generate_order_status_report(s)`, `generate_fill_reports`).
4. Стоп-заявки — через `StopOrdersService.PostStopOrder` (TakeProfit / StopLoss / StopLimit).

**Портфель/операции:**
1. `OperationsStreamService.PortfolioStream` / `PositionsStream` / `OperationsStream` — realtime.
2. Unary `GetPortfolio` / `GetPositions` / `GetOperations` / `GetOperationsByCursor` — по запросу/сверка.

**Песочница:** зеркальная ветка клиентов на `SandboxService`, все методы имеют `Sandbox*`-аналоги.

---

## 5. Карта gRPC-сервисов T-Invest → реализация в Nautilus

Легенда: ✅ реализовано (базово) · 🔨 доработать в рамках задачи · 🧩 добавить · ➖ не применимо (NOT_APPLICABLE)

### 5.1. UsersService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `GetAccounts` | ✅ | `get_accounts` |
| `GetUserTariff` | ✅ | F8 — реализовано |
| `GetMarginAttributes` | ➖ | справочно, не используется движком |
| `GetInfo` | ➖ | справочно |

### 5.2. InstrumentsService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `Shares / ShareBy` | ✅ | `load_all` / `request_instrument` |
| `Bonds / BondBy` | ✅ | → `Equity` (в Nautilus нет BondInstrument) |
| `Etfs / EtfBy` | ✅ | → `Equity` |
| `Futures / FutureBy` | ✅ | → `FuturesContract` |
| `Options / OptionsBy / OptionBy` | ✅ | → `OptionContract` (🔨 проверить underlying/expiry) |
| `Currencies / CurrencyBy` | ✅ | → `Equity` (кэш) |
| `GetInstrumentBy` | ✅ | F10 — реализовано |
| `TradingSchedules` | ✅ | F11 — реализовано |
| `GetTradingStatuses` | ✅ | F11 — реализовано |
| `GetAccruedInterests` | ✅ | F12 — реализовано |
| `GetDividends` | ➖ | справочно |
| `GetFuturesMargin` | ➖ | справочно |
| `GetAssets / GetBrands` | ➖ | справочно |
| `News / StructuredNotes` | ➖ | не применимо для движка |
| `Indicatives / RiskRates` | ➖ | справочно |

### 5.3. MarketDataService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `GetCandles` | ✅ | `request_candles` (🔨 все `CandleInterval`) |
| `GetLastPrices` | ✅ | `get_last_prices` |
| `GetOrderBook` | ✅ | `request_order_book` |
| `GetTradingStatus` | ✅ | `get_trading_status` |
| `GetLastTrades` | 🧩 | `request_trades` (🔨 проверить объём) |
| `GetClosePrices` | ✅ | `get_close_prices` |
| `GetTechAnalysis` | ✅ | F5 — реализовано |

### 5.4. OrdersService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `PostOrder` | ✅ | рыночные/лимитные |
| `PostOrderAsync` | ✅ | F2 — реализовано |
| `ReplaceOrder` | ✅ | `replace_order` / `_modify_order` |
| `CancelOrder` | ✅ | `cancel_order` / `_cancel_order` |
| `GetOrderState` | ✅ | `get_order_state` |
| `GetOrders` | ✅ | `get_orders` |
| `GetMaxLots` | ✅ | `get_max_lots` |
| `GetOrderPrice` | ✅ | F9 — реализовано |
| `PostOrder` (BESTPRICE) | ✅ | F1 — реализовано |

### 5.5. StopOrdersService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `PostStopOrder` | ✅ | F3 — интегрировано в `_submit_order` (`_submit_stop_order`) |
| `GetStopOrders` | ✅ | `get_stop_orders` |
| `CancelStopOrder` | ✅ | `cancel_stop_order` |

### 5.6. OperationsService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `GetPortfolio` | ✅ | `get_portfolio` |
| `GetPositions` | ✅ | `get_positions` |
| `GetOperations` | ✅ | `get_operations` |
| `GetOperationsByCursor` | ✅ | F6 — реализовано |
| `GetWithdrawLimits` | ✅ | F7 — реализовано |
| `GetBrokerReport` | ➖ | отчёт — вне движка |
| `GetDividendsForeignIssuer` | ➖ | вне движка |
| `PayIn` | ➖ | вне движка (только sandbox) |

### 5.7. SandboxService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `OpenSandboxAccount` | ✅ | `open_sandbox_account` |
| `CloseSandboxAccount` | ✅ | `close_sandbox_account` |
| `SandboxPayIn` | ✅ | `sandbox_pay_in` |
| `PostSandboxOrder` | ✅ | F14 — реализовано |
| `PostSandboxOrderAsync` | ✅ | F14 — реализовано |
| `ReplaceSandboxOrder` | ✅ | F14 — реализовано |
| `CancelSandboxOrder` | ✅ | F14 — реализовано |
| `GetSandboxPortfolio/Positions/Operations/OrderState/Orders/MaxLots/OrderPrice` | ✅ | F14 — реализовано |

### 5.8. MarketDataStreamService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `MarketDataStream` (bidi) | ✅ | `NativeMarketDataStream` |
| `MarketDataServerSideStream` | ✅ | F16 — реализовано |

### 5.9. OrdersStreamService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `TradesStream` | ✅ | макрос native |
| `OrderStateStream` | ✅ | `start_order_state_stream` |

### 5.10. OperationsStreamService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `PortfolioStream` | ✅ | native |
| `PositionsStream` | ✅ | native |
| `OperationsStream` | ✅ | F17 — реализовано |

### 5.11. SignalsService
| Метод | Статус | Примечание |
|-------|--------|-----------|
| `GetStrategies / GetSignals` | ✅ | F15 — стаб реализован (без интеграции в движок; NOT_APPLICABLE) |

---

## 6. Gap-анализ и план доработки

### 6.1. Критические дефекты (обязательны, блокируют merge/push)

| # | Дефект | Файл | Действие |
|---|--------|------|----------|
| D1 | Закоммиченные merge-маркеры | `pyproject.toml`, `python/pyproject.toml` | ✅ Исправлено (коммит `cd6c08263c`: uv `==0.11.33`) |
| D2 | Закоммиченные merge-маркеры (18 шт.) | `docs/integrations/tinvest.md` | ✅ Исправлено (коммит `fa57b7bde6`: выбрана Rust/PyO3 версия) |
| D3 | Сломанные gitlink-записи без `.gitmodules` | индекс `libs/invest-contracts`, `libs/invest-java` | ✅ Исправлено (коммит `8fef7517e4`: gitlinks удалены) |
| D4 | Неотслеживаемые папки `libs/` в рабочем дереве | `libs/` | ✅ Исправлено (коммит `8fef7517e4`: `libs/` в `.gitignore`); также удалён `.envrc`-секрет |

### 6.2. Функциональные доработки (по R3 — «максимум»)

| # | Фича | Сервис | Слой | Описание |
|---|------|--------|------|----------|
| F1 | Тип заявки «лучшая цена» (BESTPRICE) | Orders | execution | ✅ Реализовано (коммит `a8a9762626`) |
| F2 | Асинхронные заявки `PostOrderAsync` | Orders | grpc_client + execution | ✅ Реализовано (коммит `a8a9762626`) |
| F3 | **Стоп-заявки в `_submit_order`** | StopOrders | execution | ✅ Реализовано (коммит `75d4499c46`: `_submit_stop_order`, маппинг StopMarket→StopLoss, StopLimit→StopLimit, MarketIfTouched→TakeProfit) |
| F4 | Замена стоп-заявки | StopOrders | grpc_client | ✅ Реализовано (коммит `75d4499c46`: `replace_stop_order` — отмена+новая, т.к. в контракте нет `ReplaceStopOrder` RPC) |
| F5 | `GetTechAnalysis` | MarketData | data | ✅ Реализовано (коммит `56362a7d5f`) |
| F6 | `GetOperationsByCursor` | Operations | grpc_client | ✅ Реализовано (коммит `a1ceb3f858`) |
| F7 | `GetWithdrawLimits` | Operations | grpc_client | ✅ Реализовано (коммит `a1ceb3f858`) |
| F8 | `GetUserTariff` | Users | grpc_client | ✅ Реализовано (коммит `a1ceb3f858`) |
| F9 | `GetOrderPrice` | Orders | grpc_client | ✅ Реализовано (коммит `a1ceb3f858`) |
| F10 | `GetInstrumentBy` | Instruments | providers | ✅ Реализовано (коммит `1306180d4b`) |
| F11 | `TradingSchedules` + `GetTradingStatuses` | Instruments | providers/data | ✅ Реализовано (коммит `1306180d4b`) |
| F12 | `GetAccruedInterests` | Instruments | providers | ✅ Реализовано (коммит `1306180d4b`) |
| F13 | Полный набор интервалов свечей | MarketData | data | ✅ Реализовано/проверено (коммит `56362a7d5f`) |
| F14 | Sandbox: `PostSandboxOrderAsync`, `ReplaceSandboxOrder`, `CancelSandboxOrder` | Sandbox | sandbox | ✅ Реализовано (коммит `c319cf5035`) |
| F15 | `SignalsService` стаб | Signals | client | ✅ Реализовано (коммиты `c319cf5035`, `90137562d5`: `get_signals` в Python) |
| F16 | `MarketDataServerSideStream` | Stream | stream | ✅ Реализовано (коммит `c319cf5035`) |
| F17 | Обработка `OperationsStream` | OperationsStream | stream | ✅ Реализовано (коммит `c319cf5035`) |

### 6.3. Качество и CI

| # | Работа | Описание |
|---|--------|----------|
| Q1 | Rust: `cargo fmt`, `cargo clippy`, `cargo build` (все фичи) | Код-качество, отсутствие warnings |
| Q2 | Rust unit/pyo3 тесты: `tests/python.rs` | Прогон в CI |
| Q3 | Python unit-тесты `python/tests/unit/adapters/tinvest/*` | Расширить на F1–F17 |
| Q4 | Integration-тесты | Проверить запуск (нужен токен; помечаются `@pytest.mark.skipif`) |
| Q5 | Stubs `.pyi` | Перегенерировать через `python/generate_stubs.py` при изменении публичного API |
| Q6 | CI-рецепт | Убедиться, что `.github/workflows/build.yml` компилирует `nautilus-tinvest` (workspace member — по умолчанию да) |
| Q7 | Docs: `docs/integrations/tinvest.md`, `docs/api_reference/adapters/tinvest.md` | Обновить, убрать маркеры |

---

## 7. Ключевые архитектурные решения (ADR)

### ADR-1. Синхронизация git через merge (без rebase)
- **Контекст**: 94 коммита в `origin/develop`; история `feature-tinvest` содержит один коммит WIP и
  предок от старого `develop`.
- **Решение**: `git checkout develop && git pull --ff-only origin develop`, затем
  `git checkout feature-tinvest && git merge develop` (merge-commit). История не переписывается,
  что безопасно для уже существующей локальной ветки.
- **Альтернатива (отклонена)**: rebase переписывает коммит WIP; риск потери работы при конфликтах выше.

### ADR-2. Rust-core + PyO3, а не чистый Python
- **Контекст**: существующий адаптер уже написан так; паттерн соответствует остальным адаптерам.
- **Решение**: сохранить двухслойную архитектуру; Python-клиент `TInvestGrpcClient` использует
  native-клиент, когда доступен, с fallback на polling (уже реализовано через `_detect_native_streaming`).

### ADR-3. Не включать `libs/` в репозиторий
- **Контекст**: решение заказчика R1; в индексе feature-tinvest ошибочные gitlink-записи.
- **Решение**: удалить из индекса, добавить `libs/` в `.gitignore`. Proto живут только в
  `crates/adapters/tinvest/proto/`. Это делает репозиторий самодостаточным и не зависит от
  `opensource.tbank.ru` при клонировании.

### ADR-4. Bond/ETF/Currency → `Equity` (компромисс)
- **Контекст**: в Nautilus нет `BondInstrument`/`CurrencyInstrument`; модель `Equity` — ближайший аналог.
- **Решение**: представлять облигации, ETF и валюты как `Equity` с `info=raw_dict` (сырые данные
  сохраняются). Поведение уже реализовано; задокументировать и покрыть тестами.

### ADR-5. Signals — NOT_APPLICABLE
- **Контекст**: сервис сигналов — отдельная сущность (аналитические сигналы), не имеет аналога в
  event-модели Nautilus.
- **Решение**: не реализовывать интеграцию; добавить стаб gRPC-клиента (опционально F15) для полноты
  контракта без бизнес-логики. Не блокирует DoD.

### ADR-6. Токен и секреты
- **Контекст**: в `.env` лежит реальный токен (`TINVEST_TOKEN`), `.gitignore` уже исключает `*.env`.
- **Решение**: не коммитить `.env`; в `.env.example` хранить заглушку. Пулл-реквест должен проходить
  проверку на отсутствие секретов (security-аудит).

### ADR-7. Версия uv
- **Контекст**: merge-маркеры в `[tool.uv] required-version` (`==0.11.33` upstream vs `>=0.11.29` stash).
- **Решение**: зафиксировать `==0.11.33` (как upstream) для воспроизводимости; проверить, что `uv.lock`
  совместим.

---

## 8. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Конфликты при merge `develop` → `feature-tinvest` (94 коммита, включая pyproject/uv.lock) | Высокая | Среднее | Merge-коммит, точечное разрешение; D1–D4 исправить в первую очередь |
| Несовпадение локальных proto с актуальными контрактами T-Invest (новые поля/методы) | Средняя | Среднее | Сверить с `libs/invest-contracts` (локальная копия), при необходимости обновить `proto/` |
| gRPC-таймауты/лимиты (GetTechAnalysis, OperationsByCursor — тяжёлые) | Средняя | Среднее | Использовать `with_retry` + deadline; кэширование |
| BESTPRICE/async-заявки могут быть недоступны для части инструментов (опционы — только лимитные) | Средняя | Среднее | Ограничения задокументировать; валидация на уровне клиента |
| Секреты в CI/истории (токен в старых коммитах) | Низкая | Высокое | Не коммитить `.env`; security-аудит перед push |
| Сбой сборки pyo3-модуля из-за Tonic/протobuf версий | Средняя | Среднее | `tonic = 0.13`, `prost = 0.13.5` уже зафиксированы; проверить в CI |
| Отсутствие серверных стримов в песочнице | Низкая | Низкое | Unary-fallback |

---

## 9. План задач (этапы) — передаётся оркестратору

### Этап 0 — Git-синхронизация и починка (блокирующий) — ✅ ВЫПОЛНЕН
- [x] T0.1: `develop` → fast-forward до `origin/develop` (94 коммита). (merge-коммит `1ef66a70da`)
- [x] T0.2: gitlink `libs/...` удалены; `libs/` в `.gitignore`. (`8fef7517e4`)
- [x] T0.3: merge-маркеры pyproject исправлены (uv `==0.11.33`). (`cd6c08263c`)
- [x] T0.4: merge-маркеры `docs/integrations/tinvest.md` исправлены. (`fa57b7bde6`)
- [x] T0.5: Merge `develop` → `feature-tinvest` выполнен. (`1ef66a70da`)

### Этап 1 — Доработка функциональности (исполнение/данные) — ✅ ВЫПОЛНЕН
- [x] T1.1: F1 BESTPRICE + F2 `PostOrderAsync`. (`a8a9762626`)
- [x] T1.2: F3 стоп-заявки в `_submit_order` + F4 замена стоп. (`75d4499c46`)
- [x] T1.3: F5 `GetTechAnalysis` + F13 интервалы свечей. (`56362a7d5f`)
- [x] T1.4: F6/F7/F8/F9. (`a1ceb3f858`)
- [x] T1.5: F10/F11/F12. (`1306180d4b`)
- [x] T1.6: F14 sandbox + F15 signals + F16 server-side стрим + F17 operations stream. (`c319cf5035`, `90137562d5`)

### Этап 2 — Тесты и качество — В ПРОЦЕССЕ (осталось)
- [x] T2.1: Rust fmt + clippy исправления. (`63c9a6ea14`, `90137562d5`)
- [ ] T2.2: Python unit-тесты на F1–F17 — **НЕ написаны** (проверено: grep по `python/tests/unit/adapters/tinvest/` не находит новых фич).
- [ ] T2.3: Перегенерировать `.pyi`-стабы — **не обновлены** (только `__init__.pyi`).
- [ ] T2.4: Обновить документацию (без маркеров) — частично (новые фичи упомянуты в tinvest.md, 20 вхождений).

### Этап 3 — Публикация — ✅ ВЫПОЛНЕН (приёмка: ПРИНЯТО С ОГОВОРКАМИ)
- [x] T3.1: Ревью (reviewer) **PASS**; security-аудит **FAIL → устранено** (реальный `TINVEST_TOKEN` был в истории из `.envrc`, коммит `90561148be`; история переписана `filter-branch`, `git gc --prune=now`, `git log --all -S 'TINVEST_TOKEN'` → пусто). Повторный security-аудит скипнут заказчиком.
- [x] T3.2: Push `feature-tinvest` в `origin` — **УСПЕХ**, хэш `a18b09ae81c83d409497b88aeeb92e3f610ae4e5`; `origin/feature-tinvest` подтверждён `ls-remote`.
- [x] T3.3: Итоговая приёмка director — **ПРИНЯТО С ОГОВОРКАМИ** (DoD 1–5, 7, 9 зелёные).

### Итоговые оговорки (не блокируют, требуют внимания)
1. T2.2–T2.4 **отложены**: Python unit-тесты F6–F17, `.pyi`-стабы, финализация `docs/integrations/tinvest.md` — не прогонялись/не доделаны (причина: конфликт v1/v2 резолва пакета при запуске pytest; по решению заказчика этап T2 отложен).
2. **ОБЯЗАТЕЛЬНО: ротация T-Invest токена** — был скомпрометирован коммитом `90561148be`; отозвать и перевыпустить в кабинете T-Invest.
3. Повторный security-аудит не проводился (скипнут заказчиком).
4. Remote переключён HTTPS→SSH (`git@github.com:LimonTH/nautilus_trader_ru.git`); при необходимости вернуть HTTPS.
5. АД [`tinvest-full-integration.md`](docs/architecture/tinvest-full-integration.md) не закоммичен (внутренний документ).

---

## 10. Открытые вопросы (эскалация к director при необходимости)

1. Нужна ли реальная интеграция `GetTechAnalysis` (F5) или достаточно штатных индикаторов Nautilus?
   *(рекомендация: штатные индикаторы, F5 — опционально)*
2. Подтвердить выбор `required-version = "==0.11.33"` для uv (ADR-7).
3. Имя целевой ветки на GitHub — `feature-tinvest` (по R2) или создать `feature/tinvest-full-integration`?
