import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

INPUT = Path("data/intel.json")

def norm(value):
    return re.sub(r"\s+, " ", str(value or "").strip()).casefold()

def canonical_url(value):
    if not value:
        return ""
    try:
        parts = urlsplit(str(value).strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
    except ValueError:
        return ""

def eligibility_reasons(item):
    reasons = []
    verification = norm(item.get("verification"))
    source_level = norm(item.get("sourceLevel"))
    summary = norm(item.get("summary"))
    evidence = norm(item.get("evidence"))
    source_url = canonical_url(item.get("sourceUrl"))
    if verification not in {"已验证", "完全验证", "verified"}:
        reasons.append("验证状态未达到已验证")
    first_party = source_level == "s1" or source_level.startswith("s1 ") or source_level in {"一级", "一手来源", "官方来源"}
    if not first_party:
        reasons.append("来源等级不是S1一手来源")
    if len(summary) < 80:
        reasons.append("核心摘要不足80字符")
    if len(evidence) < 40:
        reasons.append("证据说明不足40字符")
    if not source_url:
        reasons.append("缺少有效HTTP(S)原始链接")
    return reasons

def main():
    if not INPUT.exists():
        raise RuntimeError("Missing data/intel.json; refusing to report an empty successful run.")
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("data/intel.json has no non-empty 'items' list; refusing silent zero-record success.")
    if data.get("count") is not None and data["count"] != len(items):
        raise RuntimeError(f"Record count mismatch: count={data['count']} but items={len(items)}.")

    seen = set()
    duplicates = []
    candidates = []
    blocked = []
    for item in items:
        key_url = canonical_url(item.get("sourceUrl"))
        key = (key_url, norm(item.get("title"))) if key_url else ("source_id", str(item.get("id") or ""))
        if key in seen:
            duplicates.append(item.get("id", ""))
            continue
        seen.add(key)
        reasons = eligibility_reasons(item)
        if not reasons:
            candidates.append({
                "sourceId": item.get("id", ""),
                "title": item.get("title", ""),
                "topic": item.get("topic", ""),
                "field": item.get("field", ""),
                "summary": item.get("summary", ""),
                "evidence": item.get("evidence", ""),
                "sourceUrl": key_url,
                "sourceNotionUrl": item.get("notionUrl", ""),
                "decision": "candidate_only",
                "writeEnabled": False,
            })
        else:
            blocked.append({
                "sourceId": item.get("id", ""),
                "title": item.get("title", ""),
                "reasons": reasons,
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
    encoded = json.dumps(report, ensure_ascii=False)
    print("KNOWLEDGE_SHADOW_REPORT=" + encoded)
    print(f"Shadow run complete: {len(items)} input, {len(candidates)} candidates, {len(blocked)} blocked, {len(duplicates)} duplicates. No model calls or Notion writes.")

if __name__ == "__main__":
    main()
