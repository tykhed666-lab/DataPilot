"use strict";

const STORAGE_KEY = "datapilot.currentTaskId";
const state = {
  datasetId: null,
  taskId: localStorage.getItem(STORAGE_KEY),
  planVersion: null,
  taskStatus: null,
  busy: false,
};

const byId = (id) => document.getElementById(id);
const elements = {
  serviceStatus: byId("service-status"),
  datasetFile: byId("dataset-file"),
  uploadButton: byId("upload-button"),
  uploadMeta: byId("upload-meta"),
  question: byId("question"),
  createTaskButton: byId("create-task-button"),
  clearTaskButton: byId("clear-task-button"),
  taskIdentity: byId("task-identity"),
  taskStatus: byId("task-status"),
  profilePanel: byId("profile-panel"),
  profileMetrics: byId("profile-metrics"),
  planPanel: byId("plan-panel"),
  planVersion: byId("plan-version"),
  planList: byId("plan-list"),
  finalDeliverable: byId("final-deliverable"),
  revisionFeedback: byId("revision-feedback"),
  approveButton: byId("approve-button"),
  reviseButton: byId("revise-button"),
  rejectButton: byId("reject-button"),
  emptyResult: byId("empty-result"),
  resultContent: byId("result-content"),
  answerOutput: byId("answer-output"),
  findingsOutput: byId("findings-output"),
  caveatsOutput: byId("caveats-output"),
  reportOutput: byId("report-output"),
  reportDownload: byId("report-download"),
  traceOutput: byId("trace-output"),
  message: byId("message"),
};

function showMessage(text, isError = false) {
  elements.message.textContent = text;
  elements.message.classList.toggle("message-error", isError);
  elements.message.hidden = false;
  window.clearTimeout(showMessage.timer);
  showMessage.timer = window.setTimeout(() => { elements.message.hidden = true; }, 4500);
}

function setBusy(busy, message = "") {
  state.busy = busy;
  elements.uploadButton.disabled = busy;
  elements.createTaskButton.disabled = busy;
  const approvalDisabled = busy || state.taskStatus !== "awaiting_approval";
  [elements.approveButton, elements.reviseButton, elements.rejectButton].forEach((button) => {
    button.disabled = approvalDisabled;
  });
  if (message) showMessage(message);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" ? payload.message || payload.detail : payload;
    const requestId = typeof payload === "object" ? payload.request_id : null;
    throw new Error(`${detail || `请求失败 (${response.status})`}${requestId ? ` · ${requestId}` : ""}`);
  }
  return payload;
}

function replaceList(target, values, emptyText = "无") {
  target.replaceChildren();
  const items = values && values.length ? values : [emptyText];
  items.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = String(value);
    target.appendChild(item);
  });
}

function setStatus(status) {
  state.taskStatus = status || null;
  elements.taskStatus.textContent = status || "未知";
  elements.taskStatus.className = "status-pill";
  if (status === "completed") elements.taskStatus.classList.add("status-success");
  else if (["failed", "rejected"].includes(status)) elements.taskStatus.classList.add("status-error");
  else if (status) elements.taskStatus.classList.add("status-active");
  else elements.taskStatus.classList.add("status-muted");
}

function renderProfile(profile) {
  elements.profileMetrics.replaceChildren();
  elements.profilePanel.hidden = !profile;
  if (!profile) return;
  const metrics = [
    ["数据行数", profile.row_count],
    ["字段数量", profile.column_count],
    ["字段示例", (profile.columns || []).slice(0, 3).map((item) => item.name).join("、") || "无"],
  ];
  metrics.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "metric";
    const caption = document.createElement("span");
    caption.textContent = String(label);
    const strong = document.createElement("strong");
    strong.textContent = String(value ?? "-");
    card.append(caption, strong);
    elements.profileMetrics.appendChild(card);
  });
}

function renderPlan(task) {
  const plan = task.plan;
  elements.planPanel.hidden = !plan;
  elements.planList.replaceChildren();
  if (!plan) return;
  state.planVersion = task.plan_version;
  elements.planVersion.textContent = `版本 ${task.plan_version}`;
  elements.finalDeliverable.textContent = `预期交付：${plan.final_deliverable}`;
  (plan.steps || []).forEach((step) => {
    const item = document.createElement("li");
    item.className = "plan-item";
    const title = document.createElement("div");
    title.className = "plan-title";
    title.textContent = step.title;
    const tool = document.createElement("div");
    tool.className = "plan-tool";
    tool.textContent = `${step.tool_name} · ${step.expected_output}`;
    item.append(title, tool);
    elements.planList.appendChild(item);
  });
  const awaiting = task.status === "awaiting_approval" && !state.busy;
  elements.approveButton.disabled = !awaiting;
  elements.reviseButton.disabled = !awaiting;
  elements.rejectButton.disabled = !awaiting;
}

