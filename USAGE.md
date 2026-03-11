# 🎨 ArtHub 美术资源审核平台 - 使用手册

> **适用人员**：美术设计师、主美、程序员、项目管理
> **AI 接入文档**：访问 `GET /api/docs` 或查看同目录 `API_REFERENCE.md`

---

## 目录

1. [平台介绍](#一平台介绍)
2. [一键部署](#二一键部署)
3. [项目配置](#三项目配置)
4. [任务管理接口](#四任务管理接口)
5. [审核工作流接口](#五审核工作流接口)
6. [文件上传接口](#六文件上传接口)
7. [评论接口](#七评论接口)
8. [批量操作接口](#八批量操作接口)
9. [CICD集成接口](#九cicd集成接口)
10. [统计接口](#十统计接口)
11. [完整工作流示例](#十一完整工作流示例)
12. [接口速查表](#十二接口速查表)

---

## 一、平台介绍

ArtHub 是一个**与游戏项目解耦的通用美术资源审核平台**，核心理念：

- **一次部署，任意项目复用**：通过 `project.yaml` 绑定不同游戏项目，换项目只需改配置文件
- **AI 友好**：所有操作均通过 HTTP API 完成，AI 可读取 `/api/docs` 自动接入
- **完整审核闭环**：任务创建 → 认领 → 上传资源 → 审核 → 触发 CI/CD 自动化

### 功能一览

| 功能 | 说明 |
|------|------|
| 任务管理 | 创建/查询/更新/删除美术任务 |
| 审核工作流 | 认领 → 上传资源 → 提交审核 → 通过/拒绝/要求修改 |
| 文件上传 | 支持图片/PSD/视频/3D模型，图片可在线预览 |
| 评论系统 | 任务下发表评论，沟通审核细节 |
| 看板视图 | Kanban 视图按状态分列展示，直观掌握进度 |
| 批量操作 | 多选任务批量删除/改优先级/改分类 |
| CI/CD 集成 | 审核通过后自动触发 GitHub Actions / GitLab / Webhook |
| 飞书通知 | 任务变更实时推送飞书卡片消息 |

---

## 二、一键部署

### 2.1 部署命令

在任意 Linux 服务器上执行（需要 root 或 sudo 权限）：

```bash
curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash
```

自定义端口（默认 80）：

```bash
PORT=8899 curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash
```

**脚本会自动完成**：
- 检测 Linux 发行版，自动安装 Docker（如未安装）
- 从 GitHub 下载最新源码并本地构建镜像
- 启动容器，挂载数据目录和配置文件
- 生成默认 `project.yaml`
- 健康检查，输出访问地址

### 2.2 支持的系统

| 系统 | 版本 |
|------|------|
| Ubuntu | 18.04 / 20.04 / 22.04 / 24.04 |
| Debian | 10 / 11 / 12 |
| CentOS / RHEL / AlmaLinux / Rocky | 7 / 8 / 9 |
| Fedora | 36+ |
| Alpine Linux | 3.14+ |
| 其他 Linux | 通过 Docker 官方脚本自动安装 |

### 2.3 部署后文件位置

```
/opt/art-platform/
├── config/
│   └── project.yaml     ← 项目配置文件（核心，编辑此文件绑定项目）
├── data/
│   ├── artplatform.db   ← SQLite 数据库（任务/审核/评论）
│   └── uploads/         ← 上传的美术资源文件
└── src/                 ← 平台源码
```

### 2.4 常用运维命令

```bash
# 查看容器状态
docker ps

# 查看服务日志
docker logs art-platform -f

# 重启服务
docker restart art-platform

# 停止服务
docker stop art-platform

# 更新到最新版本（重新运行部署脚本即可）
curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash
```

---

## 三、项目配置

部署完成后第一件事：**编辑配置文件，将平台绑定到你的游戏项目**。

### 3.1 直接编辑文件

```bash
vi /opt/art-platform/config/project.yaml
```

### 3.2 完整配置说明

```yaml
project:
  name: "我的游戏项目"        # 显示在平台顶部的项目名称（必填）
  description: "游戏美术资源审核平台"

cicd:
  repo_url: "https://github.com/org/game-assets"   # 美术资源仓库地址
  branch: "main"                                     # 分支（GitLab trigger 用）
  ci_token: "ghp_xxxxxxxx"                          # GitHub PAT（需 repo 权限）
  webhook_url: ""                                    # 自定义 Webhook（可选）
  gitlab_token: ""                                   # GitLab CI Token（可选）
  gitlab_trigger_url: ""                             # GitLab Trigger URL（可选）
  github_actions_event: "art_approved"               # GitHub Actions 事件名

storage:
  max_file_size_mb: 50          # 单文件最大体积（MB）
  allowed_extensions:           # 允许上传的文件类型
    - png
    - jpg
    - jpeg
    - gif
    - webp
    - psd
    - svg
    - mp4
    - fbx
    - obj
    - unity3d

review:
  reviewers:                    # 审核员名单（可认领任务的人）
    - "CTO"
    - "主美"
    - "程序"
  priorities:                   # 优先级选项
    - "紧急"
    - "高"
    - "中"
    - "低"
  categories:                   # 美术资源分类（根据项目自定义）
    - "角色"
    - "场景"
    - "UI"
    - "特效"
    - "音效"
    - "动画"
    - "其他"

notifications:
  feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
  wecom_webhook: ""             # 企业微信 Webhook（可选）

server:
  port: 8899
  debug: false
```

### 3.3 通过 API 更新配置

支持只传需要修改的字段，其余字段保留原值：

```bash
curl -X PUT http://你的IP/api/config/project \
  -H "Content-Type: application/json" \
  -d '{
    "project": {"name": "龙虾卡牌游戏"},
    "cicd": {
      "repo_url": "https://github.com/hewenze11/card-game",
      "ci_token": "ghp_xxxxxxxxxx"
    },
    "review": {
      "categories": ["卡牌插画", "角色立绘", "UI界面", "场景背景", "特效", "图标"],
      "reviewers": ["CTO", "主美", "程序"]
    },
    "notifications": {
      "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"
    }
  }'
```

**响应**：`{"ok": true}`

---

## 四、任务管理接口

### 任务状态说明

| 状态 | 含义 |
|------|------|
| `pending` | 待认领 — 任务刚创建，等待审核员接手 |
| `in_review` | 审核中 — 已被认领，正在进行审核 |
| `changes_requested` | 需要修改 — 审核员要求美术修改后重提 |
| `approved` | 已通过 — 审核通过，自动触发 CI/CD |
| `rejected` | 已拒绝 — 审核拒绝，任务终止 |

状态流转图：

```
[pending]
    │
    └─ 认领 ─→ [in_review]
                    │
                    ├─ 通过 ─→ [approved]  ← 自动触发 CI/CD
                    │
                    ├─ 需修改 ─→ [changes_requested]
                    │                │
                    │                └─ 重新认领 ─→ [in_review]
                    │
                    └─ 拒绝 ─→ [rejected]
```

---

### 4.1 创建任务

```
POST /api/tasks
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `title` | string | ✅ | 标题，建议格式：`[分类] 资源名称` |
| `description` | string | | 详细说明：风格要求、参考图、尺寸规格等 |
| `category` | string | | 分类（与 project.yaml categories 对应） |
| `priority` | string | | `紧急` / `高` / `中` / `低`，默认「中」 |
| `created_by` | string | | 创建人 |
| `due_date` | string | | 截止日期 `YYYY-MM-DD` |

```bash
curl -X POST http://你的IP/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "[卡牌插画] 火焰法师 - 稀有卡",
    "description": "风格：暗黑奇幻。主色调红/橙，需要动态感。尺寸：512x768px。",
    "category": "卡牌插画",
    "priority": "高",
    "created_by": "陈煦园",
    "due_date": "2026-03-20"
  }'
```

**响应 201**：

```json
{"id": "550e8400-e29b-41d4-a716-446655440000", "ok": true}
```

> ⚠️ 保存返回的 `id`，后续所有操作都需要用它。

---

### 4.2 查询任务列表

```
GET /api/tasks[?status=xxx&category=xxx&assignee=xxx]
```

```bash
# 全部任务
curl http://你的IP/api/tasks

# 待认领任务
curl "http://你的IP/api/tasks?status=pending"

# 某分类的任务
curl "http://你的IP/api/tasks?category=卡牌插画"

# 某人认领的任务
curl "http://你的IP/api/tasks?assignee=主美"

# 组合筛选
curl "http://你的IP/api/tasks?status=in_review&category=UI界面"
```

---

### 4.3 查询单个任务（含审核记录和操作日志）

```
GET /api/tasks/{task_id}
```

```bash
curl http://你的IP/api/tasks/550e8400-e29b-41d4-a716-446655440000
```

---

### 4.4 更新任务字段

```
PUT /api/tasks/{task_id}
Content-Type: application/json
```

可更新：`title` `description` `category` `priority` `status` `assignee` `due_date`

```bash
# 改优先级
curl -X PUT http://你的IP/api/tasks/550e8400-... \
  -H "Content-Type: application/json" \
  -d '{"priority": "紧急", "actor": "CTO"}'
```

---

### 4.5 删除任务

```
DELETE /api/tasks/{task_id}
```

> ⚠️ **限制**：只有 `pending`（待认领）的任务才可以删除，已认领的任务无法删除。

```bash
curl -X DELETE http://你的IP/api/tasks/550e8400-...
```

**响应 200**：`{"ok": true}`

**响应 403**（已认领，不可删）：

```json
{"error": "无法删除：任务已处于「in_review」状态，只有未被接手的任务（pending）才能删除"}
```

---

## 五、审核工作流接口

### 5.1 认领任务（pending → in_review）

```
POST /api/tasks/{task_id}/claim
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `assignee` | string | ✅ | 认领人名称 |

```bash
curl -X POST http://你的IP/api/tasks/550e8400-.../claim \
  -H "Content-Type: application/json" \
  -d '{"assignee": "主美"}'
```

**响应 200**：`{"ok": true}`

**响应 409**（已被认领）：`{"error": "任务已被认领或已完成"}`

---

### 5.2 提交审核结果

```
POST /api/tasks/{task_id}/review
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `reviewer` | string | ✅ | 审核员名称 |
| `status` | string | ✅ | `approved` / `rejected` / `changes_requested` |
| `comment` | string | | 审核意见（强烈建议填写） |

```bash
# 审核通过
curl -X POST http://你的IP/api/tasks/550e8400-.../review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"主美","status":"approved","comment":"色调和构图均符合，通过。"}'

# 要求修改
curl -X POST http://你的IP/api/tasks/550e8400-.../review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"主美","status":"changes_requested","comment":"背景太暗，法师脸部光影不够，请调整。"}'

# 审核拒绝
curl -X POST http://你的IP/api/tasks/550e8400-.../review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"主美","status":"rejected","comment":"整体风格与项目不符，需重新设计。"}'
```

**响应 200**：`{"ok": true, "review_id": "..."}`

> 📌 **status = approved 时自动触发**：CI/CD（GitHub Actions / GitLab / Webhook）+ 飞书卡片通知

---

## 六、文件上传接口

### 6.1 上传美术文件

```
POST /api/tasks/{task_id}/upload
Content-Type: multipart/form-data（表单字段名：file）
```

支持格式：`png jpg jpeg gif webp psd svg mp4 fbx obj unity3d`（可在 project.yaml 扩展）

```bash
# 上传图片
curl -X POST http://你的IP/api/tasks/550e8400-.../upload \
  -F "file=@character_mage_v2.png"

# 上传 PSD
curl -X POST http://你的IP/api/tasks/550e8400-.../upload \
  -F "file=@character_mage_v2.psd"
```

**响应 201**：`{"asset_id": "...", "filename": "uuid.png", "ok": true}`

---

### 6.2 查询任务附件列表

```
GET /api/tasks/{task_id}/assets
```

```bash
curl http://你的IP/api/tasks/550e8400-.../assets
```

---

### 6.3 预览 / 下载文件

```
GET /api/uploads/{task_id}/{filename}
```

直接在浏览器访问，图片会内联显示，非图片文件会触发下载。

---

## 七、评论接口

### 7.1 获取评论列表

```
GET /api/tasks/{task_id}/comments
```

```bash
curl http://你的IP/api/tasks/550e8400-.../comments
```

---

### 7.2 发表评论

```
POST /api/tasks/{task_id}/comments
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `author` | string | ✅ | 评论人名称 |
| `content` | string | ✅ | 评论内容 |

```bash
curl -X POST http://你的IP/api/tasks/550e8400-.../comments \
  -H "Content-Type: application/json" \
  -d '{"author":"主美","content":"颜色偏冷，火焰应该更偏橙红色"}'
```

**响应 201**：`{"id": "comment-uuid", "ok": true}`

---

### 7.3 删除评论

```
DELETE /api/tasks/{task_id}/comments/{comment_id}
```

```bash
curl -X DELETE http://你的IP/api/tasks/550e8400-.../comments/comment-uuid
```

---

## 八、批量操作接口

```
POST /api/tasks/batch
Content-Type: application/json
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `ids` | array | ✅ | 任务 ID 列表 |
| `action` | string | ✅ | `delete` 或 `update` |
| `data` | object | | update 时的字段更新 |
| `actor` | string | | 操作人（记入日志） |

```bash
# 批量删除（只有 pending 任务会被删，其余跳过）
curl -X POST http://你的IP/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{"ids":["uuid-1","uuid-2"],"action":"delete","actor":"CTO"}'

# 批量改优先级为紧急
curl -X POST http://你的IP/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{"ids":["uuid-1","uuid-2"],"action":"update","data":{"priority":"紧急"},"actor":"CTO"}'

# 批量改分类
curl -X POST http://你的IP/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{"ids":["uuid-1","uuid-2"],"action":"update","data":{"category":"UI界面"}}'
```

**响应 200**：

```json
{
  "ok": true,
  "processed": 2,
  "skipped": 1,
  "skip_reasons": ["任务XXX: 非pending状态不可删除"]
}
```

---

## 九、CI/CD 集成接口

### 9.1 手动触发 CI/CD（用于测试配置）

```
POST /api/tasks/{task_id}/trigger-cicd
```

```bash
curl -X POST http://你的IP/api/tasks/550e8400-.../trigger-cicd
```

**响应 200**：

```json
{"ok": true, "triggered": ["github_actions"]}
```

`triggered` 数组包含成功触发的方式：`webhook` / `github_actions` / `gitlab_pipeline`

---

### 9.2 GitHub Actions 配置步骤

**Step 1** — 在 project.yaml 中配置：

```yaml
cicd:
  repo_url: "https://github.com/org/game-assets"
  ci_token: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  github_actions_event: "art_approved"
```

> GitHub Token 需要 `repo` 权限，在 GitHub → Settings → Developer settings → Personal access tokens 创建。

**Step 2** — 在目标仓库创建 workflow 文件：

```yaml
# .github/workflows/deploy-art.yml
name: 部署审核通过的美术资源

on:
  repository_dispatch:
    types: [art_approved]   # 与 github_actions_event 配置一致

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: 打印任务信息
        run: |
          echo "任务ID: ${{ github.event.client_payload.task_id }}"
          echo "任务名: ${{ github.event.client_payload.title }}"
          echo "审核员: ${{ github.event.client_payload.reviewer }}"

      - uses: actions/checkout@v3

      - name: 部署美术资源
        run: |
          # 在这里写你的资源处理/上传/部署脚本
          echo "部署成功"
```

---

## 十、统计接口

```
GET /api/stats
```

```bash
curl http://你的IP/api/stats
```

**响应 200**：

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

## 十一、完整工作流示例

### 场景：新项目启动，一次性注入 50 个美术任务

```bash
BASE="http://你的服务器IP"

# 1. 配置项目
curl -X PUT $BASE/api/config/project \
  -H "Content-Type: application/json" \
  -d '{
    "project": {"name": "龙虾卡牌游戏"},
    "review": {
      "reviewers": ["CTO","主美","程序"],
      "categories": ["卡牌插画","角色立绘","UI界面","场景背景","特效","图标"]
    },
    "cicd": {"repo_url":"https://github.com/hewenze11/card-game","ci_token":"ghp_xxx"},
    "notifications": {"feishu_webhook":"https://open.feishu.cn/..."}
  }'

# 2. 创建任务
TID=$(curl -s -X POST $BASE/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"[卡牌插画] 火焰法师","category":"卡牌插画","priority":"高","created_by":"陈煦园"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

echo "创建成功，任务ID: $TID"

# 3. 上传资源文件
curl -X POST $BASE/api/tasks/$TID/upload -F "file=@mage.png"

# 4. 发评论
curl -X POST $BASE/api/tasks/$TID/comments \
  -H "Content-Type: application/json" \
  -d '{"author":"主美","content":"颜色参考第3版方案，背景要有光晕效果"}'

# 5. 认领任务
curl -X POST $BASE/api/tasks/$TID/claim \
  -H "Content-Type: application/json" \
  -d '{"assignee":"主美"}'

# 6. 提交审核（通过）→ 自动触发 CI/CD
curl -X POST $BASE/api/tasks/$TID/review \
  -H "Content-Type: application/json" \
  -d '{"reviewer":"主美","status":"approved","comment":"色调到位，发光效果好，通过！"}'

# 7. 查看统计
curl $BASE/api/stats
```

---

## 十二、接口速查表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 读取配置概览 |
| GET | `/api/config/project` | 读取完整配置（YAML） |
| PUT | `/api/config/project` | 更新配置（JSON 补丁） |
| GET | `/api/tasks` | 查询任务列表（支持过滤） |
| POST | `/api/tasks` | 创建任务 |
| POST | `/api/tasks/batch` | 批量操作（删除/更新） |
| GET | `/api/tasks/{id}` | 获取任务详情 |
| PUT | `/api/tasks/{id}` | 更新任务字段 |
| DELETE | `/api/tasks/{id}` | 删除任务（仅 pending） |
| POST | `/api/tasks/{id}/claim` | 认领任务 |
| POST | `/api/tasks/{id}/review` | 提交审核 |
| POST | `/api/tasks/{id}/upload` | 上传文件 |
| GET | `/api/tasks/{id}/assets` | 查询附件列表 |
| GET | `/api/uploads/{id}/{file}` | 下载/预览文件 |
| GET | `/api/tasks/{id}/comments` | 获取评论列表 |
| POST | `/api/tasks/{id}/comments` | 发表评论 |
| DELETE | `/api/tasks/{id}/comments/{cid}` | 删除评论 |
| POST | `/api/tasks/{id}/trigger-cicd` | 手动触发 CI/CD |
| GET | `/api/stats` | 获取统计数据 |
| GET | `/api/docs` | 获取 AI 接口文档（Markdown） |

---

*ArtHub 美术资源审核平台 | https://github.com/hewenze11/art-platform*
