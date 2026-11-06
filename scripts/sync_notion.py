import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.notion.com/v1"
DATA_SOURCE_ID = os.environ.get("NOTION_DATA_SOURCE_ID", "f12e3184-4a3a-49ce-a62c-a5367b0e574f")
TOKEN = os.environ["NOTION_TOKEN"]

def notion_request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_BASE + path,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json",
        },
        method="GET" if payload is None else "POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 429 or 500 <= error.code < 600:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Notion API {error.code}: {detail}") from error
    raise RuntimeError("Notion API request failed after retries")

def plain_text(items):
    return "".join(item.get("plain_text", "") for item in (items or []))

def prop(properties, name):
    return properties.get(name, {}) or {}

def text_prop(properties, name):
    value = prop(properties, name)
    if value.get("type") == "title":
        return plain_text(value.get("title"))
    if value.get("type") == "rich_text":
        return plain_text(value.get("rich_text"))
    return ""

def select_prop(properties, name):
    value = prop(properties, name)
    kind = value.get("type")
    if kind in ("select", "status"):
        selected = value.get(kind)
        return selected.get("name", "") if selected else ""
    return ""

def number_prop(properties, name):
    value = prop(properties, name)
    return value.get("number") if value.get("type") == "number" else None

def date_prop(properties, name):
    value = prop(properties, name)
    date_value = value.get("date")
    return date_value.get("start", "") if date_value else ""

def url_prop(properties, name):
    value = prop(properties, name)
    return value.get("url", "") if value.get("type") == "url" else ""

def safe_url(value):
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else ""

def main():
    results = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        response = notion_request(f"/data_sources/{DATA_SOURCE_ID}/query", payload)
        for page in response.get("results", []):
            p = page.get("properties", {})
            source_url = safe_url(url_prop(p, "原始链接"))
            results.append({
                "id": page.get("id", ""),
                "title": text_prop(p, "情报标题"),
                "date": date_prop(p, "发布日期") or date_prop(p, "发现日期"),
                "topic": text_prop(p, "关联主题"),
                "field": select_prop(p, "所属领域"),
                "type": select_prop(p, "信息类型"),
                "status": select_prop(p, "处理状态"),
                "verification": select_prop(p, "验证状态"),
                "sourceLevel": select_prop(p, "来源等级"),
                "credibility": number_prop(p, "可信度"),
                "score": number_prop(p, "综合评分"),
                "summary": text_prop(p, "核心摘要"),
                "evidence": text_prop(p, "证据与适用条件"),
                "next": text_prop(p, "后续动作"),
                "sourceUrl": source_url,
                "notionUrl": f"https://www.notion.so/{page.get('id', '').replace('-', '')}",
            })
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        if not cursor:
            break

    results.sort(key=lambda item: item.get("date", ""), reverse=True)
    output = {
        "source": "Notion 情报收件箱",
        "dataSourceId": DATA_SOURCE_ID,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(results),
        "items": results,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/intel.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Exported {len(results)} Notion intelligence records.")

if __name__ == "__main__":
    main()
