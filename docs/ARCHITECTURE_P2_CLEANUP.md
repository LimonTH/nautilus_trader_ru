# Архитектурный документ: P2 Cleanup адаптера T-Invest

## 1. Контекст

Директором сформулированы 6 неблокирующих рекомендаций (P2) по улучшению кодовой базы
адаптера [`nautilus_trader/adapters/tinvest/`](nautilus_trader/adapters/tinvest/__init__.py).
Все изменения — атомарные, низкорисковые, не затрагивают бизнес-логику.

**Ветка:** `feature-tinvest`

---

## 2. Список изменений

### 2.1. Убрать dead code в [`data.py`](nautilus_trader/adapters/tinvest/data.py:695)

**Проблема:** На строках 695–696 условные выражения `if instrument else 2` и
`if instrument else 0` недостижимы, потому что на строке 691–693 уже выполнен
early return при `instrument is None`.

**Текущий код (строки 689–696):**
```python
instrument = self._cache.instrument(instrument_id)
if instrument is None:
    self._log.debug(f"Instrument {instrument_id} not in cache for order book")
    return

price_precision = instrument.price_precision if instrument else 2   # dead: instrument never None
size_precision = instrument.size_precision if instrument else 0     # dead: instrument never None
```

**Целевой код:**
```python
instrument = self._cache.instrument(instrument_id)
if instrument is None:
    self._log.debug(f"Instrument {instrument_id} not in cache for order book")
    return

price_precision = instrument.price_precision
size_precision = instrument.size_precision
```

**Обоснование:** Dead code вводит в заблуждение (читатель думает, что `None` возможен
ниже по коду). После early return ветка `else` никогда не выполняется — статический
анализатор (mypy/pyright) также подтвердит, что `instrument` не `None`.

**Риск:** Нулевой. Поведение не меняется.

---

### 2.2. Заменить [`asyncio.create_task`](nautilus_trader/adapters/tinvest/execution.py:1087) на `self.create_task`

**Проблема:** На строке 1087 используется `asyncio.create_task(...)` — «fire-and-forget»
без обработки ошибок. Если корутина `_update_account_state()` выбросит исключение,
оно будет поглощено event loop без логирования.

Базовый класс [`ExecutionClient`](nautilus_trader/live/execution_client.py:157) предоставляет
метод [`create_task()`](nautilus_trader/live/execution_client.py:157) с:
- Автоматическим логированием ошибок через `_on_task_completed`
- Добавлением задачи в `self._tasks` (для корректной отмены при остановке)
- Опциональными callback-действиями

**Текущий код (строка 1087):**
```python
asyncio.create_task(self._update_account_state())
```

**Целевой код:**
```python
self.create_task(self._update_account_state())
```

**Обоснование:** Единообразный подход к созданию задач. Ошибки в
`_update_account_state()` будут залогированы, а не потеряны.

**Риск:** Нулевой. `self.create_task` вызывает `self._loop.create_task` (тот же
event loop), но добавляет done-callback для обработки ошибок.

**Дополнительное наблюдение:** В том же файле на строках 852–854 есть ещё три
вызова `asyncio.create_task` в методе `_start_native_streams`. Они используют иной
паттерн — ручное сохранение в `self._native_stream_tasks` для последующей отмены
в `_stop_native_streams`. Замена этих вызовов на `self.create_task` **не**
рекомендуется в рамках данной задачи, т.к.:
1. Задачи хранятся в выделенном списке `_native_stream_tasks` для каскадной отмены
2. `self.create_task` добавляет задачи в `self._tasks` — возникнет двойное хранение
3. Требуется дополнительный анализ влияния на логику остановки стримов

---

### 2.3. Привести моки в [`test_execution.py`](tests/unit_tests/adapters/tinvest/test_execution.py:67) к реальному API

**Проблема:** Моки в `_make_mock_order` используют метод `as_f64()` для Price/Quantity,
но реальный API Nautilus использует метод `as_double()`. Это подтверждается кодом
[`execution.py:490`](nautilus_trader/adapters/tinvest/execution.py:490):
```python
price = float(command.order.price.as_double())
```

Текущие моки (строки 67–86) создают фиктивный метод `as_f64`, которого нет
в реальных объектах `Price` / `Quantity`. Тесты проходят только потому, что
MagicMock принимает любые атрибуты.

**Затрагиваемые строки (67–86):**
```python
# Строка 67: комментарий
# Строки 75–80: _pm.as_f64 вместо _pm.as_double
# Строки 82–86: _tpm.as_f64 вместо _tpm.as_double
```

**Целевой код:**
- `as_f64` → `as_double` во всех местах (строки 67, 77, 79, 80, 83, 85, 86)
- Комментарий на строке 67: `as_f64()` → `as_double()`

**Обоснование:** Моки должны соответствовать реальному API. Это снижает риск
ложноположительных тестов (тесты проходят с неверным API, но реальный код
использует другой метод).

**Риск:** Низкий. Тесты продолжат проходить, т.к. меняется только имя метода на MagicMock.

---

### 2.4. Исправить [`conftest.py:160`](tests/unit_tests/adapters/tinvest/conftest.py:160) — `get_instruments` должен возвращать `dict`

**Проблема:** Фабрика `make_mock_instrument_provider()` на строке 160 возвращает
`[]` (list) для `get_instruments`. Реальный метод
[`TInvestInstrumentProvider.get_instruments()`](nautilus_trader/adapters/tinvest/providers.py:487)
возвращает `dict[str, object]`.

**Текущий код (строка 160):**
```python
provider.get_instruments = MagicMock(return_value=[])
```

