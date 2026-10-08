# Day 15：应用 seam、答案型报告、冷启动与发布

## 今天完成了什么

前十四天的模块已经能单独工作，最后一天把它们组合成面试官可以运行的完整应用：

```text
FastAPI / CLI
  → TaskService
  → AgentWorkflow
  → Dataset Tools + Planner + Reviewer
  → Checkpoint + Artifact Store + Trace
  → Grounded Answer + Markdown Report
```

同时完成版本号、README、架构说明、面试指南、CI、公开仓库和 Release。

v1.1 在这条 seam 上增加一个不需要 Node 构建的 Web Workbench。它是操作 Adapter，不把分析逻辑搬进浏览器。

## 1. 为什么增加 TaskService

如果 FastAPI 路由直接创建模型、打开 SQLite、拼 Workflow 和处理路径，CLI 就必须复制同样代码，测试也会依赖 HTTP 细节。

`TaskService` 提供少量接口：

- `upload_dataset()`
- `create_task()`
- `approve_task()`
- `get_task()`
- `get_trace()`
- `load_artifact()`

它隐藏上传目录、Workflow 恢复参数、Artifact 查找和 Trace 读取。FastAPI 与 CLI 是两个不同 Adapter，共用同一个应用 seam。

## 2. 上传如何处理

上传模块执行：

1. 检查 `.csv` 或 `.xlsx`；
2. 拒绝空文件和超限文件；
3. 计算 SHA-256；
4. 保存为 `uploads/<sha256>.<suffix>`；
5. 相同内容直接复用；
6. 返回不含绝对路径的 `DatasetUpload`。

原始文件名只用于显示，不参与磁盘目标路径，降低路径穿越风险。

## 3. FastAPI 路径

```text
POST /api/datasets
POST /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/approval
GET  /api/tasks/{task_id}/trace
GET  /api/tasks/{task_id}/artifacts/{artifact_id}
```

创建任务会运行到审批暂停点，而不是在 HTTP 请求中自动批准。过期 `plan_version` 返回 409。

### 轻量 Web Workbench

访问根路径 `/` 可以完成上传、提问、查看计划、approve/revise/reject、查看答案、报告和 Trace。页面由 FastAPI 同源提供：

```text
src/datapilot/api/static/
├── index.html
├── app.css
└── app.js
```

它使用原生 HTML/CSS/JavaScript，不引入 React、npm 或 CDN。所有不可信内容通过 `textContent` 渲染，浏览器只保存最近的 `task_id`，不会接触模型 API Key。

## 4. 统一错误格式

应用错误统一为：

```json
{
  "error_type": "...",
  "code": "...",
  "message": "...",
  "request_id": "...",
  "details": []
}
```

它不会向调用方暴露 traceback 或本机绝对路径。Pydantic 请求错误也映射到同一形状。

## 5. 报告为什么必须先有答案

原始 JSON 是证据，不是回答。报告主结构是：

```text
问题
直接答案
预期交付
关键发现
注意事项
执行计划
证据附录
审核结论
```

`AnalysisPlan.final_deliverable` 明确展示用户批准的交付目标；`GroundedReview.answer` 是执行后基于真实证据产生的答案。两者不能互相替代。

原始 ToolEnvelope 只放在证据附录，方便审计，而不是要求用户自己阅读 JSON 得出结论。

## 6. 为什么报告节点不再调用模型

语义 Reviewer 已经读取受限证据并产出结构化答案。报告节点只做确定性渲染：

- 不会在最后一步再次产生未经审核的新事实；
- 测试可以精确检查答案和引用；
- 模型成本和失败点更少；
- Markdown 模板可以独立演进。

如果未来需要更丰富文风，可以增加 ReportWriter，但它不能改变已审核的数字和结论。

## 7. CLI 演示

```powershell
uv run datapilot-demo examples/sales_demo.csv "各区域总收入是多少？" --auto-approve
```

