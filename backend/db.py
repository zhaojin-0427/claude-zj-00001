"""数据库初始化与连接（SQLite，无需外部服务）"""
import sqlite3
from pathlib import Path

try:  # 运行 seed/独立脚本时不强制安装 Flask
    from flask import g
except ImportError:
    try:  # 优先复用标准库回退服务器的请求级 g
        from stdlib_server import g
    except ImportError:  # pragma: no cover - 纯独立脚本场景
        class _GStub:
            """无 Flask 环境下的最小 g：仅承载本请求连接"""
            pass

        g = _GStub()

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
    batch_id          INTEGER REFERENCES vaccine_batches(id),  -- 扣减的库存批次（历史记录可为空）
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 疫苗库存批次：同一疫苗 + 同一批号不得重复
CREATE TABLE IF NOT EXISTS vaccine_batches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    vaccine_id       INTEGER NOT NULL REFERENCES vaccines(id),
    batch_no         TEXT NOT NULL,          -- 批号
    manufacturer     TEXT NOT NULL,          -- 生产厂家
    production_date  TEXT NOT NULL,          -- 生产日期 YYYY-MM-DD
    expiry_date      TEXT NOT NULL,          -- 有效期至 YYYY-MM-DD
    initial_quantity INTEGER NOT NULL CHECK(initial_quantity > 0),  -- 首次入库数量
    remaining        INTEGER NOT NULL CHECK(remaining >= 0),        -- 当前剩余数量（禁止负库存）
    warning_threshold INTEGER NOT NULL DEFAULT 10 CHECK(warning_threshold >= 0),  -- 低库存预警阈值
    operator         TEXT NOT NULL,          -- 登记操作人
    note             TEXT,                   -- 备注
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK(date(expiry_date) >= date(production_date))  -- 有效期不得早于生产日期
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_vaccine_no
    ON vaccine_batches(vaccine_id, lower(batch_no));

-- 库存流水：入库 inbound / 接种消耗 consume / 调整 adjust
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id         INTEGER NOT NULL REFERENCES vaccine_batches(id),
    vaccination_id   INTEGER REFERENCES vaccinations(id),  -- 仅 consume 类型有值
    type             TEXT NOT NULL CHECK(type IN ('inbound','consume','adjust')),
    quantity         INTEGER NOT NULL CHECK(quantity > 0),       -- 变动数量（正整数）
    delta            INTEGER NOT NULL,                           -- 对库存的带符号增减
    remaining_after  INTEGER NOT NULL CHECK(remaining_after >= 0),  -- 变动后结余
    reason           TEXT NOT NULL,          -- 变动原因
    operator         TEXT NOT NULL,          -- 操作人
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
-- 同一接种记录至多一条消耗流水：防止重复扣减
CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_vaccination
    ON inventory_transactions(vaccination_id)
    WHERE vaccination_id IS NOT NULL;

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

CREATE TABLE IF NOT EXISTS followup_plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id       INTEGER NOT NULL REFERENCES pets(id),
    vaccine_id   INTEGER NOT NULL REFERENCES vaccines(id),
    plan_date    TEXT NOT NULL,          -- 计划随访日期
    assignee     TEXT NOT NULL,          -- 负责人
    note         TEXT,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','confirmed','completed','cancelled')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL + busy_timeout：降低单文件 SQLite 在并发/读写重叠时的锁冲突
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        g.db = conn
    return g.db

def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # 旧库迁移：vaccinations 增加 batch_id 列（历史接种记录保持兼容，允许为空）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vaccinations)")}
    if "batch_id" not in cols:
        conn.execute("ALTER TABLE vaccinations ADD COLUMN batch_id INTEGER")
    conn.commit()
    conn.close()
