# Dashboard Petem 🐾

自动化监控工具箱 — 定时跑在 GitHub Actions 上，不依赖本地电脑。

## 已部署的任务

### 📈 NASDAQ 回撤监控
- ⏰ 每天 **北京时间 08:00** 自动运行
- 📊 获取纳斯达克综合指数近6个月数据
- 🔔 回撤超过 **8%** 时发送飞书警报
- 🔧 可在 `.github/workflows/nasdaq-monitor.yml` 中调整阈值

## 配置

### 飞书机器人通知（可选）
如需要收到飞书通知，在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret | 说明 |
|--------|------|
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 webhook 地址 |

> 没有配置 webhook 时，可以在 Actions 运行日志中查看结果。

## 手动触发
在 GitHub 仓库 → Actions → 对应 workflow → "Run workflow" 即可手动执行。
