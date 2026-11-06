#!/usr/bin/env python3
"""Public URL intake: safe HTML extraction and Notion draft creation (no model API)."""
import html
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
EVENT_PATH = os.environ["GITHUB_EVENT_PATH"]
CATEGORY_PAGE = "3f42a473-4547-80d7-a913-ff98716eb94f"
NOTION_VERSION = "2022-06-28"
TASKS_PATH = "data/tasks.json"
MAX_BYTES = 1_000_000

class Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts, self.text_parts, self.headings = [], [], []
        self.meta, self.links = {}, []
        self.in_title = False
        self.skip = 0
        self.current_heading = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "nav", "footer"):
            self.skip += 1
        if tag == "title": self.in_title = True
        if tag == "meta":
            key = a.get("property") or a.get("name")
            if key and a.get("content"): self.meta[key.lower()] = a["content"].strip()
        if tag in ("h1","h2","h3"):
            self.current_heading = tag
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer") and self.skip:
            self.skip -= 1
        if tag == "title": self.in_title = False
        if tag in ("h1","h2","h3"): self.current_heading = None
    def handle_data(self, data):
        value = " ".join(data.split())
        if not value: return
        if self.in_title: self.title_parts.append(value)
        if self.skip: return
        if self.current_heading: self.headings.append(value)
        if len(value) > 25: self.text_parts.append(value)

