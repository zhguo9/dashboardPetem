#!/usr/bin/env python3
"""
纳斯达克综合指数回撤监控脚本
- 获取近6个月数据，计算从高点的回撤
- 超过阈值(8%)时输出警报信息
"""

import json
import os
import urllib.request
import datetime

# ============ 配置 ============
THRESHOLD = 8.0  # 回撤触发百分比
LOOKBACK_DAYS = 180  # 回顾天数
# =============================


def fetch_nasdaq_data():
    """从 nasdaq.com API 获取历史数据"""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=LOOKBACK_DAYS)

    fromdate = start.strftime("%Y-%m-%d")
    todate = today.strftime("%Y-%m-%d")

    url = (
        f"https://api.nasdaq.com/api/quote/COMP/historical"
        f"?assetclass=index&fromdate={fromdate}&todate={todate}&limit=200"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())

    rows = data["data"]["tradesTable"]["rows"]

    closes = []
    for row in rows:
        close_str = row["close"].replace(",", "")
        try:
            closes.append((row["date"], float(close_str)))
        except ValueError:
            continue

    return closes


def main():
    closes = fetch_nasdaq_data()
    if not closes:
        print("❌ 无法获取纳斯达克数据")
        exit(1)

    # 最新收盘（第一行是最新）
    latest_date, latest_price = closes[0]
    # 6个月最高
    closes_sorted = sorted(closes, key=lambda x: x[1], reverse=True)
    high_date, high_price = closes_sorted[0]

    drawdown = (high_price - latest_price) / high_price * 100
    triggered = drawdown > THRESHOLD

    # 输出 summary（会显示在 Actions 日志里）
    print(f"📆 数据区间: {closes[-1][0]} ~ {latest_date}")
    print(f"💹 最新收盘 ({latest_date}): {latest_price:,.2f}")
    print(f"🏔️ 6个月最高 ({high_date}): {high_price:,.2f}")
    print(f"📉 当前回撤: {drawdown:.2f}%")
    print(f"🔔 触发买入信号: {'是' if triggered else '否'}")
    print(f"⚙️  阈值: {THRESHOLD}%")

    # 设置 GitHub Actions 输出
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"alert={'true' if triggered else 'false'}\n")
        f.write(f"drawdown={drawdown:.2f}\n")
        f.write(f"latest_price={latest_price:.2f}\n")
        f.write(f"high_price={high_price:.2f}\n")
        f.write(f"latest_date={latest_date}\n")
        f.write(f"high_date={high_date}\n")

    # 保存警报 JSON（供飞书推送使用）
    msg = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🚨 NASDAQ 回撤警报！" if triggered else "📊 NASDAQ 每日监控",
                },
                "template": "red" if triggered else "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**纳斯达克综合指数 — 回撤监控报告**\n\n"
                            f"📆 最新数据: **{latest_date}**\n"
                            f"💹 最新收盘: **{latest_price:,.2f}**\n"
                            f"🏔️ 6个月高点: **{high_price:,.2f}**（{high_date}）\n"
                            f"📉 当前回撤: **{drawdown:.2f}%**\n\n"
                            + (
                                f"🔴 **回撤已超 {THRESHOLD}%！建议考虑分批买入！**"
                                if triggered
                                else f"🟢 回撤 {drawdown:.2f}%，低于 {THRESHOLD}% 警戒线，正常状态。"
                            )
                        ),
                    },
                },
            ],
        },
    }

    with open("/tmp/nasdaq_alert.json", "w") as f:
        json.dump(msg, f, ensure_ascii=False)

    if not triggered:
        print("\n✅ 正常状态，未触发买入信号。")
    else:
        print(f"\n🔴 警告！回撤 {drawdown:.2f}% 超过 {THRESHOLD}% 阈值！")


if __name__ == "__main__":
    main()
