# DataPilot

DataPilot 是一个面向 CSV、Excel 与 SQLite 的安全、可审计数据分析智能体。

当前仓库只完成了“Day 1 开发底座”，业务功能会按每日学习切片逐步加入。

## 本地环境

- Python 3.11.9
- uv 0.12+
- 虚拟环境：`D:\DataPilot\.venv`

首次安装或更新依赖：

```powershell
uv sync --python 3.11
```

启动最小 API：

```powershell
uv run uvicorn datapilot.api.app:app --reload
```

打开 <http://127.0.0.1:8000/health/live>，应看到服务状态和版本号。

运行测试与质量检查：

```powershell
uv run pytest
uv run ruff check .
uv run pyright src
uv run python scripts/check_quality.py
```

学习说明见 [`docs/learning/day-01-foundation.md`](docs/learning/day-01-foundation.md)。

