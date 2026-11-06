import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

INPUT = Path("data/intel.json")

def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()

def canonical_url(value):
    if not value:
        return ""
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))

def eligible(item):
    # Conservative shadow gate: no model calls and no automatic Notion writes.
    verification = norm(item.get("verification"))
    source_level = norm(item.get("sourceLevel"))
    summary = norm(item.get("summary"))
    evidence = norm(item.get("evidence"))
    source_url = canonical_url(item.get("sourceUrl"))
    verified = verification in {"已验证", "完全验证", "verified"}
    first_party = source_level in {"s1", "一级", "一手来源", "官方来源"}
    sufficiently_described = len(summary) >= 80 and len(evidence) >= 40
    traceable = source_url.startswith(("https://", "http://"))
    return verified and first_party and sufficiently_described and traceable

def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    items = data.get("items", [])
    seen = set()
    duplicates = []
    candidates = []
    blocked = []
    for item in items:
        key = (canonical_url(item.get("sourceUrl")), norm(item.get("title")))
        if key in seen:
            duplicates.append(item.get("id", ""))
            continue
        seen.add(key)
        if eligible(item):
            candidates.append({
                "sourceId": item.get("id", ""),
                "title": item.get("title", ""),
                "topic": item.get("topic", ""),
                "field": item.get("field", ""),
                "summary": item.get("summary", ""),
                "evidence": item.get("evidence", ""),
                "sourceUrl": canonical_url(item.get("sourceUrl")),
                "sourceNotionUrl": item.get("notionUrl", ""),
                "decision": "candidate_only",
                "writeEnabled": False,
            })
        else:
            blocked.append({
                "sourceId": item.get("id", ""),
                "title": item.get("title", ""),
                "reason": "未同时满足：已验证 + S1一手来源 + 摘要/证据完整 + 可追溯原始链接",
            })
    report = {
        "mode": "shadow",
        "modelCalls": 0,
        "notionWrites": 0,
        "inputCount": len(items),
        "candidateCount": len(candidates),
        "blockedCount": len(blocked),
        "duplicateCount": len(duplicates),
        "candidates": candidates,
        "blocked": blocked,
        "duplicateSourceIds": duplicates,
    }
    print("KNOWLEDGE_SHADOW_REPORT=" + json.dumps(report, ensure_ascii=False))
    print(f"Shadow run complete: {len(candidates)} candidates, {len(blocked)} blocked, {len(duplicates)} duplicates. No model calls or Notion writes.")
    
if __name__ == "__main__":
    main()
