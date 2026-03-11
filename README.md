# 🎨 美术资源审核平台

**与项目解耦的游戏美术资源审核工具**。每开始一个新游戏项目，一条 curl 命令拉起，编辑一个配置文件即可对应该项目的美术审核流程。

---

## 快速启动

### 方式一：一键 curl 安装（推荐，在项目服务器上执行）

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/art-platform/main/install.sh | bash
```

指定端口或安装目录：

```bash
curl -fsSL .../install.sh | PORT=9000 INSTALL_DIR=/opt/art bash
```

### 方式二：docker-compose

```bash
git clone https://github.com/YOUR_ORG/art-platform.git
cd art-platform
docker compose up -d
```

### 方式三：本地开发

```bash
pip install -r requirements.txt
python app.py
```

---

## 配置项目信息

安装完成后编辑 `project.yaml`（或通过平台 Web 界面的「⚙️ 项目配置」编辑）：

```yaml
project:
  name: "龙虾卡牌游戏"           # 改成你的项目名称

cicd:
  repo_url: "https://github.com/hewenze11/card-game-assets"
  ci_token: "ghp_xxxxx"          # GitHub Token
  webhook_url: ""                # CI/CD Webhook URL（资源通过审核后触发）

review:
  reviewers:
    - "CTO"
    - "主美"
    - "程序"

notifications:
  feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

**填好配置文件 = 直接对应本项目的美术审核**。无需重启，实时生效。

---

## 功能

| 功能 | 说明 |
|------|------|
| 任务管理 | 创建、筛选、搜索美术任务 |
| 任务认领 | 审核员认领 pending 任务 |
| 删除任务 | **只能删除未被接手（pending）的任务** |
| 文件上传 | 拖拽上传资源文件（PNG/PSD/FBX 等） |
| 审核流程 | 通过 / 需修改 / 拒绝，带意见留存 |
| CI/CD 联动 | 任务通过审核后自动触发 Webhook |
| 飞书通知 | 任务状态变更时发送飞书机器人通知 |
| 统计看板 | 各状态任务数量实时统计 |

---

## 任务状态流转

```
pending（待认领）
    │  认领
    ▼
in_review（审核中）
    │  提交审核
    ├──→ approved（已通过）→ 触发 CI/CD Webhook
    ├──→ changes_requested（需修改）→ 可重新提交
    └──→ rejected（已拒绝）
```

> ⚠️ **删除限制**：只有 `pending` 状态的任务可以删除。一旦被认领（进入 `in_review`），无法删除，需通过 `rejected` 流程结束。

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/tasks` | 列出所有任务（支持 status/category/assignee 过滤）|
| POST | `/api/tasks` | 创建任务 |
| GET  | `/api/tasks/:id` | 获取任务详情（含审核记录、活动日志）|
| PUT  | `/api/tasks/:id` | 更新任务字段 |
| DELETE | `/api/tasks/:id` | 删除任务（仅 pending 状态可删）|
| POST | `/api/tasks/:id/claim` | 认领任务 |
| POST | `/api/tasks/:id/review` | 提交审核意见 |
| POST | `/api/tasks/:id/upload` | 上传资源文件 |
| GET  | `/api/tasks/:id/assets` | 列出资源文件 |
| GET  | `/api/stats` | 统计数据 |
| GET  | `/api/config` | 获取项目配置（前端用）|
| GET  | `/api/config/project` | 读取 project.yaml 原文 |
| PUT  | `/api/config/project/raw` | 写入 project.yaml 原文 |

---

## 数据持久化

所有数据存储在 `./data/` 目录：

```
data/
├── artplatform.db    # SQLite 数据库（任务、审核记录、日志）
└── uploads/          # 上传的资源文件
    └── <task_id>/
        └── <file>
```

---

## 目录结构

```
art-platform/
├── app.py              # Flask 后端
├── project.yaml        # 项目配置文件（每个项目独立编辑）
├── requirements.txt
├── Dockerfile
├── docker-compose.yaml
├── entrypoint.sh       # 容器启动脚本
├── install.sh          # 一键安装脚本（curl 入口）
└── templates/
    └── index.html      # 前端单页应用
```
