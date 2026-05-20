"""
美团 Dashboard - 数据分析模块
异动检测、趋势分析、上新预测
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from db import get_daily, get_stores, get_city_summary


# ─── 异动检测 ───

def detect_anomalies(
    df: pd.DataFrame,
    metric: str = "foot_traffic",
    z_threshold: float = 2.0,
    window: int = 7,
) -> pd.DataFrame:
    """
    基于滑动窗口 Z-Score 检测异常值
    返回标记了异常的 DataFrame
    """
    if df.empty or metric not in df.columns:
        return pd.DataFrame()

    result = df.copy()
    result["_date_sort"] = pd.to_datetime(result["date"])
    result = result.sort_values(["store_id", "_date_sort"]).reset_index(drop=True)

    anomalies = []
    for store_id, group in result.groupby("store_id"):
        group = group.sort_values("_date_sort")
        values = group[metric].fillna(0)

        # 滑动窗口均值和标准差
        rolling_mean = values.rolling(window=window, min_periods=3).mean()
        rolling_std = values.rolling(window=window, min_periods=3).std()
        z_scores = (values - rolling_mean) / rolling_std.replace(0, np.nan)

        is_anomaly = z_scores.abs() > z_threshold
        direction = z_scores.apply(lambda x: "大涨" if x > z_threshold else ("大跌" if x < -z_threshold else ""))

        anomalies.append(
            pd.DataFrame({
                "store_id": group["store_id"],
                "store_name": group["store_name"],
                "city": group["city"],
                "date": group["date"],
                metric: values,
                "rolling_mean": rolling_mean.round(0),
                "z_score": z_scores.round(2),
                "is_anomaly": is_anomaly,
                "direction": direction,
            })
        )

    if anomalies:
        result = pd.concat(anomalies, ignore_index=True)
    else:
        result["is_anomaly"] = False
        result["direction"] = ""
        result["z_score"] = 0.0

    return result


# ─── 趋势分析 ───

def trend_analysis(df: pd.DataFrame, metric: str = "deal_revenue", window: int = 7) -> dict:
    """
    趋势分析：周环比、日均值、增长率
    """
    if df.empty or metric not in df.columns:
        return {}

    df = df.copy()
    df["_date"] = pd.to_datetime(df["date"])
    df = df.sort_values("_date")

    recent = df.tail(window)
    prev = df.tail(window * 2).head(window)

    current_avg = recent[metric].mean()
    prev_avg = prev[metric].mean()
    growth = ((current_avg - prev_avg) / prev_avg * 100) if prev_avg else 0

    return {
        "current_avg": round(current_avg, 2),
        "prev_avg": round(prev_avg, 2),
        "growth_pct": round(growth, 1),
        "trend": "上升 📈" if growth > 5 else ("下降 📉" if growth < -5 else "平稳 ➡️"),
    }


# ─── 预测建议 ───

def predict_new_deals(df: pd.DataFrame) -> dict:
    """
    基于历史销售数据，预测应该上新的品类和价位
    分析维度：
    1. 各品类销量趋势和增长
    2. 客单价分布与热力图
    3. 建议上新的方向
    """
    if df.empty:
        return {"suggestions": [], "categories": pd.DataFrame()}

    # 分析品类表现（如果有品类数据）
    category_analysis = pd.DataFrame()

    if "category" in df.columns and df["category"].notna().any():
        cat_stats = df.groupby("category").agg(
            total_sales=("daily_sales", "sum"),
            avg_price=("deal_price", "mean"),
            total_deals=("deal_price", "count"),
            avg_daily_sales=("daily_sales", "mean"),
        ).reset_index()
        cat_stats["revenue_est"] = cat_stats["total_sales"] * cat_stats["avg_price"]
        cat_stats = cat_stats.sort_values("total_sales", ascending=False)
        category_analysis = cat_stats

    # 客单价热度区间分析
    price_analysis = pd.DataFrame()
    if "avg_price" in df.columns:
        price_bins = pd.cut(
            df["avg_price"].fillna(0),
            bins=[0, 50, 100, 200, 500, 1000, 5000],
            labels=["0-50", "50-100", "100-200", "200-500", "500-1000", "1000+"],
        )
        price_stats = df.groupby(price_bins, observed=True).agg(
            订单数=("deal_orders", "sum"),
            销售额=("deal_revenue", "sum"),
            门店数=("store_name", "nunique"),
        ).reset_index()
        price_stats.columns = ["价格区间", "订单数", "销售额", "门店数"]
        price_analysis = price_stats

    # 生成建议
    suggestions = []

    if not category_analysis.empty:
        top_cats = category_analysis.head(3)
        for _, row in top_cats.iterrows():
            suggestions.append(
                f"🔥 **{row['category']}** 表现优秀（日均销售 {row['avg_daily_sales']:.0f} 单，"
                f"均价 ¥{row['avg_price']:.0f}），建议持续推新"
            )

        # 增长潜力品类
        if len(category_analysis) > 1:
            low_perf = category_analysis.tail(2)
            for _, row in low_perf.iterrows():
                suggestions.append(
                    f"💡 **{row['category']}** 销量偏低（共 {row['total_sales']} 单），"
                    f"建议优化定价或下架换新"
                )

    if not price_analysis.empty:
        best_price = price_analysis.loc[price_analysis["订单数"].idxmax()]
        suggestions.append(
            f"💰 最热价格区间 **{best_price['价格区间']}元** "
            f"（{int(best_price['订单数'])} 单），上新可参考此价位"
        )

    if not suggestions:
        suggestions.append("📊 请先导入更多数据以获得上新建议")

    return {
        "suggestions": suggestions,
        "categories": category_analysis,
        "price_analysis": price_analysis,
    }


# ─── 门店健康度评分 ───

def store_health_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    门店综合健康度评分（0-100）
    维度：销量趋势、客流量、退款率、客单价
    """
    if df.empty:
        return pd.DataFrame()

    today = df["date"].max()
    recent_14d = df[df["date"] >= (pd.to_datetime(today) - pd.Timedelta(days=14)).strftime("%Y-%m-%d")]

    scores = []
    for store_id, group in recent_14d.groupby("store_id"):
        store_name = group["store_name"].iloc[0]
        city = group["city"].iloc[0]

        total_orders = group["deal_orders"].sum()
        total_traffic = group["foot_traffic"].sum()
        total_refunds = group["deal_refunds"].sum()
        total_revenue = group["deal_revenue"].sum()
        avg_price = group["avg_price"].mean()

        # 转换率评分 (订单/进店)
        conversion_rate = total_orders / total_traffic if total_traffic > 0 else 0
        conversion_score = min(conversion_rate * 200, 30)  # 最高30分

        # 销量评分
        sales_score = min(total_orders / 10, 25)  # 最高25分

        # 退款率评分（越低越好）
        refund_rate = total_refunds / total_orders if total_orders > 0 else 0
        refund_score = max(0, 20 - refund_rate * 200)  # 最高20分

        # 客单价评分
        price_score = min(avg_price / 20, 15) if avg_price else 10  # 最高15分

        # 稳定性评分
        daily_orders = group["deal_orders"].tolist()
        if len(daily_orders) > 1:
            volatility = np.std(daily_orders) / (np.mean(daily_orders) + 0.01)
            stability_score = max(0, 10 - volatility * 5)  # 最高10分
        else:
            stability_score = 5

        total_score = conversion_score + sales_score + refund_score + price_score + stability_score

        scores.append({
            "store_id": store_id,
            "store_name": store_name,
            "city": city,
            "score": round(min(total_score, 100), 1),
            "conversion_rate": round(conversion_rate * 100, 1),
            "refund_rate": round(refund_rate * 100, 1),
            "total_revenue": round(total_revenue, 2),
            "avg_price": round(avg_price, 2),
            "total_orders": int(total_orders),
            "total_traffic": int(total_traffic),
        })

    result = pd.DataFrame(scores).sort_values("score", ascending=False)
    return result


