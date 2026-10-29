# Resume-механизм: анализ и рекомендации

## Что такое `resume` в Claude SDK

`resume` — штатная опция Claude CLI (`claude --resume <session_id>`), позволяющая продолжить предыдущую сессию. При использовании через SDK передаётся как параметр `ClaudeAgentOptions(resume=session_id)`.

**Штатное назначение**: пользователь закрыл терминал → открыл снова → продолжает тот же диалог с тем же агентом, теми же tools, тем же system prompt.

---

## Как `resume` используется в Scenario Builder

В нашем коде `resume` используется **нештатно** — не для продолжения диалога, а как **механизм передачи контекста между РАЗНЫМИ агентами**.

### Цепочка в коде

```
orchestrator.py L718-721 — захват session_id:
┌──────────────────────────────────────────────────────────────┐
│ if isinstance(msg, ResultMessage):                           │
│     sid = getattr(msg, 'session_id', None)                   │
│     if sid:                                                  │
│         sdk_session = sid                                    │
└──────────────────────────────────────────────────────────────┘

orchestrator.py L743-744 — сохранение:
┌──────────────────────────────────────────────────────────────┐
│ if sdk_session:                                              │
│     self.state.sdk_session_id = sdk_session                  │
└──────────────────────────────────────────────────────────────┘

orchestrator.py L636-649 — использование в следующем агенте:
┌──────────────────────────────────────────────────────────────┐
│ resume_id = self.state.sdk_session_id or None                │
│ options = ClaudeAgentOptions(                                 │
│     system_prompt=system_prompt,  # ← НОВЫЙ system prompt!   │
│     allowed_tools=[...],          # ← НОВЫЕ tools!           │
│     resume=resume_id,             # ← история предыдущего    │
│ )                                                            │
└──────────────────────────────────────────────────────────────┘
```

### Что происходит при каждом query()

```
query #1: SourceAnalyst
  system_prompt = source-analyst.md
  allowed_tools = [read_source_files, ask_user_question, list_workspace, read_reference]
  resume = None                           ← первый агент, нет истории
  → ResultMessage.session_id = "sess_abc123"
  → state.sdk_session_id = "sess_abc123"

query #2: StructurePlanner
  system_prompt = structure-planner.md    ← ДРУГОЙ system prompt
  allowed_tools = [read_source_files, present_proposal, ...]  ← ДРУГИЕ tools
  resume = "sess_abc123"                  ← видит ВСЮ историю SourceAnalyst
  → ResultMessage.session_id = "sess_def456"
  → state.sdk_session_id = "sess_def456"  ← перезаписывает!

query #3: ContentWriter
  system_prompt = content-writer.md       ← ТРЕТИЙ system prompt
  allowed_tools = [write_component, find_replace_in_file, ...]
  resume = "sess_def456"                  ← видит историю SourceAnalyst + StructurePlanner
  → ...цепочка растёт с каждым шагом
```

**Важно**: `sdk_session_id` перезаписывается каждым агентом (L744). Это значит, что каждый следующий агент видит **всю накопленную историю** всех предыдущих агентов.

---

## Что именно попадает в API при resume

Когда Claude CLI делает resume, он загружает из локального кеша (`~/.claude/`) полную историю сессии и отправляет её на API-сервер (Anthropic / AWS Bedrock) как часть input.

### Пример: StructurePlanner с resume

