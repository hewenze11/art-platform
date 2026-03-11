# 🎨 ArtHub 美术资源审核平台 v2 - 使用手册

> **适用人员**：美术设计师、主美、程序员、项目管理、AI Agent  
> **架构版本**：v2.0（版本快照驱动）  
> **AI 接入文档**：访问 `GET /api/docs` 获取本文档

---

## 目录

1. [平台介绍](#一平台介绍)
2. [一键部署](#二一键部署)
3. [核心概念：版本快照](#三核心概念版本快照)
4. [项目配置接口](#四项目配置接口)
5. [快照管理接口](#五快照管理接口)
6. [资源管理接口](#六资源管理接口)
7. [审核工作流接口](#七审核工作流接口)
8. [文件上传接口](#八文件上传接口)
9. [评论接口](#九评论接口)
10. [批量操作接口](#十批量操作接口)
11. [统计接口](#十一统计接口)
12. [完整工作流示例](#十二完整工作流示例)
13. [接口速查表](#十三接口速查表)

---

## 一、平台介绍

ArtHub 是一个**与游戏项目解耦的通用美术资源审核平台**，核心理念：

- **版本快照驱动**：所有资源归属于某个版本快照，形成清晰的版本脉络
- **一次部署，任意项目复用**：通过 `project.yaml` 绑定不同游戏项目，换项目只需改配置
- **AI 友好**：所有操作均通过 HTTP API 完成，AI 可读取 `/api/docs` 自动接入
- **完整审核闭环**：快照创建 → 资源添加 → 认领 → 上传 → 审核 → 应用（触发 CI/CD）

---

## 二、一键部署

```bash
curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash
```

**支持系统**：Ubuntu 20.04+、Debian 10+、CentOS 7+、RHEL 8+、Fedora 36+、Alpine 3.14+

**默认端口**：80（无需加端口号直接访问 `http://你的IP`）

**部署后目录**：
```
/opt/art-platform/
├── config/
│   ├── project.yaml      ← 项目配置（可直接编辑）
│   ├── USAGE.md          ← 本文档
│   └── API_REFERENCE.md  ← AI 接入文档
└── data/
    ├── artplatform.db    ← SQLite 数据库
    └── uploads/          ← 上传的文件
```

**修改配置后重启**：
```bash
docker restart art-platform
```

---

## 三、核心概念：版本快照

### 什么是快照

快照（Snapshot）是某一时刻所有美术资源的状态集合，相当于一个版本包：

```
v1.0 [已应用]           ← 线上版本
  └─ 主角立绘    [通过]
  └─ 主菜单背景  [通过]
  └─ 游戏Logo   [通过]

v1.1 [完善中] [已应用]  ← 同时在线 + 还在改
  └─ 继承v1.0所有资源
  └─ 火焰法师卡  [需修改]
  └─ 战斗HUD    [通过]

v2.0 [完善中]           ← 下一版，正在做
  └─ 继承v1.1所有资源
  └─ PVP竞技场  [待认领]
  └─ 段位徽章×6 [待认领]
```

### 快照的两个独立状态

| 状态 | 含义 | 说明 |
|------|------|------|
| `is_refining` | 完善中 | 可以新增/修改/删除资源 |
| `is_applied` | 已应用 | 已触发 CI/CD，已上线 |

两个状态**相互独立**，可以同时为 true（正在上线的版本还在继续完善）。

### 快照归档规则

- 最多保留 **3 个活跃快照**
- 超出时，最旧的快照自动归档（变为只读历史记录）
- 归档快照仍可查看，不可修改

### 资源操作权限

- **只有 `is_refining=true` 的快照** 才能：增删改资源、认领、提交审核
- `is_refining=false` 的快照资源全部锁定，防止误操作

---

## 四、项目配置接口

### 获取配置

```
GET /api/config
```

返回项目基础信息和审核参数（reviewers、priorities、categories）。

### 获取原始 YAML

```
GET /api/config/project
```

返回 `project.yaml` 原文（纯文本）。

### 更新配置（深度合并）

```
PUT /api/config/project
Content-Type: application/json
```

只传需要修改的字段，不影响其他配置：

```bash
curl -X PUT http://your-server/api/config/project \
  -H 'Content-Type: application/json' \
  -d '{
    "project": {
      "name": "我的游戏项目",
      "version": "1.0"
    },
    "cicd": {
      "repo_url": "https://github.com/yourname/game",
      "ci_token": "ghp_xxxxxxx",
      "github_actions_event": "art_snapshot_applied"
    },
    "notifications": {
      "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
    }
  }'
```

### 覆盖写入 YAML（原始格式）

```
PUT /api/config/project/raw
Content-Type: text/plain

project:
  name: 龙虾幻想
  version: "2.0"
cicd:
  repo_url: https://github.com/...
```

---

## 五、快照管理接口

### 获取所有快照

```
GET /api/snapshots
```

返回按创建时间倒序的快照列表，每个快照含 `stats`（资源统计）。

**响应示例**：
```json
[
  {
    "id": "uuid",
    "version": "v2.0",
    "name": "PVP对战模式",
    "is_refining": 1,
    "is_applied": 0,
    "is_archived": 0,
    "created_at": "2026-03-11T07:50:00Z",
    "stats": {
      "total": 12,
      "pending": 8,
      "in_review": 2,
      "approved": 1,
      "rejected": 0,
      "changes_requested": 1
    }
  }
]
```

### 创建快照

```
POST /api/snapshots
Content-Type: application/json
```

```json
{
  "version": "v2.0",
  "name": "PVP对战模式（可选）",
  "created_by": "CTO",
  "inherit_from": "上一个快照的UUID（可选）"
}
```

- `version` 必填
- `inherit_from` 传入时，复制该快照所有资源到新快照，状态重置为 `pending`

**响应**：`{"id": "新快照UUID", "ok": true}` (HTTP 201)

### 获取快照详情

```
GET /api/snapshots/{snapshot_id}
```

返回快照信息 + 所有资源列表 + 活动日志。

### 开始完善

```
POST /api/snapshots/{snapshot_id}/refine
Content-Type: application/json

{"actor": "CTO"}
```

将 `is_refining` 设为 true，快照进入可编辑状态。

### 停止完善

```
POST /api/snapshots/{snapshot_id}/stop-refine
Content-Type: application/json

{"actor": "CTO"}
```

将 `is_refining` 设为 false，资源锁定。

### 应用快照

```
POST /api/snapshots/{snapshot_id}/apply
Content-Type: application/json

{"actor": "CTO"}
```

- 将 `is_applied` 设为 true，记录 `applied_at` 时间
- 触发 CI/CD（GitHub Actions / GitLab Pipeline / 自定义 Webhook）
- 发送飞书通知
- 超出3个活跃快照时自动归档最旧的

**响应**：`{"ok": true, "triggered": ["github_actions"]}`

### 快照对比

```
GET /api/snapshots/{snapshot_id}/diff/{other_snapshot_id}
```

对比两个快照之间的资源差异：

```json
{
  "added": [...],    // 新增的资源
  "removed": [...],  // 移除的资源
  "changed": [       // 状态/优先级变化的资源
    {
      "name": "火焰法师卡",
      "from": {"status": "pending", "priority": "高"},
      "to": {"status": "approved", "priority": "紧急"}
    }
  ]
}
```

---

## 六、资源管理接口

### 获取快照下的资源列表

```
GET /api/snapshots/{snapshot_id}/assets
```

**过滤参数**：
- `?status=pending` — 按状态过滤
- `?category=角色` — 按分类过滤
- `?assignee=主美` — 按认领人过滤

### 创建资源

```
POST /api/snapshots/{snapshot_id}/assets
Content-Type: application/json
```

> ⚠️ 快照必须处于「完善中」状态（`is_refining=true`）

```json
{
  "name": "火焰法师-稀有卡",
  "description": "火焰系法师，稀有品质，卡面1024x1440，需发光特效",
  "category": "角色",
  "priority": "紧急",
  "created_by": "策划"
}
```

**字段说明**：
| 字段 | 必填 | 说明 |
|------|------|------|
| name | ✅ | 资源名称 |
| description | | 详细描述、风格要求 |
| category | | 分类（角色/场景/UI/特效/音效/动画/其他） |
| priority | | 紧急/高/中/低（默认：中） |
| created_by | | 创建人 |

**响应**：`{"id": "资源UUID", "ok": true}` (HTTP 201)

### 获取资源详情

```
GET /api/assets/{asset_id}
```

返回资源信息 + 附件列表 + 审核记录 + 评论 + 活动日志。

### 修改资源

```
PUT /api/assets/{asset_id}
Content-Type: application/json
```

> ⚠️ 快照必须处于「完善中」状态

```json
{
  "name": "新名称",
  "description": "新描述",
  "category": "UI",
  "priority": "高",
  "assignee": "主美",
  "actor": "操作人"
}
```

### 删除资源

```
DELETE /api/assets/{asset_id}
```

> ⚠️ 只有 `pending` 状态的资源可以删除，快照需处于「完善中」

---

## 七、审核工作流接口

### 状态流转

```
pending（待认领）
    │
    ▼ [认领] POST /claim
in_review（审核中）
    │
    ├──▶ approved（已通过）
    ├──▶ rejected（已拒绝）
    └──▶ changes_requested（需修改）
              │
              └──▶ in_review（重新认领后）
```

### 认领资源

```
POST /api/assets/{asset_id}/claim
Content-Type: application/json

{"assignee": "主美"}
```

- 资源必须是 `pending` 状态
- 认领后状态变为 `in_review`
- 发送飞书通知

### 提交审核

```
POST /api/assets/{asset_id}/review
Content-Type: application/json
```

```json
{
  "reviewer": "CTO",
  "status": "approved",
  "comment": "色彩饱满，风格统一，通过"
}
```

**status 枚举**：`approved` / `rejected` / `changes_requested`

### 手动触发 CI/CD（测试用）

```
POST /api/assets/{asset_id}/trigger-cicd
```

测试 CI/CD 配置是否正确，不改变资源状态。

---

## 八、文件上传接口

### 上传文件

```
POST /api/assets/{asset_id}/upload
Content-Type: multipart/form-data
```

```bash
curl -X POST http://your-server/api/assets/{asset_id}/upload \
  -F "file=@/path/to/character.png"
```

**支持格式**：png、jpg、jpeg、gif、webp、psd、svg、mp4、fbx、obj、unity3d

**默认大小限制**：50MB（可在 `project.yaml` 中修改）

**响应**：
```json
{
  "file_id": "uuid",
  "filename": "uuid.png",
  "ok": true
}
```

### 访问上传的文件

```
GET /api/uploads/{asset_id}/{filename}
```

### 获取资源的文件列表

```
GET /api/assets/{asset_id}/files
```

---

## 九、评论接口

### 获取评论

```
GET /api/assets/{asset_id}/comments
```

### 发表评论

```
POST /api/assets/{asset_id}/comments
Content-Type: application/json

{
  "author": "主美",
  "content": "火焰感不足，请参考《暗黑4》法师设计稿重新调整"
}
```

### 删除评论

```
DELETE /api/assets/{asset_id}/comments/{comment_id}
```

---

## 十、批量操作接口

```
POST /api/assets/batch
Content-Type: application/json
```

### 批量删除（仅 pending 资源）

```json
{
  "ids": ["uuid1", "uuid2", "uuid3"],
  "action": "delete"
}
```

### 批量更新属性

```json
{
  "ids": ["uuid1", "uuid2"],
  "action": "update",
  "data": {
    "priority": "紧急",
    "category": "角色"
  },
  "actor": "CTO"
}
```

**可批量更新的字段**：`priority`、`category`、`assignee`、`status`

**响应**：
```json
{
  "ok": true,
  "processed": 2,
  "skipped": 1,
  "skip_reasons": ["资源名称: 快照非完善中状态"]
}
```

---

## 十一、统计接口

```
GET /api/stats
```

**响应**：
```json
{
  "active_snapshots": 3,
  "total_assets": 21,
  "pending": 16,
  "in_review": 0,
  "approved": 4,
  "rejected": 0,
  "changes_requested": 1
}
```

---

## 十二、完整工作流示例

以下 bash 脚本演示从零创建一个版本快照完整走完审核流程：

```bash
BASE="http://your-server"

# 1. 绑定项目
curl -X PUT $BASE/api/config/project \
  -H 'Content-Type: application/json' \
  -d '{"project":{"name":"我的游戏"},"cicd":{"repo_url":"https://github.com/xxx/game","ci_token":"ghp_xxx"}}'

# 2. 创建快照
SNAP=$(curl -s -X POST $BASE/api/snapshots \
  -H 'Content-Type: application/json' \
  -d '{"version":"v1.0","name":"首发版本","created_by":"CTO"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 3. 添加资源
AID=$(curl -s -X POST $BASE/api/snapshots/$SNAP/assets \
  -H 'Content-Type: application/json' \
  -d '{"name":"主角立绘","category":"角色","priority":"高","created_by":"主美"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 4. 上传文件
curl -X POST $BASE/api/assets/$AID/upload -F "file=@character.png"

# 5. 认领资源
curl -X POST $BASE/api/assets/$AID/claim \
  -H 'Content-Type: application/json' \
  -d '{"assignee":"主美"}'

# 6. 审核通过
curl -X POST $BASE/api/assets/$AID/review \
  -H 'Content-Type: application/json' \
  -d '{"reviewer":"CTO","status":"approved","comment":"风格统一，通过"}'

# 7. 应用快照（触发 CI/CD）
curl -X POST $BASE/api/snapshots/$SNAP/stop-refine \
  -H 'Content-Type: application/json' -d '{"actor":"CTO"}'

curl -X POST $BASE/api/snapshots/$SNAP/apply \
  -H 'Content-Type: application/json' -d '{"actor":"CTO"}'

# 8. 下一版：继承 v1.0 创建 v1.1
SNAP2=$(curl -s -X POST $BASE/api/snapshots \
  -H 'Content-Type: application/json' \
  -d "{\"version\":\"v1.1\",\"name\":\"内容更新\",\"created_by\":\"CTO\",\"inherit_from\":\"$SNAP\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 9. 对比两个快照
curl $BASE/api/snapshots/$SNAP/diff/$SNAP2
```

---

## 十三、接口速查表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 获取项目配置 |
| `/api/config/project` | GET / PUT | 获取/更新配置（深度合并） |
| `/api/config/project/raw` | PUT | 覆盖写入原始 YAML |
| `/api/snapshots` | GET | 获取所有快照 |
| `/api/snapshots` | POST | 创建快照 |
| `/api/snapshots/{id}` | GET | 获取快照详情 |
| `/api/snapshots/{id}/refine` | POST | 开始完善 |
| `/api/snapshots/{id}/stop-refine` | POST | 停止完善 |
| `/api/snapshots/{id}/apply` | POST | 应用快照（触发CI/CD） |
| `/api/snapshots/{id}/diff/{other}` | GET | 快照对比 |
| `/api/snapshots/{id}/assets` | GET | 获取快照资源列表 |
| `/api/snapshots/{id}/assets` | POST | 新建资源 |
| `/api/assets/{id}` | GET | 获取资源详情 |
| `/api/assets/{id}` | PUT | 修改资源 |
| `/api/assets/{id}` | DELETE | 删除资源（仅pending） |
| `/api/assets/{id}/claim` | POST | 认领资源 |
| `/api/assets/{id}/review` | POST | 提交审核 |
| `/api/assets/{id}/upload` | POST | 上传文件 |
| `/api/assets/{id}/files` | GET | 获取文件列表 |
| `/api/assets/{id}/comments` | GET / POST | 获取/发表评论 |
| `/api/assets/{id}/comments/{cid}` | DELETE | 删除评论 |
| `/api/assets/batch` | POST | 批量操作（删除/更新） |
| `/api/assets/{id}/trigger-cicd` | POST | 手动触发CI/CD（测试） |
| `/api/stats` | GET | 全局统计数据 |
| `/api/docs` | GET | 获取本文档（Markdown） |
| `/api/uploads/{aid}/{file}` | GET | 访问上传的文件 |
