# Art Platform — 美术资源管理平台

游戏开发中美术资源与代码解耦的管理工具。AI 注册资源需求，人工审核上传，游戏通过 API 读取。

## 快速启动

```bash
mkdir -p /opt/art-platform/data
cd /opt/art-platform
curl -O https://raw.githubusercontent.com/hewenze11/art-platform/main/docker-compose.yaml
docker pull ghcr.io/hewenze11/art-platform:latest
docker compose up -d
```

访问 `http://服务器IP:8899`

## 核心概念

- **资源位（Slot）**：游戏中一个美术需求，有唯一 `game_key`，如 `player_idle`
- **资源（Resource）**：资源位下的具体文件，有三种状态：
  - 🟢 **正在使用（active）**：当前生效，每个资源位只能有一个
  - 🟡 **未使用（inactive）**：备选库，不影响游戏
  - 🔴 **待删除（pending_delete）**：执行 Sync 后彻底删除
- **占位资源**：资源位没有绿色资源时，自动返回爱因斯坦图/生日歌占位
- **Manifest**：`GET /api/manifest` 游戏读取接口，返回所有资源位的生效资源

## 工作流程

```
AI 注册资源位 → 用户上传图片/审核 → 用户激活（设为绿色）→ 通知 AI 同步 → AI 读取 Manifest → 游戏生效
```

## AI 调用

详见 [AI_API.md](./AI_API.md)

## CI/CD

推送到 `main` 分支自动构建镜像推送到 `ghcr.io/hewenze11/art-platform:latest`。

配置自动部署需在 GitHub 仓库设置：
- `vars.DEPLOY_HOST` — 服务器 IP
- `vars.DEPLOY_USER` — SSH 用户名（如 root）
- `secrets.DEPLOY_KEY` — SSH 私钥