# ─── 品类增长分析（辅助上新决策） ───

def category_growth_analysis(deal_df: pd.DataFrame) -> pd.DataFrame:
    """
    分析各品类的增长趋势：最近7天 vs 前7天
    """
    if deal_df.empty or "category" not in deal_df.columns:
        return pd.DataFrame()

    deal_df = deal_df.copy()
    deal_df["_date"] = pd.to_datetime(deal_df["record_date"])
    latest = deal_df["_date"].max()
    mid = latest - pd.Timedelta(days=7)

    recent = deal_df[deal_df["_date"] > mid]
    prev = deal_df[(deal_df["_date"] <= mid) & (deal_df["_date"] > mid - pd.Timedelta(days=7))]

    if recent.empty or prev.empty:
        return pd.DataFrame()

    def agg_cat(df):
        return df.groupby("category").agg(
            sales=("daily_sales", "sum"),
            deals=("deal_price", "count"),
            avg_price=("deal_price", "mean"),
        )

    r = agg_cat(recent).rename(columns={"sales": "recent_sales", "deals": "recent_deals", "avg_price": "recent_price"})
    p = agg_cat(prev).rename(columns={"sales": "prev_sales", "deals": "prev_deals", "avg_price": "prev_price"})

    merged = r.join(p, how="outer").fillna(0)
    merged["growth_pct"] = ((merged["recent_sales"] - merged["prev_sales"]) / merged["prev_sales"].replace(0, 1) * 100).round(1)
    merged["growth_pct"] = merged["growth_pct"].replace(np.inf, 999)
    merged = merged.sort_values("growth_pct", ascending=False).reset_index()
    merged.columns = ["品类", "最近7天销量", "最近7天商品数", "均价", "前7天销量", "前7天商品数", "前均价", "增长率(%)"]

    return merged
