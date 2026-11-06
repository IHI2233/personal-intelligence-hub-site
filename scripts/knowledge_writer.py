import json
import os
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"
TOKEN = os.environ["NOTION_TOKEN"]
INPUT = Path("data/intel.json")

CATEGORIES = {
    "01": "3f42a473-4547-8096-be21-fd73566ac55f",
    "02": "3f42a473-4547-8091-8275-d791b4fe44f",
    "03": "3f42a473-4547-8005-8b86-ec4ced71ed29",
    "04": "3f42a473-4547-80d7-a913-ff98716eb94f",
    "05": "3f42a473-4547-807a-8ce4-d8ad6ac73bfb",
    "06": "3f42a473-4547-80c5-8438-eb75196adf43",
    "07": "3f42a473-4547-80e9-b146-e73c6facdc18",
    "08": "3f42a473-4547-8077-9076-d9d61bae4fd9",
}

def api(method, path, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API {error.code}: {detail}") from error

def norm(value):
    return " ".join(str(value or "").strip().casefold().split())

def eligible(item):
    verification = norm(item.get("verification"))
    source_level = norm(item.get("sourceLevel"))
    summary = norm(item.get("summary"))
    evidence = norm(item.get("evidence"))
    url = str(item.get("sourceUrl") or "")
    return (
        verification in {"已验证", "完全验证", "verified"}
        and source_level in {"s1", "一级", "一手来源", "官方来源"}
        and len(summary) >= 80
        and len(evidence) >= 40
        and url.startswith(("https://", "http://"))
    )

def category_for(item):
    kind = norm(item.get("type"))
    topic = norm(item.get("topic"))
    field = norm(item.get("field"))
    if any(term in topic for term in ("jarvis", "个人 ai", "第二大脑")):
        return "04"
    if kind in {"模型/产品更新", "代码/开发工具"}:
        return "02"
    if kind == "agent/工作流":
        return "03"
    if kind == "论文/研究":
        return "05"
    if kind == "商业案例" or "商业" in field:
        return "06"
    if kind == "本地部署/隐私":
        return "04"
    return "01"

def rt(text):
    return [{"type": "text", "text": {"content": str(text)}}]

def block_title(block):
    kind = block.get("type")
    data = block.get(kind, {}) if kind else {}
    if kind == "child_page":
        return data.get("title", "")
    return ""

def get_existing_titles():
    titles = set()
    for parent_id in CATEGORIES.values():
        cursor = None
        while True:
            path = f"/blocks/{parent_id}/children?page_size=100"
            if cursor:
                path += "&start_cursor=" + urllib.parse.quote(cursor)
            result = api("GET", path)
            for block in result.get("results", []):
                if block.get("type") == "child_page":
                    titles.add(block_title(block))
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")
            if not cursor:
                break
    return titles

def build_card(item, run_id):
    title = str(item.get("title") or "未命名情报").strip()
    source_id = str(item.get("id") or "")
    source_url = str(item.get("sourceUrl") or "")
    source_notion_url = str(item.get("notionUrl") or "")
    now = datetime.now(timezone.utc).isoformat()
    summary = str(item.get("summary") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    next_step = str(item.get("next") or "暂未提供后续验证动作。").strip()
    return (
        "## 一句话结论\n\n"
        + summary
        + "\n\n## 来源事实与证据\n\n"
        + evidence
        + "\n\n## 事实、推断与未知边界\n\n"
        + "- 来源记录验证状态：已验证；来源等级：S1 一手来源。此标签沿用收件箱字段，不代表本系统重新进行了独立实验或第三方审计。\n"
        + "- 本卡片只整理收件箱中已记录的来源摘要和证据，不新增未经来源支持的推断。\n"
        + "- 未知与限制：以来源证据中明确记录的限制为准；未记录的信息不作补充猜测。\n\n"
        + "## 适用条件与后续验证\n\n"
        + next_step
        + "\n\n## 来源与追溯\n\n"
        + f"- 原始来源：[打开原始来源]({source_url})\n"
        + (f"- 情报收件箱：[打开原始情报记录]({source_notion_url})\n" if source_notion_url else "")
        + f"- 情报记录 ID：{source_id}\n"
        + f"- 沉淀时间（UTC）：{now}\n"
        + "- 处理版本：knowledge-writer-v1\n"
        + f"- GitHub Actions 运行 ID：{run_id}\n"
        + "- 生成方式：确定性模板；未调用模型 API；未生成个人观点。\n"
    )

def main():
    if not INPUT.exists():
        raise RuntimeError("Missing data/intel.json.")
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("No intelligence items found; refusing silent success.")
    if data.get("count") is not None and data["count"] != len(items):
        raise RuntimeError("Input count does not match items length.")

    run_id = os.environ.get("GITHUB_RUN_ID", "manual")
    eligible_items = [item for item in items if eligible(item)]
    existing_titles = get_existing_titles() if eligible_items else set()
    created, skipped = [], []

    for item in eligible_items:
        source_id = str(item.get("id") or "")
        title = f"知识卡片｜{str(item.get('title') or '未命名情报').strip()} · {source_id[:8]}"
        if title in existing_titles:
            skipped.append({"sourceId": source_id, "reason": "existing_title_idempotency_guard"})
            continue
        parent_id = CATEGORIES[category_for(item)]
        result = api("POST", "/pages", {
            "parent": {"type": "page_id", "page_id": parent_id},
            "properties": {"title": {"title": rt(title)}},
            "children": [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rt("自动沉淀卡片；确定性模板；无模型调用。")},
            }],
        })
        page_id = result["id"]
        content = build_card(item, run_id)
        api("PATCH", f"/blocks/{page_id}/children", {
            "children": [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rt(content[:1900])},
            }]
        })
        created.append({
            "sourceId": source_id,
            "title": title,
            "pageId": page_id,
            "category": category_for(item),
        })
        existing_titles.add(title)

    report = {
        "mode": "deterministic_auto_capture",
        "modelCalls": 0,
        "inputCount": len(items),
        "eligibleCount": len(eligible_items),
        "createdCount": len(created),
        "skippedDuplicateCount": len(skipped),
        "created": created,
        "skipped": skipped,
    }
    print("KNOWLEDGE_WRITE_REPORT=" + json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()
