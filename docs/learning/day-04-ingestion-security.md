# Day 4：安全上传与数据入库

## 今天完成什么

这一阶段只解决一件事：把用户上传的数据文件安全地放进 DataPilot，并生成可追踪的数据库记录。

完整顺序如下：

```text
客户端文件名
  → 文件名与扩展名校验
  → 分块写入 .uploading
  → 同步计算大小和 SHA-256
  → 查重
  → 原子改名为 source.<扩展名>
  → 写入 datasets 表
```

## 建议阅读顺序

1. `src/datapilot/security/paths.py`
2. `tests/unit/test_path_security.py`
3. `src/datapilot/services/datasets.py`
4. `tests/unit/test_dataset_service.py`
5. `src/datapilot/domain/models.py` 中的 `DatasetIngestResult`

先读测试，再回到实现观察每条安全规则如何被验证。

## 三个关键设计

### 1. 客户端只能提供文件名

`validate_client_filename()` 拒绝 `/`、`\\`、`..` 等路径成分。服务端自己生成目录和最终文件名，因此用户不能决定文件写到哪里。

`resolve_under_root()` 在路径规范化后再调用 `relative_to()`。这比判断字符串是否以某个前缀开头可靠，因为 `data-other` 并不属于 `data`。

### 2. 文件先临时写入，再原子发布

上传期间的目标叫 `.uploading`。只有大小、类型和内容都通过后，`os.replace()` 才把它改名成最终文件。其他代码不会误把半个文件当作完整数据集。

### 3. 哈希既用于完整性，也用于去重

服务在接收每个数据块时同时更新 SHA-256，不需要再次读取整个文件。相同内容即使文件名不同，也会复用第一次入库的 `DatasetRecord`，并删除第二份临时内容。

数据库的唯一约束负责处理两个请求同时上传同一内容的极端情况。

## 动手练习

运行本阶段测试：

```powershell
uv run pytest tests/unit/test_path_security.py tests/unit/test_dataset_service.py -q
```

建议做两个小改动观察测试失败：

1. 暂时删除 `size > self.max_upload_bytes` 判断，运行超限测试，然后还原。
2. 暂时把 `stored_path` 改成绝对路径，运行入库测试，然后还原。

最后运行完整门禁：

```powershell
uv run python scripts/check_quality.py
```

## 今天暂时不做什么

- 不解析 CSV/XLSX/SQLite 的内容。
- 不生成 profile 或预览。
- 不接 FastAPI 上传接口。
- 不启动 MCP Server。

这些会在后续学习切片中建立在当前安全存储层之上。
