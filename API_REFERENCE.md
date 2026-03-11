# 美术资源审核平台 - AI 接口文档

> **面向 AI 使用**：本文档描述了「ArtHub 美术资源审核平台」的所有 HTTP API。
> AI 可通过读取此文档，自动理解平台能力，设计适合当前游戏项目的美术分类体系，并批量注入美术任务。

---

## 快速上手（AI 操作流程）

```
1. GET  /api/config/project       → 读取当前项目配置
2. PUT  /api/config/project       → 填写项目信息（仓库地址、CI/CD、分类等）
3. POST /api/tasks                → 批量创建美术任务
4. GET  /api/tasks                → 查询任务列表，监控审核进度
5. POST /api/tasks/{id}/claim     → 代表审核员认领任务
6. POST /api/tasks/{id}/review    → 提交审核结果
```

---

## Base URL

```
http://<服务器IP>:<PORT>
```

默认端口：`8899`。通过 `deploy.sh` 部署时可用 `PORT=xxxx` 自定义。

---

## 一、项目配置 API

### 1.1 读取配置（YAML 原文）

```
GET /api/config/project
```

**响应**：`text/plain` — 当前 `project.yaml` 完整内容

```yaml
project:
  name: "我的游戏项目"
  description: "游戏美术资源审核平台"

cicd:
  repo_url: "https://github.com/org/game-assets"
  branch: "main"
  webhook_url: "https://api.github.com/repos/org/game-assets/dispatches"

review:
  categories: ["角色", "场景", "UI", "特效"]
  reviewers: ["CTO", "主美"]
  priorities: ["紧急", "高", "中", "低"]

notifications:
  feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

---

### 1.2 更新配置（JSON 补丁，推荐 AI 使用）

```
PUT /api/config/project
Content-Type: application/json
```

**Body 示例**（只需包含要修改的字段，支持深度 merge）：

```json
{
  "project": {
    "name": "龙虾卡牌游戏",
    "description": "2D 策略卡牌游戏美术审核"
  },
  "cicd": {
    "repo_url": "https://github.com/hewenze11/card-game-assets",
    "webhook_url": "https://api.github.com/repos/hewenze11/card-game-assets/dispatches"
  },
  "review": {
    "categories": ["卡牌插画", "UI界面", "角色立绘", "场景背景", "特效动画", "图标", "其他"],
    "reviewers": ["CTO", "主美", "程序"]
  },
  "notifications": {
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"
  }
}
```

**响应** `200`：
```json
{"ok": true}
```

---

### 1.3 读取配置概览（含默认值）

```
GET /api/config
```

**响应**：
```json
{
  "project": {"name": "龙虾卡牌游戏", "description": "..."},
  "review": {
    "categories": ["卡牌插画", "UI界面", ...],
    "reviewers": ["CTO", "主美", "程序"],
    "priorities": ["紧急", "高", "中", "低"]
  }
}
```

---

## 二、任务 API

### 任务状态流转

```
pending（待认领）
    → in_review（审核中）    [claim 接口]
        → approved（已通过）  [review 接口]
        → rejected（已拒绝）  [review 接口]
        → changes_requested   [review 接口]
            → in_review       [重新 claim]
```

---

### 2.1 创建任务

```
POST /api/tasks
Content-Type: application/json
```

**Body**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | ✅ | 任务标题，建议格式：`[类别] 资源名称` |
| description | string | | 详细说明（风格要求、参考链接等） |
| category | string | | 资源分类（来自 project.yaml 的 categories） |
| priority | string | | 优先级：紧急/高/中/低，默认「中」 |
| created_by | string | | 创建人标识 |
| due_date | string | | 截止日期，格式 `YYYY-MM-DD` |

**示例**：
```json
{
  "title": "[卡牌插画] 火焰法师 - 稀有卡",
  "description": "风格参考：暗黑幻想，主色调红/橙，需要动态感。分辨率 512x768。",
  "category": "卡牌插画",
  "priority": "高",
  "created_by": "AI-ProjectManager",
  "due_date": "2026-03-20"
}
```

**响应** `201`：
```json
{"id": "550e8400-e29b-41d4-a716-446655440000", "ok": true}
```

---

### 2.2 批量创建任务（AI 常用模式）

平台无批量接口，AI 应循环调用 `POST /api/tasks`：

```python
import requests, time

