# Personal Intelligence Hub

个人智能情报中控台。当前版本通过公开 JSON 数据文件展示 Notion「情报收件箱」中的真实情报记录。

## 当前能力

- 响应式仪表盘与情报收件箱
- 情报详情、验证状态、证据说明、后续动作
- 原始来源与 Notion 记录链接
- GitHub Actions 定时/手动同步 Notion 数据
- 前端只读取公开 JSON，不持有 Notion Token

## 数据链路

Notion 情报收件箱 → GitHub Actions → `data/intel.json` → GitHub Pages

同步脚本：`scripts/sync_notion.py`  
工作流：`.github/workflows/sync-notion.yml`

## 启用自动同步

1. 在 Notion 中创建一个 Internal Integration，并授予读取内容权限。
2. 在 Notion「情报收件箱」数据库中，将该 Integration 添加为连接，确保它能读取对应数据源。
3. 在 GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret 中创建：
   - Name: `NOTION_TOKEN`
   - Secret: Notion Integration 的 Internal Integration Secret
4. 在 GitHub 仓库 Actions 中运行 `Sync public Notion intelligence data`，选择 Run workflow。
5. 检查工作流成功后，确认 `data/intel.json` 已更新，随后等待 GitHub Pages 部署完成。

当前数据源 ID 在工作流中配置为公开标识；它不是密钥。Notion Token 只能保存在 GitHub Actions Secret 中，严禁写入网页代码、JSON 数据文件或仓库普通文件。

## 公开数据边界

本网站是公开网页。同步脚本会把 Notion 情报收件箱中的以下字段公开发布：

- 标题、发布日期、领域、主题、信息类型
- 处理状态、验证状态、来源等级
- 可信度、综合评分
- 核心摘要、证据与适用条件、后续动作
- 原始来源链接及 Notion 记录链接

不要将密码、API Key、个人隐私、客户机密或其他不适合公开的内容写入该数据源。网页当前为只读展示，不会修改 Notion。

## 运行频率

- GitHub Actions 每天 02:17 UTC 自动同步一次。
- 也可以在 Actions 页面手动运行。
- 同步成功后，更新后的 JSON 文件会提交到默认分支；GitHub Pages 按仓库当前发布设置更新网站。

## 本地运行

无需安装依赖。直接用浏览器打开 `index.html`。由于浏览器本地文件协议可能限制 fetch，请使用本地静态 HTTP 服务预览。

## 安全原则

- Notion Token 仅存储在 GitHub Actions Secret。
- 网页仅读取公开 JSON。
- 不开放前端写入 Notion。
- 公开数据需遵守上述字段与内容边界。