```
API Request → Bedrock:
┌──────────────────────────────────────────────────────────────┐
│ MESSAGES (из resume — история SourceAnalyst):                │
│                                                              │
│  [0] system: source-analyst.md (3KB)                         │
│  [1] user: "_build_source_prompt() output" (2KB)             │
│  [2] assistant: "Давайте начнём анализ..."                   │
│  [3] tool_call: read_source_files(path="persona.txt")        │
│  [4] tool_result: "[содержимое persona.txt — 5KB]"           │
│  [5] tool_call: read_source_files(path="stages.txt")         │
│  [6] tool_result: "[содержимое stages.txt — 8KB]"            │
│  [7] tool_call: read_source_files(path="manifest.yaml")      │
│  [8] tool_result: "[содержимое manifest.yaml — 2KB]"         │
│  [9] tool_call: ask_user_question(question="Уточните...")     │
│ [10] tool_result: "Ответ пользователя"                       │
│ [11] assistant: "Анализ завершён: [10KB summary]"            │
│                                                              │
│ НОВЫЕ СООБЩЕНИЯ (текущий query):                             │
│                                                              │
│ [12] system: structure-planner.md (3KB)  ← НОВЫЙ prompt      │
│ [13] user: "У тебя уже есть контекст..." (0.5KB)             │
│                                                              │
│ ИТОГО INPUT: ~35-50KB ≈ 10,000-15,000 tokens                │
└──────────────────────────────────────────────────────────────┘
```

### Без resume (только локальная сериализация)

```
API Request → Bedrock:
┌──────────────────────────────────────────────────────────────┐
│ [0] system: structure-planner.md (3KB)                       │
│ [1] user: "_build_structure_prompt() с source_register"      │
│     "Вот результат анализа: [финальный текст — 10KB]"        │
│     "Проанализируй и предложи план..."                       │
│                                                              │
│ ИТОГО INPUT: ~13KB ≈ 4,000-5,000 tokens                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Сравнение подходов

### Стоимость (токены)

| Шаг | С resume | Без resume | Разница |
|-----|----------|------------|---------|
| SourceAnalyst | ~5K tokens | ~5K tokens | = |
| StructurePlanner | ~15K tokens | ~5K tokens | **3x** |
| ContentWriter | ~30K tokens | ~8K tokens | **4x** |
| QAValidator | ~40K tokens | ~6K tokens | **7x** |
| QAValidatorFix | ~50K tokens | ~5K tokens | **10x** |
| TestRunner | ~55K tokens | ~4K tokens | **14x** |
| **ИТОГО** | **~195K** | **~33K** | **~6x дешевле** |

> Примечание: цифры примерные, зависят от размера сценария. Но порядок верный — resume накапливает историю экспоненциально.

### Функциональность

| Аспект | С resume | Без resume |
|--------|----------|------------|
| Финальный вывод предыдущего агента | ✅ Виден | ✅ Виден (через state.*) |
| Промежуточные tool calls | ✅ Видны | ❌ Не видны |
| Ошибки tool calls | ✅ Видны | ❌ Не видны |
| Вопросы и ответы пользователя | ✅ Видны в истории | ⚠️ Только если включены в вывод |
| Стоимость API | 💸💸💸 Растёт линейно | 💰 Постоянная |
| Латентность | 🐌 Растёт | ⚡ Постоянная |
| Размер контекстного окна | ⚠️ Может переполниться | ✅ Предсказуемый |
| Зависимость от CLI storage | ⚠️ `~/.claude/` должен быть доступен | ✅ Нет зависимости |
| Конфликт system prompts | ⚠️ В истории видны другие роли | ✅ Чистый контекст |

### Надёжность

| Проблема | С resume | Без resume |
|----------|----------|------------|
| `~/.claude/` очищен | 💥 Resume fails | ✅ Работает |
| Контекстное окно переполнено | 💥 API ошибка | ✅ Предсказуемо |
| Claude путается между ролями | ⚠️ Возможно | ✅ Нет |
| Session storage corruption | ⚠️ Возможно | ✅ Нет |

---

## Что уже есть для работы без resume

Код **уже полностью поддерживает** работу без resume. Вся локальная сериализация на месте:

### Сохранение контекста в state

```python
# orchestrator.py

# L134 — после SourceAnalyst:
self.state.source_register = result     # полный текст анализа

# L148 — после StructurePlanner:
self.state.layer_plan = result          # план изменений