tasks = [
    {"title": "[卡牌插画] 火焰法师", "category": "卡牌插画", "priority": "高"},
    {"title": "[UI界面] 主菜单背景", "category": "UI界面", "priority": "中"},
    {"title": "[角色立绘] 盗贼·全身像", "category": "角色立绘", "priority": "高"},
    # ...
]

BASE = "http://localhost:8899"
for t in tasks:
    r = requests.post(f"{BASE}/api/tasks", json=t)
    print(r.json())
    time.sleep(0.1)  # 避免过快
```

---

### 2.3 查询任务列表

```
GET /api/tasks?status=pending&category=卡牌插画
```

**Query 参数**（均可选）：

| 参数 | 说明 |
|------|------|
| status | pending / in_review / approved / rejected / changes_requested |
| category | 分类名称（与 project.yaml 保持一致） |
| assignee | 认领人名称 |

**响应**：
```json
[
  {
    "id": "550e8400-...",
    "title": "[卡牌插画] 火焰法师",
    "category": "卡牌插画",
    "priority": "高",
    "status": "pending",
    "assignee": null,
    "created_by": "AI-ProjectManager",
    "created_at": "2026-03-11T04:00:00Z",
    "updated_at": "2026-03-11T04:00:00Z",
    "due_date": "2026-03-20",
    "attachments": []
  }
]
```

---

### 2.4 获取单个任务（含审核记录和活动日志）

```
GET /api/tasks/{task_id}
```

**响应**（比列表多 `reviews` 和 `activity`）：
```json
{
  "id": "550e8400-...",
  "title": "[卡牌插画] 火焰法师",
  "status": "approved",
  "reviews": [
    {
      "id": "...",
      "reviewer": "主美",
      "status": "approved",
      "comment": "构图和色调都符合要求，可以进入集成",
      "created_at": "2026-03-12T08:30:00Z"
    }
  ],
  "activity": [
    {"action": "created", "actor": "AI-ProjectManager", "created_at": "..."},
    {"action": "claimed", "actor": "主美", "created_at": "..."},
    {"action": "review:approved", "actor": "主美", "created_at": "..."}
  ]
}
```

---

### 2.5 删除任务

```
DELETE /api/tasks/{task_id}
```

> ⚠️ **限制**：只能删除状态为 `pending`（未被认领）的任务。一旦任务被认领（`in_review` 及之后），不可删除。

**响应** `200`：
```json
{"ok": true}
```

**响应** `403`（任务已被接手）：
```json
{"error": "无法删除：任务已处于「in_review」状态，只有未被接手的任务（pending）才能删除"}
```

---

### 2.6 更新任务字段

```
PUT /api/tasks/{task_id}
Content-Type: application/json
```

可更新字段：`title` `description` `category` `priority` `status` `assignee` `due_date`

```json
{
  "priority": "紧急",
  "due_date": "2026-03-15",
  "actor": "CTO"
}
```

---

## 三、审核工作流 API

### 3.1 认领任务（pending → in_review）

```
POST /api/tasks/{task_id}/claim
Content-Type: application/json
```

```json
{"assignee": "主美"}
```

**响应** `200`：`{"ok": true}`
**响应** `409`：任务已被认领

---

### 3.2 提交审核结果（in_review/changes_requested → approved/rejected/changes_requested）

```
POST /api/tasks/{task_id}/review
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| reviewer | string | ✅ | 审核员名称 |
| status | string | ✅ | `approved` / `rejected` / `changes_requested` |
| comment | string | | 审核意见 |

```json
{
  "reviewer": "主美",
  "status": "approved",
  "comment": "色调和构图均符合要求，通过。"
}
```

> 📌 当 `status = approved` 时，平台会自动触发 `project.yaml` 中配置的 `cicd.webhook_url`（如有），并发送飞书通知。

**响应** `200`：
```json
{"ok": true, "review_id": "..."}
```

---

## 四、CI/CD 触发 API

### 4.1 手动触发 CI/CD（用于测试配置）

```
POST /api/tasks/{task_id}/trigger-cicd
```

无需请求体。触发与审核通过时相同的 CI/CD 流程（reviewer 标记为 `manual-test`）。

**响应** `200`：
```json
{
  "ok": true,
  "triggered": ["github_actions"]
}
```

`triggered` 数组包含实际触发成功的方式，可能的值：`webhook` / `github_actions` / `gitlab_pipeline`。

