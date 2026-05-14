# TopicAdvisor

Интеллектуальная система поддержки выбора тем выпускных квалификационных и научных работ. Принимает свободный текстовый запрос с указанием интересов, уровня подготовки и срока работы — и возвращает 5–12 конкретных тем с обоснованием, описанием исследовательского подхода, датасетами и ссылками на актуальные статьи arXiv.

Система построена на RAG-пайплайне: Query Expansion -> Semantic Retrieval (FAISS) -> Reranking (Cross-Encoder) -> Fact Extraction -> Topic Generation. Все LLM-вызовы выполняются локально через Ollama — без обращения к внешним API.

---

## Требования

Перед запуском убедитесь, что на вашей машине установлено следующее:

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — менеджер зависимостей и виртуальных окружений
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — для запуска PostgreSQL и Redis
- **[Ollama](https://ollama.com/)** — локальный сервер LLM

После установки Ollama скачайте языковую модель (по умолчанию используется `qwen3:4b`, можно выбрать другую совместимую):

```bash
ollama pull qwen3:4b
```

---

## Установка

**1. Клонируйте репозиторий:**

```bash
git clone https://github.com/<your-username>/TopicAdvisor.git
cd TopicAdvisor
```

**2. Установите зависимости через uv:**

```bash
uv sync
```

**3. Скопируйте файл переменных окружения и заполните его:**

```bash
cp .env.example .env
```

Откройте `.env` и при необходимости измените значения. Ключевые параметры:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=topicadvisor
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

REDIS_HOST=localhost
REDIS_PORT=6379

OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b

FAISS_INDEX_PATH=data/faiss_store/index.faiss
ARXIV_MAX_RESULTS=1000
```

**4. Запустите PostgreSQL и Redis через Docker:**

```bash
docker compose up -d
```

**5. Примените миграции базы данных:**

```bash
uv run alembic upgrade head
```

**6. Запустите сервер Ollama:**

```bash
ollama serve
```

---

## Индексация данных arXiv

Перед первым запуском пайплайна необходимо наполнить векторный индекс статьями. Команда ниже скачивает метаданные статей из arXiv и строит FAISS-индекс на диске:

```bash
uv run python data/indexer.py --source oai --category cs.AI --months 6
```

Параметры:
- `--category` — категория arXiv, например `cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`
- `--months` — глубина выборки в месяцах
- `--source` — источник данных: `oai` (OAI-PMH) или `api` (arXiv API v2)

Индексацию можно запустить несколько раз для разных категорий — индекс будет пополняться.

---

## Запуск пайплайна через CLI

Самый быстрый способ проверить систему без запуска веб-сервера:

```bash
uv run python run.py --query "интересуюсь NLP и трансформерами" --level master --duration 6
```

Параметры:

| Параметр | Описание | Значение по умолчанию |
|---|---|---|
| `--query` / `-q` | Текст запроса (интересы, область) | обязательный |
| `--level` / `-l` | Уровень: `bachelor`, `master`, `phd`, `postdoc` | `master` |
| `--duration` / `-d` | Срок работы в месяцах | `3` |
| `--topics` / `-t` | Количество генерируемых тем | `6` |
| `--output` / `-o` | Сохранить результат в JSON-файл | — |
| `--verbose` / `-v` | Подробные логи всех шагов | — |

Примеры:

```bash
uv run python run.py --query "компьютерное зрение и медицинские изображения" --level bachelor --duration 5

uv run python run.py --query "reinforcement learning" --level phd --duration 12 --topics 8 --output results.json
```

---

## Запуск веб-приложения

Веб-приложение состоит из двух частей: FastAPI-бэкенда и Next.js-фронтенда.

### Бэкенд (FastAPI)

```bash
uv run uvicorn api.main:app --reload --port 8000
```

После запуска Swagger UI доступен по адресу: [http://localhost:8000/docs](http://localhost:8000/docs)

### Фронтенд (Next.js)

```bash
cd client
npm install
npm run dev
```

Приложение будет доступно по адресу: [http://localhost:3000](http://localhost:3000)

---

## Структура проекта

```
TopicAdvisor/
├── core/               # RAG-пайплайн — вся ML-логика
├── data/               # Сбор данных, индексация, кэш
├── api/                # FastAPI-приложение, роутеры, схемы
├── db/                 # ORM-модели, сессия, миграции
├── client/             # Next.js фронтенд
├── prompts/            # Текстовые промпты для LLM
├── tests/              # Тесты
├── run.py              # CLI точка входа
├── config.py           # Централизованные настройки
├── docker-compose.yml  # PostgreSQL + Redis
└── .env.example        # Шаблон переменных окружения
```

### `core/` — интеллектуальный модуль

Содержит весь RAG-пайплайн. Не зависит от HTTP-слоя и базы данных — только ML-логика на Python. Модули вызываются последовательно через `pipeline.py`:

- **`planner.py`** — Query Expansion: расширяет запрос пользователя в 10–20 тематических подзапросов через LLM для широкого покрытия поискового пространства
- **`retriever.py`** — семантический поиск: кодирует подзапросы через Sentence-Transformers и выполняет ANN-поиск по FAISS-индексу, возвращает топ-50 кандидатов
- **`reranker.py`** — переранжирование: прогоняет топ-50 через Cross-Encoder и оставляет топ-15–20 наиболее релевантных статей
- **`extractor.py`** — извлечение фактов: отправляет абстракты в LLM и получает структурированный JSON с полями `problem`, `gap`, `methods`, `datasets`, `metrics`; при невалидном ответе — до 3 автоматических повторов
- **`generator.py`** — генерация тем: на основе извлечённых фактов и ограничений пользователя генерирует 5–12 тем с обоснованием, подходом, датасетами и источниками
- **`pipeline.py`** — оркестратор: связывает все шаги и возвращает итоговый результат

### `data/` — слой работы с данными

Отвечает за получение статей из arXiv, их индексацию и кэширование промежуточных результатов:

- **`arxiv_client.py`** — HTTP-клиент для arXiv API v2 и OAI-PMH: парсит XML-ответы и возвращает нормализованные объекты статей
- **`indexer.py`** — индексация: сохраняет метаданные в PostgreSQL, вычисляет эмбеддинги и записывает их в FAISS-индекс на диске
- **`cache.py`** — кэш на основе Redis / diskcache: хранит результаты поиска, эмбеддинги и LLM-ответы для ускорения повторных запросов
- **`faiss_store/`** — директория с персистентным FAISS-индексом, загружается при старте приложения

### `api/` — HTTP-слой

FastAPI-приложение, которое принимает запросы, вызывает `core/pipeline.py` и возвращает ответ. Пайплайн здесь не реализуется.

Основные эндпоинты:

| Эндпоинт | Назначение |
|---|---|
| `POST /auth/register` | Регистрация пользователя |
| `POST /auth/login` | Вход, получение JWT-токена |
| `POST /topics` | Полный пайплайн: запрос -> темы |
| `POST /search` | Только семантический поиск статей |
| `POST /extract` | Только извлечение фактов из абстрактов |
| `POST /generate` | Только генерация тем по статьям |

### `db/` — инфраструктура базы данных

SQLAlchemy ORM-модели, асинхронная сессия PostgreSQL через asyncpg, Alembic-миграции. Не содержит бизнес-логики.

### `client/` — веб-интерфейс

Next.js приложение с поддержкой i18n (RU/EN). Включает форму свободного ввода запроса с выбором уровня подготовки и срока, карточки тем с пагинацией, страницы авторизации и историю запросов.

### `prompts/` — промпты для LLM

Текстовые файлы с промптами для каждого LLM-компонента пайплайна. Хранятся отдельно от кода, чтобы их можно было менять и версионировать независимо.

---

## Тесты

```bash
uv run pytest
```

Покрытие включает: корректность ретривера (Precision@K, MRR), JSON parse rate экстрактора, семантическую связность тем, тесты API-эндпоинтов.

## Линтинг

```bash
uv run ruff check
```

---

## Технологический стек

| Компонент | Технология |
|---|---|
| LLM Runtime | Ollama (Gemma 2 / Qwen 3) |
| Эмбеддинги | Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| Переранжирование | Cross-Encoder (ms-marco-MiniLM-L-6-v2) |
| Векторный индекс | FAISS |
| Backend | FastAPI, Python 3.11+ |
| Frontend | Next.js, next-intl |
| База данных | PostgreSQL + SQLAlchemy + asyncpg |
| Кэш | Redis / diskcache |
| Авторизация | JWT (python-jose) |
| Зависимости | uv |