**Целевой код:**
```python
provider.get_instruments = MagicMock(return_value={})
```

**Обоснование:** Если какой-либо тест начнёт итерироваться по результату
`get_instruments()` (ожидая `.items()`, `.keys()`), он сломается с list вместо dict.
Возврат корректного типа предотвращает будущие ошибки.

**Риск:** Низкий. Текущие тесты не используют `get_instruments()` → изменений
в поведении тестов нет.

---

### 2.5. Добавить [`TInvestGrpcClient`](nautilus_trader/adapters/tinvest/__init__.py:22) в `__all__`

**Проблема:** [`TInvestGrpcClient`](nautilus_trader/adapters/tinvest/grpc_client.py) импортируется
на строке 22, но отсутствует в `__all__` (строки 40–57). Это публичный класс
(упомянут в документации, используется в примерах), который должен быть доступен
через `from nautilus_trader.adapters.tinvest import TInvestGrpcClient`.

**Текущий код (строки 40–57):**
```python
__all__ = [
    "TINVEST",
    ...
    "TInvestLiveExecClientFactory",
    "TInvestMarketDataStream",
    ...
]
```

**Целевой код:** Добавить `"TInvestGrpcClient"` в список `__all__` (в алфавитном
порядке — между `"TInvestExecClientConfig"` и `"TInvestExecutionClient"`).

**Обоснование:** Соответствие документации и публичному API. Отсутствие в `__all__`
не блокирует импорт (`import *` всё равно работает из-за явного импорта на строке 22),
но нарушает контракт и вводит в заблуждение tooling (лингеры, IDE).

**Риск:** Нулевой.

---

### 2.6. Обновить таблицу тестов в [`docs/integrations/tinvest.md`](docs/integrations/tinvest.md:685)

**Проблема:** Строка 685 утверждает «193 unit tests», но `pytest --collect-only`
насчитывает **274** теста:

```
$ pytest tests/unit_tests/adapters/tinvest/ --collect-only -q
274 tests collected in 0.25s
```

**Текущий код (строка 685):**
```markdown
The adapter is covered by 193 unit tests under
```

**Целевой код:**
```markdown
The adapter is covered by 274 unit tests under
```

**Обоснование:** Документация должна отражать актуальное состояние.

**Риск:** Нулевой.

---

## 3. Потоки данных и зависимости

Изменения не затрагивают потоки данных. Все правки — синтаксические/косметические:

```
┌─────────────────────────────────────────────────────────┐
│  Изменяемые файлы (6)                                   │
│                                                         │
│  nautilus_trader/adapters/tinvest/                      │
│  ├── data.py              ← #1 dead code                │
│  ├── execution.py          ← #2 create_task              │
│  └── __init__.py           ← #5 __all__                  │
│                                                         │
│  tests/unit_tests/adapters/tinvest/                     │
│  ├── test_execution.py     ← #3 as_f64 → as_double      │
│  └── conftest.py           ← #4 list → dict             │
│                                                         │
│  docs/integrations/                                     │
│  └── tinvest.md            ← #6 193 → 274               │
└─────────────────────────────────────────────────────────┘
```

Изменения **независимы** друг от друга — могут выполняться в любом порядке.

---

## 4. План выполнения (подзадачи)

| № | Задача | Файл | Специалист | Сложность |
|---|--------|------|------------|-----------|
| T1 | Убрать dead code (`if instrument else ...`) | [`data.py`](nautilus_trader/adapters/tinvest/data.py:695) | `backend` | Тривиально |
| T2 | Заменить `asyncio.create_task` на `self.create_task` | [`execution.py`](nautilus_trader/adapters/tinvest/execution.py:1087) | `backend` | Тривиально |
| T3 | Исправить моки `as_f64` → `as_double` | [`test_execution.py`](tests/unit_tests/adapters/tinvest/test_execution.py:67) | `tester` | Тривиально |
| T4 | Исправить `get_instruments` return `[]` → `{}` | [`conftest.py`](tests/unit_tests/adapters/tinvest/conftest.py:160) | `tester` | Тривиально |
| T5 | Добавить `TInvestGrpcClient` в `__all__` | [`__init__.py`](nautilus_trader/adapters/tinvest/__init__.py:40) | `backend` | Тривиально |
| T6 | Обновить число тестов 193 → 274 | [`tinvest.md`](docs/integrations/tinvest.md:685) | `docs` | Тривиально |
| T7 | Прогнать полный test suite (274 теста) | Все | `tester` | Проверка |

### Стратегия выполнения

Рекомендуется **пакетный подход**: один исполнитель (`backend`) делает T1, T2, T5
одним коммитом, затем `tester` делает T3, T4 и прогоняет T7. T6 делает `docs`.

Альтернативно — все 6 правок + проверка одним исполнителем за одну итерацию
(минимальные накладные расходы на переключение контекста).

---

## 5. Верификация

```bash
# Прогнать все тесты адаптера
pytest tests/unit_tests/adapters/tinvest/ -v

# Ожидаемый результат: 274 passed
```

Дополнительно:
- `ruff check` на изменённых Python-файлах
- `mypy` на изменённых Python-файлах (если настроен)

---

## 6. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Изменение сигнатуры `create_task` в будущем | Низкая | Низкое | Метод уже стабилен в базовом классе |
| Тест упадёт из-за смены `as_f64` → `as_double` | Низкая | Низкое | MagicMock принимает любые атрибуты |
| `get_instruments` list → dict сломает тест | Низкая | Низкое | Ни один тест не итерирует `get_instruments()` |
| Человеческая ошибка при редактировании | Низкая | Низкое | 274 теста — быстрая проверка |