**响应** `404`：任务不存在

---

### 4.2 自动触发时机

审核结果为 `approved` 时，平台自动触发所有已配置的 CI/CD 方式。

---

### 4.3 支持的三种触发方式

#### 方式 1：自定义 Webhook
配置 `cicd.webhook_url`（非 GitHub API 地址），平台会 POST 以下 JSON：
```json
{
  "task_id": "550e8400-...",
  "event": "task_approved",
  "title": "任务标题",
  "reviewer": "主美"
}
```

#### 方式 2：GitHub Actions `repository_dispatch`
配置 `cicd.repo_url`（含 `github.com`）和 `cicd.ci_token`（Personal Access Token，需要 `repo` 权限）。

平台会向 `https://api.github.com/repos/{owner}/{repo}/dispatches` 发送：
```json
{
  "event_type": "art_approved",
  "client_payload": {
    "task_id": "550e8400-...",
    "title": "任务标题",
    "reviewer": "主美",
    "approved_at": "2026-03-11T08:00:00Z"
  }
}
```

在 GitHub Actions workflow 中监听：
```yaml
on:
  repository_dispatch:
    types: [art_approved]
```

`event_type` 可通过 `cicd.github_actions_event` 自定义（默认 `art_approved`）。

#### 方式 3：GitLab Pipeline Trigger
配置 `cicd.gitlab_token` 和 `cicd.gitlab_trigger_url`（GitLab 项目 trigger URL）。

平台会以表单形式 POST：
```
token=<gitlab_token>
ref=main
variables[ART_TASK_ID]=550e8400-...
variables[ART_TASK_TITLE]=任务标题
```

---

### 4.4 project.yaml CI/CD 完整字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `cicd.repo_url` | string | Git 仓库地址（含 `github.com` 则启用 GitHub Actions 触发） |
| `cicd.branch` | string | GitLab Pipeline 触发分支（默认 `main`） |
| `cicd.ci_token` | string | GitHub PAT（repo 权限）或其他 token |
| `cicd.webhook_url` | string | 自定义 Webhook URL（非 GitHub API 地址） |
| `cicd.gitlab_token` | string | GitLab CI trigger token |
| `cicd.gitlab_trigger_url` | string | GitLab pipeline trigger API URL |
| `cicd.github_actions_event` | string | GitHub Actions event type（默认 `art_approved`） |

---

## 五、文件上传 API

### 4.1 上传美术资源文件

```
POST /api/tasks/{task_id}/upload
Content-Type: multipart/form-data
```

表单字段：`file` — 文件内容

支持格式（可在 project.yaml 配置）：`png jpg jpeg gif webp psd svg mp4 fbx obj unity3d`

**示例（curl）**：
```bash
curl -X POST http://localhost:8899/api/tasks/{task_id}/upload \
  -F "file=@character_mage.png"
```

**响应** `201`：
```json
{"asset_id": "...", "filename": "uuid.png", "ok": true}
```

---

### 4.2 查询任务附件列表

```
GET /api/tasks/{task_id}/assets
```

**响应**：
```json
[
  {
    "id": "...",
    "task_id": "...",
    "filename": "uuid.png",
    "original": "character_mage.png",
    "file_size": 204800,
    "mime_type": "image/png",
    "uploaded_at": "2026-03-11T06:00:00Z"
  }
]
```

---

### 4.3 访问上传的文件

```
GET /api/uploads/{task_id}/{filename}
```

直接返回文件内容，可在浏览器预览或下载。

---

## 六、统计 API

```
GET /api/stats
```

**响应**：
```json
{
  "total": 42,
  "pending": 10,
  "in_review": 8,
  "approved": 20,
  "rejected": 2,
  "changes_requested": 2
}
```

---

## 七、AI 接入完整示例

以下是新游戏项目 AI 接入本平台的完整流程（Python 伪代码）：

