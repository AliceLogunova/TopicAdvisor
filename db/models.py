"""
db/models.py — ORM-модели базы данных (SQLAlchemy)

Этот файл описывает структуру всех таблиц PostgreSQL через Python-классы.
Каждый класс = одна таблица в базе данных.
SQLAlchemy автоматически переводит эти классы в SQL-таблицы через Alembic-миграции.

Таблицы:
    - Article             — метаданные статей arXiv (title, abstract, authors, url и др.)
    - ArticleEmbedding    — связь статьи с её вектором в FAISS-индексе
    - ExtractedFact       — структурированные факты извлечённые LLM из абстрактов
    - UserQuery           — запросы пользователей с ограничениями (уровень, срок)
    - GeneratedTopic      — сгенерированные темы с обоснованием и источниками

Зависимости:
    - db/session.py   — использует Base для создания таблиц
    - db/migrations/  — Alembic читает модели и генерирует SQL-миграции
    - data/indexer.py — пишет статьи и факты в эти таблицы
    - core/pipeline.py — пишет запросы и темы в эти таблицы
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс от которого наследуются все модели.
    Alembic смотрит на все классы унаследованные от Base
    и генерирует для них SQL-таблицы."""
    pass


class Article(Base):
    """Метаданные научных статей полученных с arXiv.
    Поля соответствуют полям arXiv API с минимальными переименованиями."""

    __tablename__ = "articles"

    # Внутренний первичный ключ — PostgreSQL присваивает автоматически
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Короткий ID статьи на arXiv (например 2401.12345),
    # извлекается из полного entry_id URL
    arxiv_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Название статьи
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Аннотация (в arXiv API называется summary)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)

    # Список авторов в виде JSON-строки (авторов может быть несколько)
    authors: Mapped[str] = mapped_column(Text, nullable=True)

    # Точная дата первой публикации статьи на arXiv
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Полная ссылка на страницу статьи (https://arxiv.org/abs/...)
    url: Mapped[str] = mapped_column(String(255), nullable=False)

    # Главная категория статьи (например cs.AI, cs.LG, cs.CL)
    # Используется для фильтрации при индексации и поиске
    primary_category: Mapped[str] = mapped_column(String(50), nullable=True)

    # Все категории статьи в виде JSON-строки (их может быть несколько)
    subjects: Mapped[str] = mapped_column(Text, nullable=True)

    # Дата и время когда статья была проиндексирована в моей системе
    # Устанавливается автоматически PostgreSQL при добавлении записи
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Связь один-к-одному с таблицей article_embeddings
    # uselist=False — у статьи только один вектор
    embedding: Mapped["ArticleEmbedding"] = relationship(
        back_populates="article", uselist=False
    )

    # Связь один-ко-многим с таблицей extracted_facts
    facts: Mapped["ExtractedFact"] = relationship(back_populates="article")


class ArticleEmbedding(Base):
    """Хранит связь между статьёй и её вектором в FAISS-индексе.
    FAISS хранит только числа — эта таблица позволяет по номеру
    вектора найти соответствующую статью в PostgreSQL."""

    __tablename__ = "article_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Ссылка на статью в таблице articles
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=False
    )

    # Порядковый номер вектора в FAISS-индексе
    # После поиска в FAISS по этому номеру находим статью в PostgreSQL
    vector_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Название модели которой считался эмбеддинг
    # Нужно чтобы знать когда пересчитать векторы при смене модели
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)

    # Обратная связь со статьёй
    article: Mapped["Article"] = relationship(back_populates="embedding")


class ExtractedFact(Base):
    """Структурированные факты извлечённые LLM Extractor из абстракта статьи.
    Списки (methods, datasets, metrics) хранятся как JSON-строки."""

    __tablename__ = "extracted_facts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Ссылка на статью из которой извлечены факты
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id"), nullable=False
    )

    # Описание проблемы которую решает статья
    problem: Mapped[str] = mapped_column(Text, nullable=True)

    # Ограничения / что не решено в статье
    gap: Mapped[str] = mapped_column(Text, nullable=True)

    # Методы используемые в статье (JSON-список)
    methods_json: Mapped[str] = mapped_column(Text, nullable=True)

    # Датасеты используемые в статье (JSON-список)
    datasets_json: Mapped[str] = mapped_column(Text, nullable=True)

    # Метрики качества используемые в статье (JSON-список)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=True)

    # Обратная связь со статьёй
    article: Mapped["Article"] = relationship(back_populates="facts")


class UserQuery(Base):
    """Запросы пользователей к системе.
    Хранит исходный текст, расширенные подзапросы от Planner LLM
    и ограничения пользователя (уровень обучения, срок)."""

    __tablename__ = "user_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Ссылка на пользователя, который создал запрос
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)  # ← добавить

    # Исходный текст запроса пользователя
    query_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Список из 10-20 подзапросов сгенерированных Planner LLM (JSON-список)
    expanded_queries_json: Mapped[str] = mapped_column(Text, nullable=True)

    # Степень обучения: bachelor / master / phd / postdoc
    level: Mapped[str] = mapped_column(String(20), nullable=True)

    # Желаемый срок работы в месяцах
    term: Mapped[int] = mapped_column(Integer, nullable=True)

    # Язык запроса: ru или en
    locale: Mapped[str] = mapped_column(String(10), nullable=True)

    # Дата и время запроса — устанавливается автоматически
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Связь один-ко-многим с таблицей generated_topics
    topics: Mapped[list["GeneratedTopic"]] = relationship(back_populates="query")


class GeneratedTopic(Base):
    """Темы ВКР/научных статей сгенерированные системой.
    Каждая тема привязана к конкретному запросу пользователя."""

    __tablename__ = "generated_topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Ссылка на запрос пользователя по которому сгенерирована тема
    query_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_queries.id"), nullable=False
    )

    # Формулировка темы
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Обоснование темы (почему сейчас, на основе gaps из статей)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)

    # Предлагаемый исследовательский подход и методы
    approach: Mapped[str] = mapped_column(Text, nullable=True)

    # Найденные датасеты релевантные для темы
    datasets: Mapped[str] = mapped_column(Text, nullable=True)

    # Список arXiv-статей источников (JSON-список с title и url)
    sources_json: Mapped[str] = mapped_column(Text, nullable=True)

    # Порядковый номер темы в выдаче — нужен для пагинации
    # и кнопки «Ещё варианты»
    rank: Mapped[int] = mapped_column(Integer, nullable=True)

    # Обратная связь с запросом пользователя
    query: Mapped["UserQuery"] = relationship(back_populates="topics")


class User(Base):
    """Пользователи системы для аутентификации через JWT.
    Хранит email, хэш пароля и язык интерфейса."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Уникальный email пользователя, используется для входа
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Хэш пароля, не храню plain-text пароль по соображениям безопасности
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Язык интерфейса пользователя (ru или en), по умолчанию ru
    locale: Mapped[str] = mapped_column(String(10), nullable=True, default="ru")

    # Дата и время регистрации пользователя
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())