function renderReview(review) {
  const visible = Boolean(review && review.answer);
  elements.emptyResult.hidden = visible;
  elements.resultContent.hidden = !visible;
  if (!visible) return;
  elements.answerOutput.textContent = review.answer;
  replaceList(elements.findingsOutput, review.key_findings);
  replaceList(elements.caveatsOutput, review.caveats);
}

async function loadReportAndTrace(task) {
  if (!state.taskId) return;
  const report = (task.artifacts || []).find((item) => item.kind === "markdown_report");
  if (report) {
    const path = `/api/tasks/${encodeURIComponent(state.taskId)}/artifacts/${encodeURIComponent(report.artifact_id)}`;
    elements.reportOutput.textContent = await api(path);
    elements.reportDownload.href = path;
    elements.reportDownload.download = `datapilot-${state.taskId}.md`;
    elements.reportDownload.hidden = false;
  } else {
    elements.reportOutput.textContent = "当前任务还没有生成报告。";
    elements.reportDownload.hidden = true;
  }

  const trace = await api(`/api/tasks/${encodeURIComponent(state.taskId)}/trace`);
  elements.traceOutput.replaceChildren();
  trace.forEach((event) => {
    const item = document.createElement("li");
    item.className = "trace-item";
    item.textContent = `#${event.sequence} · ${event.kind} · ${event.name} · ${event.status} · ${event.duration_ms}ms`;
    elements.traceOutput.appendChild(item);
  });
}

async function renderTask(task) {
  state.taskId = task.task_id;
  localStorage.setItem(STORAGE_KEY, task.task_id);
  elements.taskIdentity.textContent = `任务 ${task.task_id}`;
  setStatus(task.status);
  renderProfile(task.profile);
  renderPlan(task);
  renderReview(task.review);
  if (["completed", "failed", "rejected"].includes(task.status)) {
    await loadReportAndTrace(task);
  }
  if (task.error) showMessage(`任务错误：${task.error}`, true);
}

async function uploadDataset() {
  const file = elements.datasetFile.files[0];
  if (!file) return showMessage("请先选择 CSV 或 XLSX 文件。", true);
  const body = new FormData();
  body.append("file", file);
  setBusy(true, "正在上传数据集……");
  try {
    const uploaded = await api("/api/datasets", { method: "POST", body });
    state.datasetId = uploaded.dataset_id;
    elements.uploadMeta.textContent = `已上传：${uploaded.file_name} · ${uploaded.size_bytes} 字节`;
    showMessage("数据集上传成功。先输入问题，再创建任务。");
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function createTask() {
  const question = elements.question.value.trim();
  if (!state.datasetId) return showMessage("请先上传数据集。", true);
  if (!question) return showMessage("请输入分析问题。", true);
  setBusy(true, "Planner 正在生成分析计划……");
  try {
    const task = await api("/api/tasks", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ dataset_id: state.datasetId, question }),
    });
    await renderTask(task);
    showMessage("计划已生成，请检查后批准、修改或拒绝。");
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function submitApproval(decision) {
  if (!state.taskId || !state.planVersion) return;
  const feedback = elements.revisionFeedback.value.trim();
  if (decision === "revise" && !feedback) {
    return showMessage("要求修改时必须填写修改意见。", true);
  }
  const payload = { decision, plan_version: state.planVersion };
  if (feedback) payload.feedback = feedback;
  setBusy(true, decision === "approve" ? "Agent 正在执行、审核并生成报告……" : "正在提交决定……");
  try {
    const task = await api(`/api/tasks/${encodeURIComponent(state.taskId)}/approval`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    elements.revisionFeedback.value = "";
    await renderTask(task);
    showMessage(task.status === "completed" ? "分析完成。" : `任务状态：${task.status}`);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function restoreTask() {
  if (!state.taskId) return;
  try {
    const task = await api(`/api/tasks/${encodeURIComponent(state.taskId)}`);
    await renderTask(task);
    showMessage("已恢复上次任务。")
  } catch (error) {
    localStorage.removeItem(STORAGE_KEY);
    state.taskId = null;
    showMessage(`无法恢复上次任务：${error.message}`, true);
  }
}

function clearTask() {
  localStorage.removeItem(STORAGE_KEY);
  window.location.reload();
}

async function initialize() {
  try {
    const health = await api("/health/live");
    elements.serviceStatus.textContent = `服务正常 · v${health.version}`;
    elements.serviceStatus.className = "status-pill status-success";
  } catch (error) {
    elements.serviceStatus.textContent = "服务异常";
    elements.serviceStatus.className = "status-pill status-error";
  }
  await restoreTask();
}

elements.uploadButton.addEventListener("click", uploadDataset);
elements.createTaskButton.addEventListener("click", createTask);
elements.approveButton.addEventListener("click", () => submitApproval("approve"));
elements.reviseButton.addEventListener("click", () => submitApproval("revise"));
elements.rejectButton.addEventListener("click", () => submitApproval("reject"));
elements.clearTaskButton.addEventListener("click", clearTask);
initialize();