```python
import requests

BASE = "http://150.109.95.186:8899"  # 替换为实际地址

# Step 1: 配置项目信息
requests.put(f"{BASE}/api/config/project", json={
    "project": {"name": "龙虾卡牌游戏 v2"},
    "cicd": {
        "repo_url": "https://github.com/hewenze11/card-game",
        "webhook_url": "https://api.github.com/repos/hewenze11/card-game/dispatches"
    },
    "review": {
        "categories": ["卡牌插画", "角色立绘", "UI界面", "场景背景", "特效", "图标", "其他"],
        "reviewers": ["CTO", "主美", "程序"]
    },
    "notifications": {"feishu_webhook": "https://open.feishu.cn/..."}
})

# Step 2: 根据游戏设计，批量注入美术任务
art_tasks = [
    # 卡牌插画（50张）
    {"title": f"[卡牌插画] 英雄卡-{i:02d}", "category": "卡牌插画", "priority": "高"}
    for i in range(1, 51)
] + [
    # UI 界面
    {"title": "[UI界面] 主菜单", "category": "UI界面", "priority": "紧急"},
    {"title": "[UI界面] 战斗HUD", "category": "UI界面", "priority": "高"},
    {"title": "[UI界面] 卡组构建界面", "category": "UI界面", "priority": "中"},
]

for task in art_tasks:
    task["created_by"] = "AI-ProjectManager"
    r = requests.post(f"{BASE}/api/tasks", json=task)
    print(f"创建: {task['title']} → {r.json()['id']}")

# Step 3: 监控进度
stats = requests.get(f"{BASE}/api/stats").json()
print(f"总任务: {stats['total']}, 已通过: {stats['approved']}")

# Step 4: 查询需要修改的任务，通知对应美术
needs_change = requests.get(f"{BASE}/api/tasks?status=changes_requested").json()
for t in needs_change:
    detail = requests.get(f"{BASE}/api/tasks/{t['id']}").json()
    last_review = detail['reviews'][0] if detail['reviews'] else {}
    print(f"需修改: {t['title']} — {last_review.get('comment', '')}")
```

---

## 八、project.yaml 字段速查

| 路径 | 类型 | 用途 |
|------|------|------|
| `project.name` | string | 平台顶栏显示的项目名 |
| `project.description` | string | 项目描述 |
| `cicd.repo_url` | string | Git 仓库地址（含 `github.com` 则启用 GitHub Actions 触发） |
| `cicd.webhook_url` | string | 任务通过时 POST 触发的自定义 Webhook |
| `cicd.ci_token` | string | GitHub PAT（repo 权限），用于触发 GitHub Actions |
| `cicd.gitlab_token` | string | GitLab CI trigger token |
| `cicd.gitlab_trigger_url` | string | GitLab pipeline trigger API URL |
| `cicd.github_actions_event` | string | GitHub Actions event type（默认 `art_approved`） |
| `review.categories` | list | 美术分类列表（AI 可自定义） |
| `review.reviewers` | list | 审核员名单 |
| `review.priorities` | list | 优先级选项 |
| `notifications.feishu_webhook` | string | 飞书通知 Webhook |
| `storage.max_file_size_mb` | int | 最大上传文件大小（MB） |
| `storage.allowed_extensions` | list | 允许上传的文件扩展名 |
| `server.port` | int | 服务端口（默认 8899） |

---

## 九、curl 快速命令速查

```bash
BASE="http://localhost:8899"

# 读配置
curl $BASE/api/config/project

# 更新配置
curl -X PUT $BASE/api/config/project \
  -H "Content-Type: application/json" \
  -d '{"project":{"name":"龙虾卡牌"},"cicd":{"repo_url":"https://github.com/..."}}'

# 创建任务
curl -X POST $BASE/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"[角色] 主角-站立","category":"角色立绘","priority":"高"}'

# 查询待认领任务
curl "$BASE/api/tasks?status=pending"

# 认领任务
curl -X POST $BASE/api/tasks/{id}/claim \
  -H "Content-Type: application/json" \
  -d '{"assignee":"主美"}'

# 审核通过
curl -X POST $BASE/api/tasks/{id}/review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"主美","status":"approved","comment":"风格符合，通过"}'

# 删除未认领任务
curl -X DELETE $BASE/api/tasks/{id}

# 统计
curl $BASE/api/stats
```

---

## 十、一键部署命令

```bash
# 在游戏项目服务器上执行（自动安装并启动）
curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash

# 自定义端口
PORT=9000 curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash

# 部署后，AI 通过 API 填写项目信息，无需登录服务器
curl -X PUT http://localhost:8899/api/config/project \
  -H "Content-Type: application/json" \
  -d '{"project":{"name":"新游戏项目"}}'
```

---

*本文档由 ArtHub 平台自动生成，供 AI 接入使用。*
