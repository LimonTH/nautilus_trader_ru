# Архитектурный документ: доведение адаптера T-Invest до эталонного качества

> **Версия:** 1.0  
> **Дата:** 2026-07-14  
> **Ветка:** [`feature-tinvest`](https://github.com/nautechsystems/nautilus_trader/tree/feature-tinvest)  
> **Исполнитель:** 🏗️ Architect  
> **Заказчик:** 👑 Director (ТЗ от 2026-07-14)

---

## 1. Цель

Довести адаптер [`T-Invest`](nautilus_trader/adapters/tinvest/__init__.py) до полного паритета с эталонными адаптерами NautilusTrader ([`OKX`](nautilus_trader/adapters/okx/__init__.py), [`dYdX`](nautilus_trader/adapters/dydx/__init__.py), [`Polymarket`](nautilus_trader/adapters/polymarket/__init__.py)) по:

- **Тестированию** — 100% покрытие unit-тестами всех Python-модулей адаптера
- **Примерам** — наличие `data_tester.py` и `exec_tester.py`
- **Архитектурной целостности** — устранение выявленных пробелов и неполнот
- **Documentation** — актуализация документации

## 2. Текущая архитектура

### 2.1. Компонентная схема

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Python Layer                                  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │  config.py   │  │  common.py   │  │     providers.py          │  │
│  │  (141 стр.)  │  │  (22 стр.)   │  │     (573 стр.)            │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────────┘  │
│         │                 │                      │                  │
│  ┌──────┴─────────────────┴──────────────────────┴───────────────┐  │
│  │                     factories.py (120 стр.)                    │  │
│  │   TInvestLiveDataClientFactory / TInvestLiveExecClientFactory  │  │
│  └──────┬──────────────────────────────────┬─────────────────────┘  │
│         │                                  │                        │
│  ┌──────┴──────────────┐   ┌───────────────┴────────────────────┐  │
│  │    data.py          │   │       execution.py                  │  │
│  │  (1007 стр.)        │   │      (1278 стр.)                    │  │
│  │  TInvestDataClient   │   │  TInvestExecutionClient             │  │
│  └──────────┬──────────┘   └───────────────┬────────────────────┘  │
│             │                              │                        │
│  ┌──────────┴──────────────────────────────┴────────────────────┐  │
│  │                   grpc_client.py (1624 стр.)                  │  │
│  │          TInvestGrpcClient (Python wrapper over PyO3)         │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │ PyO3 FFI
┌─────────────────────────────┼───────────────────────────────────────┐
│                     Rust Layer (nautilus_pyo3)                       │
│                                                                     │
│  ┌──────────────────────────┴───────────────────────────────────┐   │
│  │          crates/adapters/tinvest/                              │   │
│  │  ├── src/client.rs          (gRPC client core)                │   │
│  │  ├── src/config.rs          (Rust config ↔ Python config)     │   │
│  │  ├── src/enums.rs           (T-Invest enums)                  │   │
│  │  ├── src/factories.rs       (Client factories)                │   │
│  │  ├── src/common/convert.rs  (Price/instrument conversion)     │   │
│  │  ├── src/common/types.rs    (Shared types)                    │   │
│  │  ├── src/data/core.rs       (Market data service client)      │   │
│  │  ├── src/execution/core.rs  (Orders/operations service)       │   │
│  │  ├── src/providers/instruments.rs (Instrument loading)        │   │
│  │  ├── src/stream/core.rs     (gRPC streaming infrastructure)   │   │
│  │  ├── src/stream/native.rs   (Native stream bindings)          │   │
│  │  ├── src/sandbox/core.rs    (Sandbox operations)              │   │
│  │  ├── src/python/            (PyO3 Python bindings)            │   │
│  │  │   ├── config.rs                                           │   │
│  │  │   ├── factories.rs                                        │   │
│  │  │   ├── stream.rs                                           │   │
│  │  │   └── mod.rs                                              │   │
│  │  └── tests/python.rs        (Rust-side integration test)     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │ gRPC (tonic)
┌─────────────────────────────┼───────────────────────────────────────┐
│                     T-Invest API (T-Bank)                             │
│  invest-public-api.tbank.ru:443 / sandbox-invest-public-api.tbank.ru │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2. Потоки данных

#### Market Data (data.py)
```
T-Invest API ──gRPC──► TInvestGrpcClient ──► TInvestDataClient
                            │                       │
                    ┌───────┴───────┐        ┌──────┴──────────────┐
                    │ Native Stream │        │ Polling Fallback    │
                    │ (PyO3→asyncio │        │ (REST request_* +   │
                    │  Queue)        │        │  500-1000ms poll)   │
                    └───────┬───────┘        └──────┬──────────────┘
                            │                       │
                            └───────────┬───────────┘
                                        │
                          ┌─────────────┴──────────────┐
                          │ _process_native_stream_data │
                          │ _on_order_book              │
                          │ _on_quote_tick              │
                          │ _on_trade_tick              │
                          │ _on_bar                     │
                          └─────────────┬──────────────┘
                                        │
                          ┌─────────────┴──────────────┐
                          │    _handle_data(tick/snap)  │
                          │    → DataEngine             │
                          └────────────────────────────┘
```

#### Execution (execution.py)
```
Strategy ──► SubmitOrder ──► TInvestExecutionClient ──► TInvestGrpcClient
                                      │                        │
                              ┌───────┴────────┐      ┌────────┴──────────┐
                              │ post_order     │      │ post_order_async  │
                              │ (sync wait)    │      │ (fire-and-forget) │
                              └───────┬────────┘      └────────┬──────────┘
                                      │                        │
                              ┌───────┴────────────────────────┴──────────┐
                              │         T-Invest Orders Service           │
                              └────────────────────┬──────────────────────┘
                                                   │
                              ┌────────────────────┴──────────────────────┐
                              │  Native Streams:                          │
                              │  TInvestOrderStateStream                  │
                              │  TInvestPortfolioStream                   │
                              │  TInvestPositionsStream                   │
                              └────────────────────┬──────────────────────┘
                                                   │
                              ┌────────────────────┴──────────────────────┐
                              │  generate_order_* / generate_fill_*       │
                              │  → ExecutionEngine                        │
                              └───────────────────────────────────────────┘
```

### 2.3. Общий gRPC-клиент (синглтон)

[`factories.py`](nautilus_trader/adapters/tinvest/factories.py:39) реализует синглтон `_shared_grpc_client` через `get_shared_grpc_client()`. Это предотвращает открытие двух TCP-соединений к T-Invest API.

**Риск:** потенциальное состояние гонки при одновременной инициализации data + exec клиентов.

### 2.4. Native-стриминг vs Polling

Адаптер имеет двойной режим работы:

| Подсистема | Native Stream (PyO3) | Polling Fallback |
|------------|---------------------|------------------|
| OrderBook  | `TInvestMarketDataStream` | `request_order_book()` каждые 500ms |
| Trades     | `TInvestMarketDataStream` | `request_trades()` каждые 1000ms |
| Candles    | `TInvestMarketDataStream` | `request_candles()` каждые 60-300s |
| Orders     | `TInvestOrderStateStream` | `get_order_state()` по запросу |
| Portfolio  | `TInvestPortfolioStream` | `get_portfolio()` по запросу |
| Positions  | `TInvestPositionsStream` | `get_positions()` по запросу |

## 3. Gap-анализ: выявленные пробелы

### 3.1. Критические (блокируют production-использование)

| # | Проблема | Файл | Строки | Описание | Приоритет |
|---|----------|------|--------|----------|-----------|
| G1 | Нет unit-тестов | `tests/unit_tests/adapters/tinvest/` | — | 0 тестовых файлов. Без тестов адаптер не может считаться стабильным. | 🔴 P0 |
| G2 | Нет примеров | `python/examples/tinvest/` | — | Нет `data_tester.py` и `exec_tester.py`. Пользователи не знают, как запустить адаптер. | 🔴 P0 |
| G3 | Пустые методы подписки | [`data.py`](nautilus_trader/adapters/tinvest/data.py:244) | 244–258 | `_subscribe_instruments`, `_subscribe_instrument`, `_unsubscribe_instruments`, `_unsubscribe_instrument` — пустые no-op. | 🟡 P1 |
| G4 | Historical data request не реализован | [`data.py`](nautilus_trader/adapters/tinvest/data.py) | — | Нет методов `_request_bars`, `_request_order_book_snapshot`, `_request_trade_ticks`, `_request_quote_ticks`. Без них backtest и исторические данные недоступны. | 🟡 P1 |

### 3.2. Существенные (ограничивают функциональность)

| # | Проблема | Файл | Строки | Описание | Приоритет |
|---|----------|------|--------|----------|-----------|
| G5 | Нет `constants.py` | — | — | Константы (маппинги, enums) инлайн в коде. Это затрудняет тестирование и поддержку. | 🟡 P1 |
| G6 | Нет `types.py` | — | — | Отсутствуют type aliases для T-Invest-specific типов. | 🟢 P2 |
| G7 | Нет fee model | — | — | Отсутствует модель комиссий (T-Invest commission structure). | 🟢 P2 |
| G8 | Нет `_subscribe_instrument_status` | [`data.py`](nautilus_trader/adapters/tinvest/data.py:393) | 393–397 | Пустой метод. Trading status не отслеживается. | 🟢 P2 |
| G9 | Нет `_subscribe_instrument_close` | [`data.py`](nautilus_trader/adapters/tinvest/data.py:399) | 399–402 | Пустой метод. | 🟢 P2 |
| G10 | OrderBookDelta не поддерживается | [`data.py`](nautilus_trader/adapters/tinvest/data.py:253) | 253–258 | T-Invest не предоставляет дельты стакана — только снепшоты. Документировано, но нет fallback-эмуляции. | 🟢 P2 |

### 3.3. Качество кода

| # | Проблема | Файл | Описание | Приоритет |
|---|----------|------|----------|-----------|
| G11 | TODO в native-стриминге | [`grpc_client.py`](nautilus_trader/adapters/tinvest/grpc_client.py:416) | `subscribe_order_book`, `subscribe_trades`, `subscribe_candles` имеют TODO-комментарии о неготовности PyO3-wiring. | 🟡 P1 |
| G12 | Синглтон gRPC-клиента | [`factories.py`](nautilus_trader/adapters/tinvest/factories.py:39) | Модульный глобальный синглтон. При тестировании нужно сбрасывать состояние. | 🟢 P2 |
| G13 | Несогласованность типов данных | [`data.py`](nautilus_trader/adapters/tinvest/data.py:793) | `_on_trade_tick` принимает `list[dict]`, но native stream передаёт одиночный dict. Потенциальный баг. | 🟡 P1 |

### 3.4. Документация

| # | Проблема | Файл | Описание | Приоритет |
|---|----------|------|----------|-----------|
| G14 | Документация не отражает текущее состояние | [`docs/integrations/tinvest.md`](docs/integrations/tinvest.md) | Документация описывает идеальное состояние, а не реальное (напр., упоминает `TInvestSandboxExecutionClient`, которого нет в Python-слое). | 🟢 P2 |

## 4. Архитектура тестов

### 4.1. Стратегия тестирования

```
Уровень 1: Unit-тесты (pytest + unittest.mock)
  ├── test_config.py         — тесты конфигурационных классов
  ├── test_common.py         — тесты констант и хелперов
  ├── test_providers.py      — тесты инструмент-провайдера и парсинга
  ├── test_data.py           — тесты дата-клиента (подписки, колбэки)
  ├── test_execution.py      — тесты execution-клиента (ордера, филлы)
  ├── test_factories.py      — тесты фабрик
  └── test_grpc_client.py    — тесты gRPC-обёртки

Уровень 2: Интеграционные тесты (Rust side)
  └── crates/adapters/tinvest/tests/  — уже существуют

Уровень 3: Примеры (ручной запуск)
  ├── python/examples/tinvest/data_tester.py
  └── python/examples/tinvest/exec_tester.py
```

### 4.2. Подход к мокированию

Поскольку T-Invest API недоступен в CI, все Python-тесты используют моки:

```
Тестируемый класс
       │
       ├── self._client ──► MagicMock (TInvestGrpcClient)
       │   ├── .connect()           → AsyncMock
       │   ├── .request_instruments() → AsyncMock → list[dict]
       │   ├── .post_order()        → AsyncMock → dict
       │   ├── .get_portfolio()     → AsyncMock → dict
       │   └── ...                  → AsyncMock
       │
       ├── self._cache ──► MagicMock (Cache)
       │   ├── .instrument()        → возвращает мок-инструмент
       │   └── .add_instrument()    → no-op
       │
       ├── self._msgbus ──► MagicMock (MessageBus)
       │   └── .send()              → no-op
       │
       └── self._clock ──► MagicMock (LiveClock)
           └── .timestamp_ns()      → 0 (фиксировано)
```

### 4.3. Фикстуры и фабрики

Следуя паттерну [`dYdX`](tests/unit_tests/adapters/dydx/test_data.py), каждый тестовый модуль содержит:

```python
# Фабрика для создания минимального тестового клиента
def make_data_client(*, client=None, cache=None, clock=None, ...) -> TInvestDataClient:
    ...

# Фикстуры для типовых тестовых данных
@pytest.fixture
def sample_instrument_dict() -> dict:
    return {"figi": "BBG004730N88", "ticker": "SBER", "instrument_type": "share", ...}

@pytest.fixture
def sample_order_book_dict() -> dict:
    return {"bids": [...], "asks": [...]}
```

### 4.4. Структура тестовых файлов

#### [`test_config.py`](tests/unit_tests/adapters/tinvest/test_config.py)
- `TestTInvestClientConfig`:
  - `test_default_values`
  - `test_effective_target_sandbox`
  - `test_effective_target_production`
  - `test_to_pyo3`
- `TestTInvestDataClientConfig`:
  - `test_minimal_config`
  - `test_with_update_interval`
- `TestTInvestExecClientConfig`:
  - `test_defaults`
  - `test_use_bestprice_orders`
  - `test_use_async_orders`

#### [`test_common.py`](tests/unit_tests/adapters/tinvest/test_common.py)
- `test_constants_defined`
- `test_venue_value`

#### [`test_providers.py`](tests/unit_tests/adapters/tinvest/test_providers.py)
- `TestComputePricePrecision`:
  - `test_none_input`
  - `test_zero_increment`
  - `test_rubles_step`
  - `test_copecks_step`
  - `test_small_nano_increment`
- `TestTryDictToInstrument`:
  - `test_share_conversion`
  - `test_etf_conversion`
  - `test_bond_conversion`
  - `test_future_conversion`
  - `test_currency_conversion`
  - `test_option_with_direction_call`
  - `test_option_with_direction_put`
  - `test_unknown_type_defaults_to_equity`
  - `test_missing_figi_returns_none`
  - `test_conversion_exception_returns_none`
- `TestTInvestInstrumentProvider`:
  - `test_load_all_with_grpc_client`
  - `test_load_all_without_grpc_client`
  - `test_load_all_already_loaded`
  - `test_load_ids`
  - `test_find_instrument_by_figi`
  - `test_find_instrument_by_ticker`
  - `test_get_instruments`

#### [`test_data.py`](tests/unit_tests/adapters/tinvest/test_data.py)
- `TestTInvestDataClientConnection`:
  - `test_connect_loads_instruments`
  - `test_connect_starts_native_stream_when_available`
  - `test_connect_falls_back_to_polling`
  - `test_disconnect_stops_streams_and_tasks`
- `TestSubscriptions`:
  - `test_subscribe_order_book_native`
  - `test_subscribe_order_book_polling`
  - `test_subscribe_quote_ticks`
  - `test_subscribe_trade_ticks`
  - `test_subscribe_bars`
- `TestCallbacks`:
  - `test_on_order_book_valid_data`
  - `test_on_order_book_missing_instrument`
  - `test_on_quote_tick_valid_data`
  - `test_on_quote_tick_empty_book`
  - `test_on_trade_tick_valid_data`
  - `test_on_trade_tick_empty_data`
  - `test_on_bar_valid_data`
- `TestNativeStreamProcessing`:
  - `test_process_native_trade`
  - `test_process_native_orderbook`
  - `test_process_native_candle`
  - `test_unknown_payload_type_ignored`
  - `test_missing_figi_ignored`

#### [`test_execution.py`](tests/unit_tests/adapters/tinvest/test_execution.py)
- `TestOrderSubmission`:
  - `test_submit_limit_order`
  - `test_submit_market_order`
  - `test_submit_bestprice_order`
  - `test_submit_stop_market_order` (F3)
  - `test_submit_stop_limit_order` (F3)
  - `test_submit_market_if_touched` (F3)
  - `test_submit_limit_if_touched` (F3)
  - `test_submit_order_rejected_on_exception`
- `TestOrderModification`:
  - `test_modify_order_success`
  - `test_modify_order_zero_quantity`
- `TestOrderCancellation`:
  - `test_cancel_order_success`
  - `test_cancel_order_failure`
  - `test_cancel_all_orders`
- `TestReportGeneration`:
  - `test_generate_order_status_report`
  - `test_generate_order_status_reports`
  - `test_generate_fill_reports`
  - `test_generate_position_status_reports`
  - `test_generate_mass_status`
- `TestAccountState`:
  - `test_update_account_state`
  - `test_query_account`
- `TestOptionHandling`:
  - `test_is_option_instrument`
  - `test_map_order_type_forces_limit_for_options`
- `TestNativeStreams`:
  - `test_start_native_streams`
  - `test_stop_native_streams`

#### [`test_factories.py`](tests/unit_tests/adapters/tinvest/test_factories.py)
- `TestSharedGrpcClient`:
  - `test_singleton_returns_same_instance`
  - `test_creates_client_on_first_call`
- `TestTInvestLiveDataClientFactory`:
  - `test_create_returns_data_client`
- `TestTInvestLiveExecClientFactory`:
  - `test_create_returns_exec_client`
  - `test_create_with_default_account_id`

#### [`test_grpc_client.py`](tests/unit_tests/adapters/tinvest/test_grpc_client.py)
- `TestTInvestGrpcClientInit`:
  - `test_create_with_config`
  - `test_native_streaming_detection`
- `TestConnection`:
  - `test_connect_with_native_client`
  - `test_connect_without_native_client`
  - `test_disconnect_cancels_polling_tasks`
- `TestDataMethods`:
  - `test_request_instruments_returns_list`
  - `test_request_instruments_without_native`
  - `test_request_order_book`
  - `test_request_trades`
  - `test_request_candles`
- `TestPolling`:
  - `test_start_polling_creates_task`
  - `test_stop_polling_cancels_task`
  - `test_duplicate_polling_prevented`
- `TestSubscriptions`:
  - `test_subscribe_order_book_polling`
  - `test_unsubscribe_order_book`
  - `test_subscribe_trades_polling`
  - `test_subscribe_candles_polling`
- `TestExecutionMethods`:
  - `test_post_order`
  - `test_post_order_async`
  - `test_cancel_order`
  - `test_get_orders`
  - `test_get_positions`
  - `test_get_portfolio`

### 4.5. Запуск тестов

```bash
# Все тесты адаптера
pytest tests/unit_tests/adapters/tinvest/ -v

# Конкретный модуль
pytest tests/unit_tests/adapters/tinvest/test_providers.py -v

# С coverage
pytest tests/unit_tests/adapters/tinvest/ --cov=nautilus_trader.adapters.tinvest -v
```

## 5. Архитектура примеров

### 5.1. [`data_tester.py`](python/examples/tinvest/data_tester.py)

Следуя паттерну [`okx/data_tester.py`](python/examples/okx/data_tester.py):

```python
"""
T-Invest data tester example.

Builds a live node with TInvestDataClient and attaches the built-in
DataTester actor. Pass --run to connect and start subscriptions.
"""
```

Аргументы командной строки:
- `--sandbox` / `--production` — выбор окружения
- `--instrument` — FIGI инструмента (по умолчанию: `BBG004730N88.TINVEST` — SBER)
- `--trader-id` — ID трейдера
- `--run` — фактическое подключение

### 5.2. [`exec_tester.py`](python/examples/tinvest/exec_tester.py)

Следуя паттерну [`okx/exec_tester.py`](python/examples/okx/exec_tester.py):

```python
"""
T-Invest execution tester example.

Builds a live node with TInvestDataClient + TInvestExecutionClient
and attaches the ExecTester strategy. Pass --run to connect.
Pass --live-orders only when the account is funded.
"""
```

Аргументы командной строки:
- `--sandbox` / `--production`
- `--instrument` — FIGI
- `--account-id` — ID счёта
- `--quantity` — количество лотов
- `--run` — подключение
- `--live-orders` — реальные ордера (только sandbox!)

## 6. План улучшений кода

### 6.1. Критические исправления (P0-P1)

| ID | Действие | Файл |
|----|----------|------|
| F1 | Реализовать `_request_bars` — запрос исторических баров через `request_candles` с параметрами `from_ts`/`to_ts` из DataRequest | [`data.py`](nautilus_trader/adapters/tinvest/data.py) |
| F2 | Реализовать `_request_order_book_snapshot` — запрос снепшота стакана | [`data.py`](nautilus_trader/adapters/tinvest/data.py) |
| F3 | Реализовать `_request_trade_ticks` — запрос исторических трейдов | [`data.py`](nautilus_trader/adapters/tinvest/data.py) |
| F4 | Исправить `_on_trade_tick` — принимать как `list[dict]`, так и одиночный `dict` | [`data.py`](nautilus_trader/adapters/tinvest/data.py:793) |
| F5 | Реализовать `_subscribe_instruments`/`_subscribe_instrument` — как минимум с логированием | [`data.py`](nautilus_trader/adapters/tinvest/data.py:244) |
| F6 | Выделить константы в [`constants.py`](nautilus_trader/adapters/tinvest/constants.py) | Новый файл |
| F7 | Добавить docstring к `generate_order_status_report` и уточнить тип параметра `command` | [`execution.py`](nautilus_trader/adapters/tinvest/execution.py:336) |

### 6.2. Второстепенные улучшения (P2)

| ID | Действие |
|----|----------|
| F8 | Реализовать `_subscribe_instrument_status` через `TradingStatuses` API |
| F9 | Добавить `TInvestFeeModel` для учёта комиссий |
| F10 | Обновить документацию [`tinvest.md`](docs/integrations/tinvest.md) — синхронизировать с реальным состоянием |
| F11 | Добавить `types.py` с type aliases |

### 6.3. Не входят в текущий объём (Out of Scope)

- Переписывание Rust-крейта
- Реализация `TInvestSandboxExecutionClient` в Python-слое (документирован, но не реализован как отдельный класс)
- End-to-end тесты с реальным T-Invest API

## 7. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Отсутствие T-Invest API в CI | Высокая | Среднее | Все тесты используют моки; интеграционные тесты — опциональны |
| Гонка в синглтоне `_shared_grpc_client` | Низкая | Высокое | Добавить `asyncio.Lock` в `get_shared_grpc_client()` |
| Несовместимость с новыми версиями T-Invest API | Средняя | Высокое | Документировать версию API в тестах |
| PyO3-биндинги не собраны в CI | Средняя | Среднее | Тесты должны работать с `_HAS_NATIVE_STREAM_CLASS = False` |
| Разрыв между документацией и кодом | Высокая | Низкое | Актуализация документации в рамках задачи |

## 8. План задач для оркестратора

### Этап 1: Подготовка инфраструктуры тестирования

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T1 | Создать `tests/unit_tests/adapters/tinvest/__init__.py` и `conftest.py` с фикстурами | 🗄️ Backend | — |
| T2 | Создать `tests/unit_tests/adapters/tinvest/test_config.py` | 🗄️ Backend | T1 |
| T3 | Создать `tests/unit_tests/adapters/tinvest/test_common.py` | 🗄️ Backend | T1 |

### Этап 2: Тестирование providers и конвертации

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T4 | Создать `tests/unit_tests/adapters/tinvest/test_providers.py` — тесты `_compute_price_precision` | 🗄️ Backend | T1 |
| T5 | Дописать `test_providers.py` — тесты `_try_dict_to_instrument` для всех типов | 🗄️ Backend | T4 |
| T6 | Дописать `test_providers.py` — тесты `TInvestInstrumentProvider` | 🗄️ Backend | T5 |

### Этап 3: Тестирование data client

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T7 | Создать `tests/unit_tests/adapters/tinvest/test_data.py` — тесты connection/disconnection | 🗄️ Backend | T1 |
| T8 | Дописать `test_data.py` — тесты колбэков (`_on_order_book`, `_on_quote_tick`, `_on_trade_tick`, `_on_bar`) | 🗄️ Backend | T7 |
| T9 | Дописать `test_data.py` — тесты native stream processing | 🗄️ Backend | T8 |

### Этап 4: Тестирование execution client

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T10 | Создать `tests/unit_tests/adapters/tinvest/test_execution.py` — тесты ордеров | 🗄️ Backend | T1 |
| T11 | Дописать `test_execution.py` — тесты report generation | 🗄️ Backend | T10 |
| T12 | Дописать `test_execution.py` — тесты account state и native streams | 🗄️ Backend | T11 |

### Этап 5: Тестирование factories и grpc_client

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T13 | Создать `tests/unit_tests/adapters/tinvest/test_factories.py` | 🗄️ Backend | T1 |
| T14 | Создать `tests/unit_tests/adapters/tinvest/test_grpc_client.py` | 🗄️ Backend | T1 |

### Этап 6: Примеры

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T15 | Создать `python/examples/tinvest/__init__.py` и `data_tester.py` | 🎨 Frontend | — |
| T16 | Создать `python/examples/tinvest/exec_tester.py` | 🎨 Frontend | T15 |

### Этап 7: Устранение архитектурных пробелов (опционально, P1-P2)

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T17 | Реализовать `_request_bars`, `_request_order_book_snapshot`, `_request_trade_ticks` | 🗄️ Backend | — |
| T18 | Выделить константы в `constants.py` | 🗄️ Backend | — |
| T19 | Исправить `_on_trade_tick` для обработки одиночного dict | 🗄️ Backend | — |
| T20 | Актуализировать `docs/integrations/tinvest.md` | 📄 Docs | T17-T19 |

### Этап 8: Проверка качества

| # | Задача | Исполнитель | Зависимости |
|---|--------|-------------|-------------|
| T21 | Прогнать все тесты, проверить coverage | 🧪 Tester | T1–T14 |
| T22 | Код-ревью всех изменений | 🕵️ Reviewer | T1–T20 |
| T23 | Финальный аудит | 🧾 Auditor | T21, T22 |

## 9. Ожидаемый результат

После выполнения всех задач:

```
✅ tests/unit_tests/adapters/tinvest/
   ├── __init__.py
   ├── conftest.py
   ├── test_config.py          (~15 тестов)
   ├── test_common.py           (~3 теста)
   ├── test_providers.py       (~20 тестов)
   ├── test_data.py            (~25 тестов)
   ├── test_execution.py       (~25 тестов)
   ├── test_factories.py        (~5 тестов)
   └── test_grpc_client.py     (~20 тестов)
                                ─────────
                                ~113 тестов

✅ python/examples/tinvest/
   ├── __init__.py
   ├── data_tester.py
   └── exec_tester.py

✅ nautilus_trader/adapters/tinvest/constants.py   (опционально)
✅ Все тесты проходят: pytest tests/unit_tests/adapters/tinvest/ -v
✅ Coverage > 80% для nautilus_trader.adapters.tinvest
✅ Документация актуализирована
```

---

*Документ подготовлен 🏗️ Architect для передачи 🪃 Orchestrator.*
