# Day 3：SQLite 表结构与仓储层

## 今天的目标

理解数据如何从领域对象变成数据库行，再由仓储还原成领域对象。本轮不处理上传文件，也不运行
LangGraph。

## 阅读顺序

1. `src/datapilot/persistence/models.py`
2. `src/datapilot/persistence/database.py`
3. `src/datapilot/persistence/repositories.py`
4. `tests/unit/test_persistence.py`

## 三层职责

```text
Domain Record        Repository             SQLAlchemy Row
稳定业务字段    <->   查询与转换边界    <->   表、索引、外键和约束
```

- Domain Record 不知道 SQLite 和 SQLAlchemy，便于 API、Agent 与测试复用。
- SQLAlchemy Row 只描述如何持久化，不承担业务流程。
- Repository 集中处理查询和转换，调用者不拼 SQL。

## 重点设计

### 1. 为什么打开 SQLite 外键

SQLite 默认可能不执行外键约束。每次连接显式运行 `PRAGMA foreign_keys=ON`，才能保证不存在的
`dataset_id` 无法创建任务。

### 2. 为什么会话自动提交和回滚

`Database.session()` 将一次仓储操作包在同一事务里。成功就提交，任何异常都回滚，避免半成品数据。

### 3. 为什么任务状态更新带 `expected`

`WHERE id=? AND status=?` 把“检查旧状态”和“写新状态”放进同一条 SQL。两个请求同时推进任务时，
只有一个能成功。

### 4. 为什么事件有连续 sequence

WebSocket 重连时，前端使用 `after_sequence` 只补发遗漏事件，不依赖不稳定的时间戳排序。

## 动手练习

1. 在测试中创建没有 Dataset 的 Task，观察外键错误。
2. 把一次状态迁移的 `expected` 改错，观察返回值从 `True` 变为 `False`。
3. 连续写入三个事件，用 `after_sequence=1` 验证只返回第 2、3 个。

## 验收命令

```powershell
uv run pytest tests/unit/test_persistence.py -q
uv run python scripts/check_quality.py
```

