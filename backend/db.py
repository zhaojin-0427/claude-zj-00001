"""数据库初始化与连接（SQLite，无需外部服务）"""
import sqlite3
from pathlib import Path
from flask import g

DB_PATH = Path(__file__).parent / "data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    address      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS pets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES owners(id),
    name         TEXT NOT NULL,
    species      TEXT NOT NULL,          -- 狗 / 猫 / 兔 ...
    breed        TEXT,
    gender       TEXT,                   -- 公 / 母
    birth_date   TEXT,                   -- YYYY-MM-DD
    color        TEXT,
    microchip    TEXT,
    neutered     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS vaccines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,        -- 狂犬疫苗
    species        TEXT NOT NULL DEFAULT '通用',  -- 适用物种
    interval_days  INTEGER NOT NULL,     -- 建议接种间隔（天）
    core           INTEGER NOT NULL DEFAULT 1,   -- 是否核心疫苗
    description    TEXT
);

CREATE TABLE IF NOT EXISTS vaccinations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id            INTEGER NOT NULL REFERENCES pets(id),
    vaccine_id        INTEGER NOT NULL REFERENCES vaccines(id),
    vacc_date         TEXT NOT NULL,     -- 接种日期
    batch_no          TEXT,              -- 疫苗批号
    manufacturer      TEXT,              -- 生产厂家
    site              TEXT,              -- 注射部位
    doctor            TEXT,              -- 接种医生
    adverse_reaction  TEXT,              -- 不良反应：无/轻微/严重 + 描述
    next_due_date     TEXT,              -- 建议下次接种日期
    note              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS antibody_tests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id       INTEGER NOT NULL REFERENCES pets(id),
    vaccine_id   INTEGER NOT NULL REFERENCES vaccines(id),
    test_date    TEXT NOT NULL,
    result       TEXT NOT NULL,          -- 阳性 / 阴性 / 弱阳性
    titer        REAL,                   -- 抗体滴度（可选）
    lab          TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