`--auto-approve` 只用于本地演示。正式 API 仍要求显式审批请求。

CLI 和 API 都需要 `.env` 中配置 OpenAI-compatible 模型；自动测试使用 Fake Model，不消耗真实额度。

## 8. 应用生命周期

FastAPI lifespan 在启动时：

- 读取 Settings；
- 创建真实模型 Adapter；
- 构建 Registry、Artifact Store 和 Trace；
- 打开 SQLite Checkpointer；
- 图只编译一次。

应用关闭时统一关闭 SQLite 连接。缺少模型配置时健康接口仍可用，任务接口返回明确的服务不可用错误。

## 9. 端到端测试

`test_task_api.py` 通过公开 HTTP seam 完成：

1. 上传 CSV；
2. 创建任务；
3. 验证暂停等待审批；
4. 批准计划；
5. 执行 SQL；
6. 确定性复算；
7. 语义审核产生答案；
8. 生成报告；
9. 下载报告并检查直接答案、预期交付、关键发现和注意事项；
10. 检查完整 Trace。

这个测试不会访问真实模型，但走过真实 Workflow、Dataset、Artifact、Trace 和 HTTP Adapter。

## 10. 质量门禁

统一命令：

```powershell
uv run python scripts/check_quality.py
```

依次执行：

- Ruff 格式检查；
- Ruff 静态规则；
- Pyright；
- Pytest。

覆盖率单独验证核心包不低于 80%。GitHub Actions 使用锁文件和 Python 3.11，不读取本地 `.env`。

## 11. 冷启动验收

发布不能只在开发目录里成功。冷启动步骤是：

```text
新的纯英文目录
  → clone tag
  → uv sync --locked
  → health check
  → 完整演示
```

Windows 用户应优先使用 `E:\DataPilot` 这类纯英文路径，避免部分 Python 包或 `.pth` 文件受系统编码影响。

## 12. 发布内容

v1.0 发布包括：

- 公开 GitHub 仓库；
- `v1.0.0` tag 和 Release；
- MIT License；
- CHANGELOG；
- README 快速启动；
- 架构文档；
- Day 1～15 学习文档；
- 面试讲解指南。

发布前必须确认 `.env`、上传数据、SQLite、checkpoint、trace 和 artifacts 均未进入 Git。

## 阅读顺序

1. `tests/integration/test_task_api.py`
2. `src/datapilot/service.py`
3. `src/datapilot/api/app.py`
4. `src/datapilot/cli.py`
5. `src/datapilot/agent/workflow.py` 的 `_report_node`
6. `.github/workflows/quality.yml`
7. `README.md` 与 `docs/interview-guide.md`

## 练习

### 练习 1：手工走 API

在 Swagger 中上传数据、创建任务、复制 task_id、批准计划并下载报告。

### 练习 2：检查答案质量

把 Fake Reviewer 的答案删掉，观察结构化输出校验如何阻止一个“通过但无答案”的任务完成。

### 练习 3：过期审批

对 plan version 2 提交 version 1 的批准请求，验证返回 409，并说明它解决了什么并发问题。

### 练习 4：冷启动

在新的纯英文目录 clone Release tag，只按 README 操作，记录任何隐含步骤并反向修正文档。

## 面试表达

> 最终应用不是把路由堆在 Workflow 外面，而是用 TaskService 建立稳定 seam；报告把经过审核的自然语言答案放在前面，把原始工具结果放在可追溯附录中。

## v1.0 明确局限

- 单用户、单进程学习型后端；
- 没有认证、权限和多租户；
- SQLite 不用于高并发分布式执行；
- MCP Server 尚未作为 Workflow 的远程 Adapter；
- 只有轻量操作工作台，没有前端框架、复杂图表和后台任务队列；
- 真实模型质量需要用户自行配置并评测。

第 15 天的核心不是“把项目打包”，而是证明所有模块通过一个可运行、可测试、可解释的应用 seam 连成了真正回答用户问题的闭环。
