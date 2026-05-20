#!/usr/bin/env python3
"""
美团数据看板 - 静态 HTML 生成器
生成 plotly 图表并导出为 standalone HTML，部署到 GitHub Pages
"""

import os
import sys
import base64
import json
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "meituan"))

from generate_sample_data import generate
generate()

from db import get_daily, get_stores, get_date_range, get_city_summary, get_summary
from analytics import detect_anomalies, trend_analysis, store_health_score
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

today_str = datetime.now().strftime("%Y-%m-%d")

# ─── 1. 拉数据 ───
df = get_daily()
latest_date = df["date"].max()
start_date = (pd.to_datetime(latest_date) - timedelta(days=30)).strftime("%Y-%m-%d")
recent_30 = df[df["date"] >= start_date].copy()

summary = get_summary(start_date, latest_date)
city_summary = get_city_summary(start_date, latest_date)
scores = store_health_score(recent_30)

total_orders = int(summary.get("total_orders", 0))
total_revenue = summary.get("total_revenue", 0)
total_checkins = int(summary.get("total_checkins", 0))
total_refunds = int(summary.get("total_refunds", 0))
store_count = int(summary.get("store_count", 0))
refund_rate = round(total_refunds / total_orders * 100, 1) if total_orders > 0 else 0

# ─── 2. 趋势图 ───
daily_agg = recent_30.groupby("date").agg(
    销售额=("deal_revenue", "sum"),
    订单量=("deal_orders", "sum"),
    进店=("foot_traffic", "sum"),
).reset_index().sort_values("date")

fig_revenue = px.line(
    daily_agg, x="date", y="销售额",
    title="📈 近30天销售额趋势",
    template="plotly_dark",
    color_discrete_sequence=["#FFD100"],
)
fig_revenue.update_layout(margin=dict(l=20, r=20, t=40, b=20))

fig_orders = px.line(
    daily_agg, x="date", y="订单量",
    title="📦 近30天订单量趋势",
    template="plotly_dark",
    color_discrete_sequence=["#2979FF"],
)
fig_orders.update_layout(margin=dict(l=20, r=20, t=40, b=20))

