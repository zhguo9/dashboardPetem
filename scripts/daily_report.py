#!/usr/bin/env python3
"""
美团数据看板 - 每日异动报告
生成样本数据 → 检测异常 → 输出飞书卡片格式报告
"""

import os
import sys
import json
import base64

# 项目路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# 确保有数据
from generate_sample_data import generate
generate()

# 分析模块
from db import get_daily, get_stores, get_date_range, get_city_summary, get_summary
from analytics import detect_anomalies, trend_analysis, store_health_score
import pandas as pd
from datetime import datetime, timedelta

today_str = datetime.now().strftime("%Y-%m-%d")

# ─── 1. 拉取数据 ───
df = get_daily()
if df.empty:
    print("❌ 无数据")
    exit(1)

latest_date = df["date"].max()
start_date = (pd.to_datetime(latest_date) - timedelta(days=30)).strftime("%Y-%m-%d")

print(f"📅 最新数据: {latest_date}")

# ─── 2. 概览 ───
summary = get_summary(start_date, latest_date)
city_summary = get_city_summary(start_date, latest_date)

total_orders = int(summary.get("total_orders", 0))
total_revenue = summary.get("total_revenue", 0)
total_checkins = int(summary.get("total_checkins", 0))
total_refunds = int(summary.get("total_refunds", 0))
store_count = int(summary.get("store_count", 0))
refund_rate = round(total_refunds / total_orders * 100, 1) if total_orders > 0 else 0

# ─── 3. 异动检测 ───
recent_30 = df[df["date"] >= start_date].copy()
anomalies_orders = detect_anomalies(recent_30, metric="deal_orders")
anomalies_revenue = detect_anomalies(recent_30, metric="deal_revenue")
anomalies_traffic = detect_anomalies(recent_30, metric="foot_traffic")

# 合并异常
all_alerts = []
if not anomalies_orders.empty:
    flagged = anomalies_orders[anomalies_orders["is_anomaly"] & (anomalies_orders["date"] == latest_date)]
    for _, r in flagged.iterrows():
        all_alerts.append(("下单量", r["store_name"], r["city"], r["direction"], r["z_score"]))
if not anomalies_revenue.empty:
    flagged = anomalies_revenue[anomalies_revenue["is_anomaly"] & (anomalies_revenue["date"] == latest_date)]
    for _, r in flagged.iterrows():
        all_alerts.append(("销售额", r["store_name"], r["city"], r["direction"], r["z_score"]))
if not anomalies_traffic.empty:
    flagged = anomalies_traffic[anomalies_traffic["is_anomaly"] & (anomalies_traffic["date"] == latest_date)]
    for _, r in flagged.iterrows():
        all_alerts.append(("进店流量", r["store_name"], r["city"], r["direction"], r["z_score"]))

# ─── 4. 门店健康分 ───
scores = store_health_score(recent_30)
if not scores.empty:
    worst_3 = scores.tail(3).to_dict("records")

# ─── 5. 趋势 ───
revenue_trend = trend_analysis(recent_30, metric="deal_revenue")
order_trend = trend_analysis(recent_30, metric="deal_orders")

# ─── 6. 构建报告 ───
alert_count = len(all_alerts)
has_critical = any("大跌" in a[3] for a in all_alerts)
header_color = "red" if has_critical else ("orange" if alert_count > 0 else "blue")
header_title = "🚨 美团数据异动警报！" if has_critical else \
               (f"⚠️ 美团日报 - 发现 {alert_count} 项异常" if alert_count > 0 else "📊 美团数据看板 - 日报")

# 概览行
summary_text = (
    f"📅 **数据截止**: {latest_date}\n"
    f"🏪 **营业门店**: {store_count} 家\n\n"
    f"**30天累计 KPI:**\n"
    f"• 总订单: **{total_orders:,}** 单\n"
    f"• 总销售额: **¥{total_revenue:,.0f}**\n"
    f"• 总核销: **{total_checkins:,}** 单\n"
    f"• 退款率: **{refund_rate}%**\n\n"
    f"**趋势 (近7天 vs 上7天):**\n"
    f"• 销售额: {revenue_trend.get('trend', 'N/A')} ({revenue_trend.get('growth_pct', 0):+.1f}%)\n"
    f"• 订单量: {order_trend.get('trend', 'N/A')} ({order_trend.get('growth_pct', 0):+.1f}%)"
)

# 城市排行
city_lines = []
if not city_summary.empty:
    city_summary_sorted = city_summary.sort_values("total_revenue", ascending=False)
    for _, r in city_summary_sorted.iterrows():
        city_lines.append(
            f"• {r['city']}: {int(r['store_count'])}店 | "
            f"订单 {int(r['total_orders']):,} | "
            f"销售额 ¥{r['total_revenue']:,.0f}"
        )

city_text = "\n".join(city_lines) if city_lines else "暂无"

# 异常详情
alert_lines = []
if all_alerts:
    for metric, store, city, direction, z in all_alerts[:10]:
        icon = "🔴" if "大跌" in direction else "🟡"
        alert_lines.append(f"{icon} **{store}** ({city}) — {metric} {direction} (Z={z:.1f})")
else:
    alert_lines.append("✅ 今日无显著异常")

alert_text = "\n".join(alert_lines)

# 低分门店
score_lines = []
if scores.empty:
    score_lines.append("暂无评分数据")
else:
    for s in worst_3:
        score_lines.append(
            f"⚠️ **{s['store_name']}** ({s['city']}) — {s['score']}分 | "
            f"订单 {s['total_orders']} | 退款率 {s['refund_rate']}%"
        ) if worst_3 else None

score_text = "\n".join(score_lines) if score_lines else "暂无"

# ─── 输出 GitHub Actions summary ───
GITHUB_STEP_SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY")
if GITHUB_STEP_SUMMARY:
    md = f"""# 美团日报 - {latest_date}

## 📊 概览
{summary_text}

## 🌆 城市排行
{city_text}

## 🔔 异动检测
{alert_text}

## 🏥 低分门店
{score_text}
"""
    with open(GITHUB_STEP_SUMMARY, "a") as f:
        f.write(md)

# ─── 输出到控制台 ───
print(f"\n{'='*50}")
print(f"📊 美团数据看板 - 日报 ({latest_date})")
print(f"{'='*50}")
print(f"\n🏪 门店: {store_count} 家")
print(f"📦 总订单: {total_orders:,}")
print(f"💰 总销售额: ¥{total_revenue:,.0f}")
print(f"💳 核销: {total_checkins:,}")
print(f"🔙 退款率: {refund_rate}%")
print(f"\n📈 销售额趋势: {revenue_trend.get('trend', 'N/A')} ({revenue_trend.get('growth_pct', 0):+.1f}%)")
print(f"📈 订单量趋势: {order_trend.get('trend', 'N/A')} ({order_trend.get('growth_pct', 0):+.1f}%)")
print(f"\n🔔 今日异常: {alert_count} 项")
for line in alert_lines:
    print(f"  {line}")

# ─── 输出 GitHub Actions outputs ───
GITHUB_OUTPUT = os.environ.get("GITHUB_OUTPUT")
if GITHUB_OUTPUT:
    with open(GITHUB_OUTPUT, "a") as f:
        f.write(f"latest_date={latest_date}\n")
        f.write(f"store_count={store_count}\n")
        f.write(f"total_orders={total_orders}\n")
        f.write(f"total_revenue={total_revenue:.0f}\n")
        f.write(f"alert_count={alert_count}\n")
        f.write(f"has_critical={'true' if has_critical else 'false'}\n")

print(f"\n{'='*50}")
print("✅ 报告生成完成")
