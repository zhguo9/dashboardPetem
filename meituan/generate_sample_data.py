"""
生成示例数据 - 批量插入版本
"""
import sqlite3
import random
import os
from datetime import date, timedelta

random.seed(42)

CITIES = {
    "北京": ["朝阳区", "海淀区", "东城区", "西城区", "丰台区", "通州区", "大兴区", "昌平区", "顺义区", "房山区"],
    "上海": ["浦东新区", "黄浦区", "徐汇区", "静安区", "长宁区", "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区"],
    "深圳": ["南山区", "福田区", "罗湖区", "宝安区", "龙岗区", "龙华区", "光明区", "坪山区", "盐田区", "大鹏新区"],
}

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "meituan.db")


def generate():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")

    # 建表
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT DEFAULT '',
            address TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            foot_traffic INTEGER DEFAULT 0,
            deal_orders INTEGER DEFAULT 0,
            deal_revenue REAL DEFAULT 0.0,
            deal_refunds INTEGER DEFAULT 0,
            deal_refund_amt REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            checkins INTEGER DEFAULT 0,
            exposure INTEGER DEFAULT 0,
            rating REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(store_id, date),
            FOREIGN KEY (store_id) REFERENCES stores(id)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_store_date ON daily_metrics(store_id, date);
    """)

    # 清空旧数据
    conn.execute("DELETE FROM daily_metrics")
    conn.execute("DELETE FROM stores")
    conn.commit()

    store_types = ["美发", "美甲", "美容", "SPA", "皮肤管理"]
    all_stores = []
    store_id = 0

    for city, districts in CITIES.items():
        num_stores = 70 if city in ("北京", "上海") else 60
        for i in range(num_stores):
            dist = random.choice(districts)
            name = f"{city}{dist}{random.choice(store_types)}{i+1}号店"
            store_id += 1
            all_stores.append((store_id, name, city, dist))

    # 批量插入门店
    conn.executemany(
        "INSERT INTO stores (id, name, city, district) VALUES (?, ?, ?, ?)",
        all_stores,
    )
    conn.commit()
    print(f"✅ 已创建 {len(all_stores)} 家门店")

    # 生成数据
    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    batch = []
    current = start_date
    total = 0

    sid_list = [sid for sid, _, _, _ in all_stores]

    while current <= end_date:
        is_weekend = current.weekday() >= 5
        traffic_base = (500, 1200) if is_weekend else (300, 800)
        order_ratio = 0.18 if is_weekend else 0.12

        is_holiday = (current.month in (1, 5, 10) and current.day <= 7)

        for idx, sid in enumerate(sid_list):
            city_idx = idx % 3
            city_factor = [1.1, 1.05, 0.95][city_idx]
            city_factor *= random.uniform(0.8, 1.2)

            base = random.randint(*traffic_base)
            foot_traffic = int(base * city_factor * (1.3 if is_holiday else 1.0))
            orders = int(foot_traffic * order_ratio * random.uniform(0.7, 1.3))
            avg_price = random.randint(80, 500)
            revenue = orders * avg_price
            refunds = int(orders * random.uniform(0.01, 0.08))
            checkins = int(orders * random.uniform(0.6, 0.95))
            exposure = int(foot_traffic * random.uniform(2, 5))

            # 随机异常
            if random.random() < 0.02:
                if random.random() < 0.5:
                    foot_traffic = int(foot_traffic * random.uniform(0.1, 0.3))
                else:
                    orders = int(orders * random.uniform(2.5, 4.0))
                    revenue = orders * avg_price

            batch.append((
                sid, current.strftime("%Y-%m-%d"),
                foot_traffic, orders, revenue, refunds,
                refunds * avg_price, int(avg_price), checkins,
                exposure, round(random.uniform(3.5, 5.0), 1),
            ))
            total += 1

        if len(batch) >= 2000:
            conn.executemany(
                """INSERT OR IGNORE INTO daily_metrics
                   (store_id, date, foot_traffic, deal_orders, deal_revenue,
                    deal_refunds, deal_refund_amt, avg_price, checkins,
                    exposure, rating)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
            batch = []

        if current.day % 15 == 0:
            print(f"  📅 {current} 完成 ({len(sid_list)} 门店 x {(current - start_date).days + 1} 天)")

        current += timedelta(days=1)

    # 最后一次批量写入
    if batch:
        conn.executemany(
            """INSERT OR IGNORE INTO daily_metrics
               (store_id, date, foot_traffic, deal_orders, deal_revenue,
                deal_refunds, deal_refund_amt, avg_price, checkins,
                exposure, rating)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )

    conn.commit()
    conn.close()

    print(f"\n✅ 示例数据生成完成!")
    print(f"   📅 {start_date} ~ {end_date} ({90}天)")
    print(f"   🏪 {len(all_stores)} 家门店 (北京70/上海70/深圳60)")
    print(f"   💾 {total:,} 条日数据记录")


if __name__ == "__main__":
    generate()
