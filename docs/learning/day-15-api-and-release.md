# Day 15：API、CLI 与发布

`TaskService` 是最终应用层：它组合 Workflow、上传目录、Artifact Store 和 Trace。FastAPI 与 CLI 只调用这个接口，不直接拼 LangGraph 节点。

最终 HTTP 路径：

- `POST /api/datasets`：上传并按 SHA-256 去重；
- `POST /api/tasks`：创建任务并运行到审批中断；
- `POST /api/tasks/{id}/approval`：approve、revise 或 reject；
- `GET /api/tasks/{id}`：读取 checkpoint 状态；
- `GET /api/tasks/{id}/trace`：查看安全轨迹；
- `GET /api/tasks/{id}/artifacts/{artifact_id}`：下载证据或报告。

发布前执行 `uv run python scripts/check_quality.py`。它依次检查格式、静态规则、类型和全量测试。CI 不读取本地 `.env`，所以不会消耗真实模型额度。

练习：用 `tests/integration/test_task_api.py` 走一遍“上传—计划—批准—执行—审核—报告”，并在断点中观察每层只依赖下一层的小接口。
