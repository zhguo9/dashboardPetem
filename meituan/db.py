"""
美团 Dashboard - 数据库模块
SQLite 数据模型与 CRUD 操作
"""

import sqlite3
import os
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "meituan.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            city        TEXT NOT NULL,
            district    TEXT DEFAULT '',
            address     TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',  -- active / closed
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id        INTEGER NOT NULL,
            date            TEXT NOT NULL,
            foot_traffic    INTEGER DEFAULT 0,       -- 进店人数
            deal_orders     INTEGER DEFAULT 0,        -- 团购订单数
            deal_revenue    REAL DEFAULT 0.0,         -- 团购销售额(元)
            deal_refunds    INTEGER DEFAULT 0,        -- 退款数
            deal_refund_amt REAL DEFAULT 0.0,         -- 退款金额
            avg_price       REAL DEFAULT 0.0,         -- 平均团购客单价
            checkins        INTEGER DEFAULT 0,        -- 核销数
            exposure        INTEGER DEFAULT 0,        -- 曝光量(如有)
            rating          REAL DEFAULT 0.0,         -- 评分(如有)
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(store_id, date),
            FOREIGN KEY (store_id) REFERENCES stores(id)
        );

        CREATE TABLE IF NOT EXISTS deals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id        INTEGER NOT NULL,
            name            TEXT NOT NULL,
            category        TEXT DEFAULT '',         -- 品类: 美发/美甲/美容/...
            original_price  REAL DEFAULT 0.0,
            deal_price      REAL DEFAULT 0.0,
            commission      REAL DEFAULT 0.0,       -- 佣金比例%
            daily_sales     INTEGER DEFAULT 0,      -- 当日销量
            total_sales     INTEGER DEFAULT 0,      -- 累计销量
            start_date      TEXT,
            end_date        TEXT,
            status          TEXT DEFAULT 'active',
            record_date     TEXT NOT NULL,           -- 数据记录日期
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (store_id) REFERENCES stores(id)
        );

        CREATE INDEX IF NOT EXISTS idx_daily_store_date ON daily_metrics(store_id, date);
        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_metrics(date);
        CREATE INDEX IF NOT EXISTS idx_deals_store ON deals(store_id);
    """)
    conn.commit()
    conn.close()


# ---- Store CRUD ----

def add_store(name: str, city: str, district: str = "", address: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO stores (name, city, district, address) VALUES (?, ?, ?, ?)",
        (name, city, district, address),
    )
    conn.commit()
    store_id = cur.lastrowid
    conn.close()
    return store_id


def get_stores() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM stores ORDER BY city, name", conn)
    conn.close()
    return df


def get_store(store_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def bulk_upsert_stores(stores: list[dict]):
    """批量导入门店: [{name, city, district, address}, ...]"""
    conn = get_conn()
    for s in stores:
        conn.execute(
            """INSERT OR IGNORE INTO stores (name, city, district, address)
               VALUES (?, ?, ?, ?)""",
            (s["name"], s["city"], s.get("district", ""), s.get("address", "")),
        )
    conn.commit()
    conn.close()


# ---- Daily Metrics CRUD ----

def upsert_daily(store_id: int, record_date: str, **kwargs):
    """插入或更新一条门店日数据"""
    fields = {
        "foot_traffic": kwargs.get("foot_traffic", 0),
        "deal_orders": kwargs.get("deal_orders", 0),
        "deal_revenue": kwargs.get("deal_revenue", 0.0),
        "deal_refunds": kwargs.get("deal_refunds", 0),
        "deal_refund_amt": kwargs.get("deal_refund_amt", 0.0),
        "avg_price": kwargs.get("avg_price", 0.0),
        "checkins": kwargs.get("checkins", 0),
        "exposure": kwargs.get("exposure", 0),
        "rating": kwargs.get("rating", 0.0),
    }
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)

    conn = get_conn()
    conn.execute(
        f"""INSERT INTO daily_metrics (store_id, date, {cols})
            VALUES (?, ?, {placeholders})
            ON CONFLICT(store_id, date) DO UPDATE SET {updates}""",
        [store_id, record_date] + list(fields.values()),
    )
    conn.commit()
    conn.close()


def get_daily(
    store_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    city: Optional[str] = None,
) -> pd.DataFrame:
    """查询门店日数据，支持过滤"""
    conn = get_conn()
    where = []
    params = []
    if store_id:
        where.append("d.store_id = ?")
        params.append(store_id)
    if start_date:
        where.append("d.date >= ?")
        params.append(start_date)
    if end_date:
        where.append("d.date <= ?")
        params.append(end_date)
    if city:
        where.append("s.city = ?")
        params.append(city)

    where_clause = " AND ".join(where) if where else "1=1"
    query = f"""
        SELECT d.*, s.name as store_name, s.city, s.district
        FROM daily_metrics d
        JOIN stores s ON d.store_id = s.id
        WHERE {where_clause}
        ORDER BY d.date DESC, s.city, s.name
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_latest_date() -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT MAX(date) as max_date FROM daily_metrics").fetchone()
    conn.close()
    return row["max_date"] if row else None


