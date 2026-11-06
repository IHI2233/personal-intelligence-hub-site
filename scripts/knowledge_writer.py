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
    first_party = source_level == "s1" or source_level.startswith("s1 ") or source_level in {"一级", "一手来源", "官方来源"}
    summary = norm(item.get("summary"))
    evidence = norm(item.get("evidence"))
    url = str(item.get("sourceUrl") or "")
    return (
        verification in {"已验证", "完全验证", "verified"}
        and first_party
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

def rich_text(value, link=None):
    value = str(value or "")
    chunks = [value[i:i + 1800] for i in range(0, len(value), 1800)] or [""]
    result = []
    for chunk in chunks:
        item = {"type": "text", "text": {"content": chunk}}
        if link:
            item["text"]["link"] = {"url": link}
        result.append(item)
    return result

def paragraph(value):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text(value)}}

def heading(value):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": rich_text(value)}}

def bullet(value):
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text(value)}}

def build_blocks(item, run_id):
    now = datetime.now(timezone.utc).isoformat()
    summary = str(item.get("summary") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    next_step = str(item.get("next") or "暂未提供后续验证动作。").strip()
    source_id = str(item.get("id") or "")
    source_url = str(item.get("sourceUrl") or "")
    source_notion_url = str(item.get("notionUrl") or "")
    blocks = [
        heading("一句话结论"),
        paragraph(summary),
        heading("来源事实与证据"),
        paragraph(evidence),
        heading("事实、推断与未知边界"),
        bullet("来源记录验证状态：已验证；来源等级：S1 一手来源。此标签沿用收件箱字段，不代表本系统重新进行了独立实验或第三方审计。"),
        bullet("本卡片只整理收件箱中已记录的来源摘要和证据，不新增未经来源支持的推断。"),
        bullet("未知与限制：以来源证据中明确记录的限制为准；未记录的信息不作补充猜测。"),
        heading("适用条件与后续验证"),
        paragraph(next_step),
        heading("来源与追溯"),
        paragraph(f"情报记录 ID：{source_id}"),
        paragraph(f"原始来源：{source_url}"),
    ]
    if source_notion_url:
        blocks.append(paragraph(f"原始情报记录：{source_notion_url}"))
    blocks.extend([
        paragraph(f"沉淀时间（UTC）：{now}"),
        paragraph("处理版本：knowledge-writer-v1"),
        paragraph(f"GitHub Actions 运行 ID：{run_id}"),
        paragraph("生成方式：确定性模板；未调用模型 API；未生成个人观点。"),
    ])
    return blocks

def block_title(block):
    if block.get("type") == "child_page":
        return block.get("child_page", {}).get("title", "")
    return ""

def get_existing_titles():
    titles = {}
    for parent_id in CATEGORIES.values():
        cursor = None
        while True:
            path = f"/blocks/{parent_id}/children?page_size=100"
            if cursor:
                path += "&start_cursor=" + urllib.parse.quote(cursor)
            result = api("GET", path)
            for block in result.get("results", []):
                if block.get("type") == "child_page":
                    titles[block_title(block)] = block.get("id")
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")
            if not cursor:
                break
    return titles

def update_source_record(item, status, page_id=None):
    source_id = str(item.get("id") or "")
    if not source_id:
        raise RuntimeError("Source record is missing its Notion page ID.")
    page_url = f"https://www.notion.so/{page_id.replace('-', '')}" if page_id else None
    processed_date = datetime.now(timezone.utc).date().isoformat()
    properties = {
        "知识沉淀状态": {"select": {"name": status}},
        "知识页面链接": {"url": page_url},
        "知识处理时间": {"date": {"start": processed_date}},
        "知识沉淀版本": {"rich_text": [{"type": "text", "text": {"content": "knowledge-writer-v1"}}]},
    }
    api("PATCH", f"/pages/{source_id}", {"properties": properties})

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
    existing_titles = get_existing_titles() if eligible_items else {}
    created, reused, blocked = [], [], []
    status_updates = 0

    for item in items:
        source_id = str(item.get("id") or "")
        title = f"知识卡片｜{str(item.get('title') or '未命名情报').strip()} · {source_id[:8]}"
        if not eligible(item):
            current_status = norm(item.get("knowledgeStatus"))
            if current_status == "已沉淀":
                blocked.append({"sourceId": source_id, "status": "preserved_existing_knowledge_status"})
                continue
            verification = norm(item.get("verification"))
            if verification == "存在争议":
                state = "存在争议"
            elif verification in {"已证伪/不适用", "不适用"}:
                state = "不适用"
            else:
                state = "证据不足"
            update_source_record(item, state)
            status_updates += 1
            blocked.append({"sourceId": source_id, "status": state})
            continue

        if title in existing_titles:
            page_id = existing_titles[title]
            reused.append({"sourceId": source_id, "pageId": page_id, "reason": "idempotent_existing_card"})
        else:
            parent_id = CATEGORIES[category_for(item)]
            result = api("POST", "/pages", {
                "parent": {"type": "page_id", "page_id": parent_id},
                "properties": {"title": {"title": rich_text(title)}},
                "children": build_blocks(item, run_id),
            })
            page_id = result["id"]
            existing_titles[title] = page_id
            created.append({
                "sourceId": source_id,
                "title": title,
                "pageId": page_id,
                "category": category_for(item),
            })
        update_source_record(item, "已沉淀", page_id)
        status_updates += 1

    report = {
        "mode": "deterministic_auto_capture",
        "modelCalls": 0,
        "inputCount": len(items),
        "eligibleCount": len(eligible_items),
        "createdCount": len(created),
        "reusedExistingCount": len(reused),
        "blockedCount": len(blocked),
        "sourceStatusUpdates": status_updates,
        "created": created,
        "reused": reused,
        "blocked": blocked,
    }
    print("KNOWLEDGE_WRITE_REPORT=" + json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()