def validate_url(url):
    p = urllib.parse.urlsplit(url.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("仅允许无凭据的 HTTPS 公网页面。")
    host = p.hostname.lower().rstrip(".")
    if host in {"localhost"} or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("拒绝本地或内部主机。")
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as e:
        raise ValueError("域名解析失败。") from e
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("拒绝指向非公网 IP 的地址。")
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch_page(url):
    opener = urllib.request.build_opener(SafeRedirect)
    req = urllib.request.Request(url, headers={"User-Agent":"PersonalIntelligenceHub/1.0 (+public URL intake)", "Accept":"text/html"})
    with opener.open(req, timeout=20) as response:
        final_url = validate_url(response.geturl())
        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype.lower():
            raise ValueError("目标不是 HTML 页面，当前入口只支持 HTML。")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError("网页超过 1 MB 采集上限。")
        charset = response.headers.get_content_charset() or "utf-8"
        return final_url, raw.decode(charset, errors="replace")

def notion_request(method, path, payload):
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request("https://api.notion.com/v1"+path, data=body, method=method, headers={
        "Authorization":"Bearer "+NOTION_TOKEN, "Notion-Version":NOTION_VERSION, "Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as res: return json.loads(res.read())

def rt(text):
    text = str(text)[:1900]
    return [{"type":"text","text":{"content":text}}]

def block(kind, text):
    return {"object":"block","type":kind,kind:{"rich_text":rt(text)}}

def create_notion_draft(title, source_url, domain, date, headings, excerpts, page_type):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page_title = ("URL采集草稿｜"+title)[:190]
    children = [
        block("heading_2","任务状态与处理边界"),
        block("paragraph","已完成网页抓取、元数据与结构提取。此版本未调用模型 API；不包含自动语义总结或独立事实核验。状态：待人工分析与审核。"),
        block("heading_2","来源信息"),
        block("paragraph",f"原始 URL：{source_url}"),
        block("paragraph",f"域名：{domain}；页面类型初判：{page_type}；采集时间：{stamp}；页面日期元数据：{date or '未识别'}"),
        block("heading_2","提取到的标题结构"),
    ]
    for h in headings[:20]: children.append(block("bulleted_list_item",h))
    if not headings: children.append(block("paragraph","未识别到明确的 H1-H3 标题。"))
    children.append(block("heading_2","正文片段（节选，非全文存档）"))
    for p in excerpts[:8]: children.append(block("paragraph",p[:900]))
    children.extend([
        block("heading_2","核验状态"),
        block("paragraph","待核验。页面自身陈述不自动视为事实；应对关键主张寻找原始论文、官方文档、数据或独立来源。"),
        block("heading_2","下一步"),
        block("paragraph","由研究流程补充语义摘要、事实/推断/未知拆分、外部证据和知识分类；审核通过后再转为正式知识卡片。"),
    ])
    result = notion_request("POST","/pages",{
        "parent":{"type":"page_id","page_id":CATEGORY_PAGE},
        "properties":{"title":{"title":rt(page_title)}},
        "children":children
    })
    return result["id"], result.get("url","")

def write_tasks(task):
    os.makedirs("data",exist_ok=True)
    try:
        old=json.load(open(TASKS_PATH,encoding="utf-8"))
        items=old.get("items",[])
    except (FileNotFoundError, json.JSONDecodeError):
        items=[]
    items=[x for x in items if x.get("issueNumber") != task["issueNumber"]]
    items.insert(0,task)
    payload={"generatedAt":datetime.now(timezone.utc).isoformat(),"count":len(items[:30]),"items":items[:30]}
    with open(TASKS_PATH,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)

def comment_issue(number, body):
    url=f"https://api.github.com/repos/{REPO}/issues/{number}/comments"
    req=urllib.request.Request(url,data=json.dumps({"body":body}).encode(),method="POST",headers={
        "Authorization":"Bearer "+GITHUB_TOKEN,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=20) as r: return r.status

def main():
    event=json.load(open(EVENT_PATH,encoding="utf-8"))
    issue=event["issue"]
    number=issue["number"]
    body=issue.get("body") or ""
    match=re.search(r"(?im)^\s*(?:source\s*url|url)\s*:\s*(https://\S+)\s*$",body)
    if not match: raise ValueError("Issue 正文必须包含单独一行 Source URL: https://...")
    url=match.group(1).rstrip(").,;")
    task={"issueNumber":number,"title":issue.get("title","URL采集任务"),"status":"fetching","stage":"采集网页","createdAt":issue.get("created_at"),"issueUrl":issue.get("html_url"),"domain":"","pageTitle":"","notionUrl":"","error":""}
    write_tasks(task)
    try:
        final_url, source=fetch_page(url)
        parser=Extractor(); parser.feed(source)
        title=html.unescape(" ".join(parser.title_parts) or parser.meta.get("og:title") or issue.get("title") or "未命名网页")
        desc=parser.meta.get("description") or parser.meta.get("og:description") or ""
        date=parser.meta.get("article:published_time") or parser.meta.get("date") or parser.meta.get("pubdate") or ""
        text=" ".join(parser.text_parts)
        if len(text)<120: raise ValueError("正文提取内容过少，可能是 JS 渲染页、登录墙或非文章页面。")
        path=urllib.parse.urlsplit(final_url)
        page_type="独立文章" if len(parser.headings)>=2 and len(text)>1000 else "普通网页/栏目页（待人工确认）"
        task.update({"status":"writing","stage":"写入 Notion 草稿","domain":path.hostname,"pageTitle":title})
        write_tasks(task)
        page_id, notion_url=create_notion_draft(title,final_url,path.hostname,date,parser.headings,[desc]+parser.text_parts[:8],page_type)
        task.update({"status":"awaiting_review","stage":"已生成 Notion 草稿","notionUrl":notion_url,"pageId":page_id,"completedAt":datetime.now(timezone.utc).isoformat(),"note":"自动采集与结构提取完成；语义分析和事实核验待人工完成。"})
        write_tasks(task)
        comment_issue(number,f"## URL 采集完成\n\n- 页面：**{title}**\n- 类型初判：{page_type}\n- 正文提取：{len(text)} 字符\n- Notion 草稿：[打开页面]({notion_url})\n\n状态：**待人工分析与审核**。本次未调用模型 API；尚未完成语义总结和事实核验。")
    except Exception as exc:
        task.update({"status":"failed","stage":"处理失败","error":str(exc)[:500],"completedAt":datetime.now(timezone.utc).isoformat()})
        write_tasks(task)
        try: comment_issue(number,"## URL 采集失败\n\n原因："+str(exc)[:500]+"\n\n请检查 URL 是否为可公开访问的 HTTPS HTML 页面。")
        except Exception: pass
        raise

if __name__=="__main__": main()
