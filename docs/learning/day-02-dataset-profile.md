# Day 2：统一 Dataset Profile

## 今天只解决一个问题

Planner 在制定分析计划前，需要先知道数据有多少行、有哪些字段、字段是什么类型、是否存在缺失值。

CSV 和 XLSX 的读取方式不同，但上层 Agent 不应该关心文件格式。因此 Dataset 模块对外只暴露一个入口：

```python
profile_dataset(path) -> DatasetProfile
```

## 三个核心知识点

### 1. DataFrame 是内存中的二维表

Pandas 将 CSV 或 XLSX 加载为 `DataFrame`。每一列是 `Series`，包含字段名、数据类型和值。

DataFrame 只在 Dataset 模块内部短暂存在，不会放进未来的 `AgentState`。Agent 只接收体积较小、可以序列化的 `DatasetProfile`。

### 2. 不同文件要收敛为同一个 Contract

`DatasetProfile` 包含：

- 文件名与文件类型
- 行数与列数
- 每个字段的数据类型
- 缺失数量与缺失比例
- 非空唯一值数量
- 数值字段的最小值、最大值和平均值

CSV 和 XLSX 最终都返回这个结构。以后 Planner 不需要写两套逻辑。

### 3. Profile 是摘要，不是原始数据

Profile 的作用是帮助 Agent 理解数据结构，不应复制整张表。这样可以控制 checkpoint 大小，也能避免把大量原始数据直接发送给模型。

## 推荐阅读顺序

1. `tests/unit/test_dataset_profile.py`
2. `src/datapilot/dataset.py` 中的 `profile_dataset`
3. `DatasetProfile` 和 `ColumnProfile`
4. `_profile_column`
5. `_classify_dtype`

先看测试，可以先知道模块承诺了什么；以下划线开头的函数属于内部实现，不是上层模块依赖的接口。

## 运行示例

在 PyCharm Python Console 中运行：

```python
from datapilot.dataset import profile_dataset

profile = profile_dataset("data/samples/sales_demo.csv")
print(profile.model_dump_json(indent=2))
```

观察结果：

- 总共有 5 行、5 列。
- `cost` 有一个缺失值。
- `revenue` 和 `cost` 被识别为数值字段。
- CSV 中的 `order_date` 暂时是字符串；今天不猜测日期格式，避免错误推断。

## 动手练习

在 `sales_demo.csv` 中增加一行数据，然后再次生成 Profile，并回答：

1. 哪些统计值发生了变化？
2. 为什么缺失比例的分母是总行数？
3. 为什么 `unique_count` 不计算空值？
4. 为什么 Planner 应依赖 `DatasetProfile`，而不是直接依赖 Pandas？

进阶练习：创建一个简单的 XLSX 文件，使用同一个 `profile_dataset` 读取它，比较两者返回的数据结构。

## 验收命令

```powershell
uv run pytest tests/unit/test_dataset_profile.py -q
uv run python scripts/check_quality.py
```

理解今天的代码后，再进入 Day 3 的 DuckDB 查询与只读 SQL Guardrail。