# L174 — после QAValidator:
self.state.qa_result = result           # QA findings

# L204 — после TestRunner:
self.state.test_result = result         # результаты тестов
```

### Использование контекста в промптах

Каждый `_build_*_prompt()` уже умеет работать в режиме FULL:

```python
# _build_structure_prompt():
if self.state.sdk_session_id:
    # RESUME mode — краткий промпт
    prompt = "У тебя уже есть полный контекст..."
else:
    # FULL mode — вставляем source_register целиком
    prompt = f"Вот результат анализа:\n{self.state.source_register}\n..."

# _build_content_prompt():
# Всегда вставляет source_register + layer_plan — не зависит от resume

# _build_qa_prompt():
# Вставляет source_register + workspace info

# _build_qa_fix_prompt():
# Вставляет qa_result

# _build_test_prompt():
# Вставляет qa_result[:1000]
```

---

## Что теряется при отказе от resume

### 1. Промежуточные детали tool calls

StructurePlanner не видит, какие именно файлы SourceAnalyst читал и в каком порядке. Видит только финальный `source_register`.

**Влияние**: минимальное. `source_register` содержит все выводы анализа. Порядок чтения файлов не важен для планирования.

### 2. Сырой контент файлов в tool results

Через resume Claude видит полное содержимое файлов, которые читал предыдущий агент. Без resume — только сводку.

**Влияние**: можно компенсировать. StructurePlanner всё равно имеет `read_source_files` в своих tools и может прочитать нужные файлы сам.

### 3. Точная формулировка вопросов/ответов

Вопросы `ask_user_question` и ответы пользователя видны в resume-истории.

**Влияние**: можно компенсировать — ответы уже сохранены в `state.questions[]` и могут быть включены в промпт.

---

## Рекомендация

### Убрать resume, усилить локальную сериализацию

#### Шаг 1: Удалить resume из `_run_subagent()`

```python
# БЫЛО:
resume_id = self.state.sdk_session_id if self.state.sdk_session_id else None
options = ClaudeAgentOptions(
    ...
    resume=resume_id,
)

# СТАЛО:
options = ClaudeAgentOptions(
    ...
    # resume убран — каждый агент получает чистый контекст
)
```

#### Шаг 2: Убрать RESUME-ветку из `_build_structure_prompt()`

Всегда использовать FULL mode — вставлять `source_register` в промпт.

#### Шаг 3: (опционально) Обогатить промпты Q&A историей

```python
# Добавить в _build_*_prompt():
qa_context = ""
for q in self.state.questions:
    if q.answer:
        qa_context += f"Q: {q.question}\nA: {q.answer}\n"
if qa_context:
    prompt += f"\n## Ответы пользователя:\n{qa_context}"
```

#### Шаг 4: Удалить `sdk_session_id` из state model

Поле `sdk_session_id` в `SessionState` становится ненужным.

### Ожидаемый эффект

- **~6x снижение** потребления input tokens
- **~2-3x ускорение** API-ответов (меньше данных)
- **Нет зависимости** от `~/.claude/` session storage
- **Предсказуемое** использование контекстного окна
- **Чистый контекст** — нет конфликтов system prompts между агентами

### Риски

- Для очень сложных сценариев, где StructurePlanner полагается на «сырые» данные файлов из истории SourceAnalyst, может потребоваться чтение файлов заново. Это добавит 1-2 tool calls, но всё равно дешевле resume.

---

## Связанные файлы

| Файл | Что менять |
|------|------------|
| `src/orchestrator.py` L636-649, L718-721, L743-744 | Убрать resume логику |
| `src/orchestrator.py` `_build_structure_prompt()` | Убрать RESUME ветку |
| `src/state/models.py` | Убрать поле `sdk_session_id` |
| `ARCHITECTURE.md` | Обновить раздел SDK Execution |
| `static/architecture.html` | Обновить вкладку SDK Execution |