def get_date_range() -> tuple:
    conn = get_conn()
    row = conn.execute(
        "SELECT MIN(date) as min_date, MAX(date) as max_date FROM daily_metrics"
    ).fetchone()
    conn.close()
    return (row["min_date"], row["max_date"]) if row else (None, None)


# ---- Deal CRUD ----

def upsert_deal(store_id: int, record_date: str, name: str, **kwargs):
    conn = get_conn()
    conn.execute(
        """INSERT INTO deals (store_id, record_date, name, category,
           original_price, deal_price, commission, daily_sales, total_sales,
           start_date, end_date, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT DO NOTHING""",
        (
            store_id,
            record_date,
            name,
            kwargs.get("category", ""),
            kwargs.get("original_price", 0.0),
            kwargs.get("deal_price", 0.0),
            kwargs.get("commission", 0.0),
            kwargs.get("daily_sales", 0),
            kwargs.get("total_sales", 0),
            kwargs.get("start_date", ""),
            kwargs.get("end_date", ""),
            kwargs.get("status", "active"),
        ),
    )
    conn.commit()
    conn.close()


def get_deals(store_id: Optional[int] = None) -> pd.DataFrame:
    conn = get_conn()
    where = "WHERE d.store_id = ?" if store_id else ""
    params = [store_id] if store_id else []
    query = f"""
        SELECT d.*, s.name as store_name, s.city
        FROM deals d
        JOIN stores s ON d.store_id = s.id
        {where}
        ORDER BY d.record_date DESC
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


# ---- Aggregate Queries ----

def get_summary(start_date: str, end_date: str) -> dict:
    """获取概览统计"""
    conn = get_conn()
    row = conn.execute(
        """SELECT
            COUNT(DISTINCT store_id) as store_count,
            SUM(foot_traffic) as total_traffic,
            SUM(deal_orders) as total_orders,
            SUM(deal_revenue) as total_revenue,
            SUM(checkins) as total_checkins,
            SUM(deal_refunds) as total_refunds
           FROM daily_metrics
           WHERE date BETWEEN ? AND ?""",
        (start_date, end_date),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_city_summary(start_date: str, end_date: str) -> pd.DataFrame:
    """按城市汇总"""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT
            s.city,
            COUNT(DISTINCT s.id) as store_count,
            SUM(d.foot_traffic) as total_traffic,
            SUM(d.deal_orders) as total_orders,
            SUM(d.deal_revenue) as total_revenue,
            ROUND(AVG(d.avg_price), 2) as avg_price,
            SUM(d.checkins) as total_checkins
           FROM daily_metrics d
           JOIN stores s ON d.store_id = s.id
           WHERE d.date BETWEEN ? AND ?
           GROUP BY s.city
           ORDER BY total_revenue DESC""",
        conn,
        params=(start_date, end_date),
    )
    conn.close()
    return df


def get_top_stores(metric: str = "deal_revenue", start_date: str = None, end_date: str = None, limit: int = 10) -> pd.DataFrame:
    """Top N 门店排行"""
    conn = get_conn()
    where = ""
    params = []
    if start_date and end_date:
        where = "WHERE d.date BETWEEN ? AND ?"
        params = [start_date, end_date]
    df = pd.read_sql_query(
        f"""SELECT
            s.name, s.city, s.district,
            SUM(d.foot_traffic) as total_traffic,
            SUM(d.deal_orders) as total_orders,
            SUM(d.deal_revenue) as total_revenue,
            ROUND(AVG(d.avg_price), 2) as avg_price
           FROM daily_metrics d
           JOIN stores s ON d.store_id = s.id
           {where}
           GROUP BY s.id
           ORDER BY SUM({metric}) DESC
           LIMIT ?""",
        conn,
        params=params + [limit],
    )
    conn.close()
    return df


if __name__ == "__main__":
    init_db()
    print(f"✅ 数据库初始化完成: {DB_PATH}")