# ─── 3. 城市对比 ───
if not city_summary.empty:
    fig_city = px.bar(
        city_summary, x="city", y="total_revenue",
        title="🌆 各城市销售额对比",
        template="plotly_dark",
        color="city",
        text="total_revenue",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_city.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig_city.update_layout(margin=dict(l=20, r=20, t=40, b=20), showlegend=False)

# ─── 4. 健康分排行 ───
if not scores.empty:
    top10 = scores.head(10)
    fig_scores = px.bar(
        top10, x="score", y="store_name",
        title="🏆 门店健康分 TOP 10",
        template="plotly_dark",
        orientation="h",
        color="score",
        color_continuous_scale=["#FF1744", "#FF9100", "#FFD100", "#00C853"],
        text="score",
    )
    fig_scores.update_traces(texttemplate="%{text}", textposition="outside")
    fig_scores.update_layout(margin=dict(l=20, r=20, t=40, b=20), yaxis={"categoryorder": "total ascending"})

# ─── 5. 异动检测 ───
anomalies_orders = detect_anomalies(recent_30, metric="deal_orders")
anomalies_revenue = detect_anomalies(recent_30, metric="deal_revenue")
anomalies_traffic = detect_anomalies(recent_30, metric="foot_traffic")

all_alerts = []
for name, adf, metric in [
    ("下单量", anomalies_orders, "deal_orders"),
    ("销售额", anomalies_revenue, "deal_revenue"),
    ("进店流量", anomalies_traffic, "foot_traffic"),
]:
    if not adf.empty:
        flagged = adf[adf["is_anomaly"] & (adf["date"] == latest_date)]
        for _, r in flagged.iterrows():
            all_alerts.append((metric, r["store_name"], r["city"], r["direction"], abs(r["z_score"])))

# ─── 6. 生成 HTML ───
charts_html = ""

charts_html += fig_revenue.to_html(full_html=False, include_plotlyjs="cdn", div_id="chart-revenue")
charts_html += fig_orders.to_html(full_html=False, include_plotlyjs=False, div_id="chart-orders")

if not city_summary.empty:
    charts_html += fig_city.to_html(full_html=False, include_plotlyjs=False, div_id="chart-city")

if not scores.empty:
    charts_html += fig_scores.to_html(full_html=False, include_plotlyjs=False, div_id="chart-scores")

# 异动列表
alert_items = ""
if all_alerts:
    for metric, store, city, direction, z in all_alerts:
        icon = "🔴" if "大跌" in direction else "🟡"
        alert_items += f"""
        <div class="alert-item {'alert-critical' if '大跌' in direction else 'alert-warning'}">
            <span class="alert-icon">{icon}</span>
            <span class="alert-text"><strong>{store}</strong> ({city})</span>
            <span class="alert-metric">{metric.replace('deal_','').replace('_',' ')}</span>
            <span class="alert-direction">{direction}</span>
            <span class="alert-zscore">Z={z:.1f}</span>
        </div>"""
else:
    alert_items = '<div class="alert-item alert-ok"><span class="alert-icon">✅</span> 今日无显著异常</div>'

# 城市排行
city_rows = ""
if not city_summary.empty:
    for _, r in city_summary.sort_values("total_revenue", ascending=False).iterrows():
        city_rows += f"""
        <div class="stat-row">
            <span class="stat-label">{r['city']}</span>
            <span class="stat-value">{int(r['total_orders']):,}单</span>
            <span class="stat-value">¥{r['total_revenue']:,.0f}</span>
        </div>"""

# 健康分排行
score_rows = ""
if not scores.empty:
    for i, (_, r) in enumerate(scores.head(5).iterrows()):
        score_rows += f"""
        <div class="stat-row">
            <span class="stat-rank">#{i+1}</span>
            <span class="stat-label">{r['store_name']}</span>
            <span class="stat-score">{r['score']}分</span>
        </div>"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>美团数据看板 - {latest_date}</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0F0F23;
            color: #EAEAEA;
            min-height: 100vh;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}

        /* Header */
        .header {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 20px 0; border-bottom: 1px solid #2A2A4E; margin-bottom: 24px;
        }}
        .header h1 {{ font-size: 1.8rem; color: #FFD100; }}
        .header .date {{ color: #888; font-size: 0.9rem; }}

        /* KPI Cards */
        .kpi-row {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }}
        .kpi-card {{
            background: #1A1A2E; border-radius: 12px; padding: 20px;
            border: 1px solid #2A2A4E; text-align: center;
        }}
        .kpi-value {{ font-size: 1.8rem; font-weight: 700; color: #FFD100; }}
        .kpi-label {{ font-size: 0.85rem; color: #888; margin-top: 6px; }}

        /* Charts */
        .chart-row {{
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 16px; margin-bottom: 24px;
        }}
        .chart-card {{
            background: #1A1A2E; border-radius: 12px; padding: 16px;
            border: 1px solid #2A2A4E;
        }}
        .chart-full {{ grid-column: 1 / -1; }}

        /* Alerts */
        .alert-list {{ margin-bottom: 24px; }}
        .alert-item {{
            background: #1A1A2E; border-radius: 8px; padding: 12px 16px;
            margin-bottom: 8px; display: flex; align-items: center; gap: 12px;
            border-left: 4px solid #FFD100;
        }}
        .alert-critical {{ border-left-color: #FF1744; }}
        .alert-warning {{ border-left-color: #FF9100; }}
        .alert-ok {{ border-left-color: #00C853; }}
        .alert-icon {{ font-size: 1.2rem; }}
        .alert-text {{ flex: 1; }}
        .alert-direction {{ color: #FF9100; font-weight: 600; }}

        /* Stats list */
        .stats-card {{
            background: #1A1A2E; border-radius: 12px; padding: 16px;
            border: 1px solid #2A2A4E; margin-bottom: 16px;
        }}
        .stats-card h3 {{ color: #FFD100; margin-bottom: 12px; font-size: 1rem; }}
        .stat-row {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 8px 0; border-bottom: 1px solid #2A2A4E;
        }}
        .stat-row:last-child {{ border-bottom: none; }}
        .stat-value {{ color: #FFD100; font-weight: 600; }}
        .stat-score {{ color: #00C853; font-weight: 600; }}
        .stat-rank {{ color: #888; width: 30px; }}

        /* Footer */
        .footer {{
            text-align: center; padding: 20px; color: #555;
            font-size: 0.8rem; border-top: 1px solid #2A2A4E; margin-top: 24px;
        }}

        /* Tags */
        .tag {{
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.75rem; font-weight: 600;
        }}
        .tag-up {{ background: #00C85333; color: #00C853; }}
        .tag-down {{ background: #FF174433; color: #FF1744; }}

        @media (max-width: 768px) {{
            .chart-row {{ grid-template-columns: 1fr; }}
            .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>📊 美团数据看板</h1>
            <span class="date">更新于 {latest_date} · 每日 09:00 自动更新</span>
        </div>

        <!-- KPI -->
        <div class="kpi-row">
            <div class="kpi-card">
                <div class="kpi-value">{store_count}</div>
                <div class="kpi-label">🏪 营业门店</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{total_orders:,}</div>
                <div class="kpi-label">📦 总订单 (30天)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">¥{total_revenue/10000:.0f}万</div>
                <div class="kpi-label">💰 总销售额 (30天)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{total_checkins:,}</div>
                <div class="kpi-label">💳 总核销 (30天)</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{refund_rate}%</div>
                <div class="kpi-label">🔙 退款率</div>
            </div>
        </div>

        <!-- Alerts -->
        <h2 style="color:#FFD100; margin-bottom:12px;">🔔 异动检测</h2>
        <div class="alert-list">{alert_items}</div>

        <!-- Charts -->
        <div class="chart-row">
            <div class="chart-card chart-full">{charts_html.split('chart-revenue')[0]}<div id="chart-revenue"></div></div>
        </div>

        <!-- Side by side -->
        <div class="chart-row">
            <div class="chart-card"><div id="chart-orders"></div></div>
            <div class="chart-card"><div id="chart-city"></div></div>
        </div>

        <div class="chart-row">
            <div class="chart-card chart-full"><div id="chart-scores"></div></div>
        </div>

        <!-- Stats -->
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:24px;">
            <div class="stats-card">
                <h3>🌆 城市排行</h3>
                {city_rows}
            </div>
            <div class="stats-card">
                <h3>🏆 健康分 TOP 5</h3>
                {score_rows}
            </div>
        </div>

        <div class="footer">
            美团数据看板 · 由 GitHub Actions 自动生成 · 数据来源：模拟样本
        </div>
    </div>

    <script>
        // Inject chart data
        var charts = {json.dumps(charts_html)};
    </script>
</body>
</html>"""

# 写入 index.html
OUTPUT_DIR = os.path.join(PROJECT_DIR, "_site")
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ HTML 看板生成完成: _site/index.html")
print(f"📊 200 家门店 · 30 天数据 · {len(all_alerts)} 项异常")
