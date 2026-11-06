import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"
TOKEN = os.environ["NOTION_TOKEN"]
PARENT_PAGE_ID = "3f42a473-4547-80d7-a913-ff98716eb94f"
PAGE_TITLE = "系统运行记录｜GitHub Actions 写入验收"

def request(method, path, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
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
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API {error.code}: {detail}") from error

def rich_text(text):
    return [{"type": "text", "text": {"content": text}}]

def child_text(block):
    kind = block.get("type")
    data = block.get(kind, {}) if kind else {}
    return "".join(x.get("plain_text", "") for x in data.get("rich_text", []))

def main():
    run_id = os.environ.get("GITHUB_RUN_ID", "manual")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "manual")
    marker = f"WRITE_SMOKE_TEST_RUN_ID={run_id}"
    children = request("GET", f"/blocks/{PARENT_PAGE_ID}/children?page_size=100").get("results", [])
    page = next(
        (b for b in children if b.get("type") == "child_page" and b.get("child_page", {}).get("title") == PAGE_TITLE),
        None,
    )

    if page:
        page_id = page["id"]
        existing = request("GET", f"/blocks/{page_id}/children?page_size=100").get("results", [])
        if not any(marker in child_text(b) for b in existing):
            request("PATCH", f"/blocks/{page_id}/children", {
                "children": [{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text(f"{marker} | run_number={run_number} | status=write_readback_pending")},
                }]
            })
    else:
        created = request("POST", "/pages", {
            "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
            "properties": {"title": {"title": rich_text(PAGE_TITLE)}},
            "children": [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text(f"{marker} | run_number={run_number} | status=write_readback_pending")},
            }],
        })
        page_id = created["id"]

    readback = request("GET", f"/blocks/{page_id}/children?page_size=100")
    verified = any(marker in child_text(block) for block in readback.get("results", []))
    if not verified:
        raise RuntimeError("Notion page was created/located, but the expected run marker was not present on read-back.")
    print(json.dumps({
        "write_test": "passed",
        "readback": "passed",
        "page_id": page_id,
        "page_title": PAGE_TITLE,
        "run_id": run_id,
        "parent_page_id": PARENT_PAGE_ID,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
