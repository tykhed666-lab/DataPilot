# Day 3：DuckDB 只读查询与 SQL Guardrail

## 今天只解决一个问题

昨天的 Profile 只能告诉 Planner 数据长什么样，不能回答“哪个区域收入最高”。今天为 Dataset 模块增加第二个公开入口：

```python
query_dataset(path, sql, max_rows=1000) -> QueryResult
```

CSV 和 XLSX 都会被注册成 DuckDB 中名为 `dataset` 的临时表。上层只需要生成针对该表的 SQL。

## 四个核心知识点

### 1. DuckDB 是进程内分析数据库

DataPilot 不需要启动独立数据库服务。代码为每次查询创建内存连接，将 Pandas DataFrame 注册为 `dataset` 表，查询结束后关闭连接。

这也是为什么虚拟机中的 MySQL、MongoDB 和 Milvus 不属于当前主线：这里解决的是单文件分析，而不是生产数据平台。

### 2. SQL 必须先解析，再执行

只检查 SQL 是否以 `SELECT` 开头是不够的。例如下面仍然会读取任意本机文件：

```sql
SELECT * FROM read_csv_auto('private.csv')
```

DataPilot 使用 SQLGlot 将 SQL 转为抽象语法树（AST），然后检查：

- 只能有一条语句；
- 根节点必须是 SELECT，WITH 最终也必须产生 SELECT；
- 只能读取 `dataset` 或当前语句定义的 CTE；
- DELETE、COPY、ATTACH 和外部文件表函数都会被拒绝。

### 3. 行数上限由系统强制执行

不能相信模型一定会写 LIMIT。通过校验的 SQL 会被包在外层查询中：

```sql
SELECT *
FROM (<validated query>) AS datapilot_result
LIMIT <max_rows + 1>
```

多取的一行不会返回给调用者，只用于判断 `truncated` 是否为 `true`。这样 Executor 能知道结果不是完整集合。

### 4. QueryResult 是工具友好的结果

DuckDB 可能返回 `date`、`Decimal` 等 Python 对象。Dataset 模块会将它们转换为 ISO 日期字符串和普通数字，使结果可以安全进入 JSON、图表准备步骤和未来的 MCP 工具响应。

完整 DataFrame 和无限制查询结果仍然不能进入 AgentState。

## 推荐阅读顺序

1. `tests/unit/test_dataset_query.py`
2. `src/datapilot/dataset.py` 中的 `QueryResult`
3. `query_dataset`
4. `_validate_read_only_query`
5. `_to_json_scalar`
6. `_load_frame`

## 运行示例

在 PyCharm Python Console 中运行：

```python
from datapilot.dataset import query_dataset

result = query_dataset(
    "data/samples/sales_demo.csv",
    """
    SELECT region, SUM(revenue) AS total_revenue
    FROM dataset
    GROUP BY region
    ORDER BY total_revenue DESC
    """,
)
print(result.model_dump_json(indent=2))
```

## 动手练习

1. 将查询改为计算每个区域的平均收入。
2. 使用 CTE 先计算 `profit = revenue - cost`，再按区域汇总。
3. 把 `max_rows` 设置为 2，观察 `truncated`。
4. 分别尝试 DELETE 和 `read_csv_auto()`，观察 `UnsafeQueryError`。

思考题：为什么“数据库是内存数据库”仍然不能代替 SQL Guardrail？

## 验收命令

```powershell
uv run pytest tests/unit/test_dataset_query.py -q
uv run python scripts/check_quality.py
```

理解今天的代码后，再进入 Day 4 的 Tool Contract、Registry 与工具输入输出 Guardrail。
