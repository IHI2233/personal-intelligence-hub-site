let intel = [];
const $ = selector => document.querySelector(selector);

const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

const safeHref = value => {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};

const statusClass = value => {
  if (value === "已验证") return "verified";
  if (value === "部分验证" || value === "待人工审核") return "partial";
  return "pending";
};

const statusLabel = item => item.verification || item.status || "状态未知";
const knowledgeClass = value => ({
  "已沉淀":"verified", "证据不足":"partial", "存在争议":"pending",
  "重复":"pending", "不适用":"pending", "写入失败":"pending", "待评估":"pending"
}[value] || "pending");

const listMarkup = item => {
  const source = safeHref(item.sourceUrl);
  const knowledge = safeHref(item.knowledgeUrl);
  return `<article class="intel-card" data-id="${escapeHtml(item.id)}">
    <div class="intel-icon">${escapeHtml((item.field || item.type || "情报").slice(0, 2))}</div>
    <div class="intel-body">
      <div class="intel-title">${escapeHtml(item.title)}</div>
      <p class="intel-summary">${escapeHtml(item.summary)}</p>
      <div class="intel-meta">
        <span>${escapeHtml(item.topic || item.field)}</span><span>·</span>
        <span>${escapeHtml(item.date || "日期未记录")}</span>
        <span class="tag ${statusClass(statusLabel(item))}">${escapeHtml(statusLabel(item))}</span>
        <span>${escapeHtml(item.sourceLevel || "来源等级未知")}</span>
        <span class="tag ${knowledgeClass(item.knowledgeStatus)}">知识：${escapeHtml(item.knowledgeStatus || "待评估")}</span>
        ${source ? `<a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">原始来源</a>` : ""}
        ${knowledge ? `<a href="${escapeHtml(knowledge)}" target="_blank" rel="noopener noreferrer">知识卡片</a>` : ""}
      </div>
    </div><span class="intel-arrow">›</span>
  </article>`;
};

function renderLists() {
  $("#featured-list").innerHTML = intel.slice(0, 3).map(listMarkup).join("") ||
    '<div class="panel">暂无公开情报记录。</div>';
  renderInbox();
  const count = intel.length;
  const navCount = document.querySelector(".nav-count");
  if (navCount) navCount.textContent = count;
  const pending = intel.filter(item => item.status !== "已归档" && item.status !== "忽略").length;
  const metrics = document.querySelectorAll(".metric-card strong");
  if (metrics[0]) metrics[0].textContent = String(pending).padStart(2, "0");
  if (metrics[1]) metrics[1].textContent = "03";
  if (metrics[2]) metrics[2].textContent = String(intel.filter(item => item.knowledgeStatus === "已沉淀").length).padStart(2, "0");
  if (metrics[3]) metrics[3].textContent = "29";
  renderKnowledgeSummary();
}

function renderKnowledgeSummary() {
  const target = $("#knowledge-summary");
  if (!target) return;
  const statuses = [["已沉淀", "verified"], ["证据不足", "partial"], ["存在争议", "pending"], ["待评估", "pending"]];
  target.innerHTML = statuses.map(([label, klass]) => {
    const count = intel.filter(item => (item.knowledgeStatus || "待评估") === label).length;
    return '<article class="knowledge-stat"><span class="tag ' + klass + '">' + label + '</span><strong>' + String(count).padStart(2, "0") + '</strong><small>条情报</small></article>';
  }).join("");
}

function renderInbox() {
  const filter = $("#status-filter")?.value || "all";
  const filtered = intel.filter(item => filter === "all" || statusClass(statusLabel(item)) === filter);
  $("#inbox-list").innerHTML = filtered.map(listMarkup).join("") ||
    '<div class="panel">当前筛选条件下没有情报。</div>';
}

function openDetail(id) {
  const item = intel.find(entry => entry.id === id);
  if (!item) return;
  const source = safeHref(item.sourceUrl);
  const notion = safeHref(item.notionUrl);
  const knowledge = safeHref(item.knowledgeUrl);
  $("#modal-content").innerHTML = `
    <span class="tag ${statusClass(statusLabel(item))}">${escapeHtml(statusLabel(item))}</span>
    <h2>${escapeHtml(item.title)}</h2>
    <div class="intel-meta">${escapeHtml(item.topic || item.field)} · ${escapeHtml(item.date)}</div>
    <h4>核心摘要</h4><p>${escapeHtml(item.summary || "暂无摘要")}</p>
    <h4>证据与适用条件</h4><p>${escapeHtml(item.evidence || "暂无补充证据说明")}</p>
    <h4>知识沉淀状态</h4><p><span class="tag ${knowledgeClass(item.knowledgeStatus)}">${escapeHtml(item.knowledgeStatus || "待评估")}</span> · ${escapeHtml(item.knowledgeVersion || "尚无处理版本")}</p>
    <h4>后续动作</h4><p>${escapeHtml(item.next || "暂无后续动作")}</p>
    <div class="modal-actions">
      ${source ? `<a class="action-btn primary" href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">查看原始来源</a>` : ""}
      ${notion ? `<a class="action-btn" href="${escapeHtml(notion)}" target="_blank" rel="noopener noreferrer">打开 Notion 记录</a>` : ""}
      ${knowledge ? `<a class="action-btn" href="${escapeHtml(knowledge)}" target="_blank" rel="noopener noreferrer">打开知识卡片</a>` : ""}
    </div>
    <p class="disclaimer">公开只读视图 · 数据来自 Notion 情报收件箱。</p>`;
  $("#detail-modal").classList.add("open");
  $("#detail-modal").setAttribute("aria-hidden", "false");
}

function closeDetail() {
  $("#detail-modal").classList.remove("open");
  $("#detail-modal").setAttribute("aria-hidden", "true");
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 2300);
}

function showView(view) {
  document.querySelectorAll(".view").forEach(element =>
    element.classList.toggle("active", element.id === `view-${view}`));
  document.querySelectorAll(".nav-item").forEach(element =>
    element.classList.toggle("active", element.dataset.view === view));
  const names = {overview:"总览仪表盘", inbox:"情报收件箱", topics:"关注主题", sources:"信息源目录", pipeline:"处理流水线"};
  $("#page-title").textContent = names[view] || "总览仪表盘";
}

async function loadIntel() {
  const refresh = $("#refresh-btn");
  refresh.disabled = true;
  try {
    const response = await fetch("data/intel.json?ts=" + Date.now(), {cache:"no-store"});
    if (!response.ok) throw new Error("数据接口返回 " + response.status);
    const payload = await response.json();
    if (!Array.isArray(payload.items)) throw new Error("数据格式不正确");
    intel = payload.items;
    renderLists();
    $(".mode-pill").innerHTML = '<i></i> Notion 公开数据';
    $(".sidebar-bottom").innerHTML = '<span class="status-dot"></span> 数据已连接 <small>Notion · 只读同步</small>';
    const generated = payload.generatedAt ? new Date(payload.generatedAt) : null;
    if (generated && !Number.isNaN(generated.getTime())) {
      $("#today-label").textContent += " · 数据更新 " + generated.toLocaleString("zh-CN");
    }
  } catch (error) {
    $(".mode-pill").textContent = "数据暂不可用";
    $(".sidebar-bottom").innerHTML = '<span class="status-dot"></span> 数据连接异常 <small>请稍后重试</small>';
    $("#featured-list").innerHTML = '<div class="panel">暂时无法读取 Notion 数据。请稍后刷新。</div>';
    $("#inbox-list").innerHTML = '<div class="panel">数据接口暂不可用。</div>';
    console.error(error);
    toast("数据读取失败：" + error.message);
  } finally {
    refresh.disabled = false;
  }
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-view]");
  if (nav) showView(nav.dataset.view);
  const go = event.target.closest("[data-goto]");
  if (go) showView(go.dataset.goto);
  const card = event.target.closest(".intel-card");
  if (card) openDetail(card.dataset.id);
});
$("#close-modal").addEventListener("click", closeDetail);
$("#detail-modal").addEventListener("click", event => {
  if (event.target.id === "detail-modal") closeDetail();
});
$("#status-filter").addEventListener("change", renderInbox);
$("#refresh-btn").addEventListener("click", loadIntel);
$("#today-label").textContent = new Intl.DateTimeFormat("zh-CN", {
  year:"numeric", month:"long", day:"numeric", weekday:"long"
}).format(new Date());
loadIntel();
