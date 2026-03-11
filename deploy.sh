#!/bin/bash
# ============================================================
# 美术资源审核平台 - 一键部署脚本
# 用法：curl -fsSL <raw_url>/deploy.sh | bash
#   或：bash deploy.sh
#   自定义端口：PORT=9000 bash deploy.sh
# ============================================================
set -e

REPO_URL="${REPO_URL:-https://github.com/hewenze11/art-platform}"
IMAGE_NAME="art-platform"
CONTAINER_NAME="art-platform"
PORT="${PORT:-8899}"
DATA_DIR="${DATA_DIR:-/opt/art-platform/data}"
CONFIG_DIR="${CONFIG_DIR:-/opt/art-platform/config}"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[ERR]${NC}  $*" >&2; exit 1; }

echo ""
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}   🎨 美术资源审核平台 - 一键部署${NC}"
echo -e "${CYAN}================================================${NC}"
echo ""

# ── 检查 Docker ──
command -v docker &>/dev/null || die "未找到 Docker，请先安装：https://docs.docker.com/engine/install/"
info "Docker 版本：$(docker --version)"

# ── 创建数据目录 ──
info "创建数据目录 $DATA_DIR / $CONFIG_DIR"
mkdir -p "$DATA_DIR" "$CONFIG_DIR"

# ── 生成默认 project.yaml（若不存在）──
if [ ! -f "$CONFIG_DIR/project.yaml" ]; then
  info "生成默认 project.yaml …"
  cat > "$CONFIG_DIR/project.yaml" << 'YAML'
# ============================================================
# 美术资源审核平台 - 项目配置文件
# 填写本文件后平台即绑定到对应游戏项目
# ============================================================

project:
  name: "我的游戏项目"
  description: "游戏美术资源审核平台"
  logo_url: ""

cicd:
  repo_url: ""          # GitHub/GitLab 仓库地址
  branch: "main"
  ci_token: ""          # CI token（可留空）
  webhook_url: ""       # 任务通过后触发的 Webhook URL

storage:
  upload_dir: "/data/uploads"
  max_file_size_mb: 50
  allowed_extensions:
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
  reviewers:
    - "CTO"
    - "主美"
    - "程序"
  priorities:
    - "紧急"
    - "高"
    - "中"
    - "低"
  categories:
    - "角色"
    - "场景"
    - "UI"
    - "特效"
    - "音效"
    - "动画"
    - "其他"

notifications:
  feishu_webhook: ""    # 飞书 Webhook（可留空）
  wecom_webhook: ""     # 企微 Webhook（可留空）

server:
  port: 8899
  debug: false
YAML
  success "project.yaml 已生成到 $CONFIG_DIR/project.yaml"
else
  warn "project.yaml 已存在，跳过生成（保留现有配置）"
fi

# ── 停止并删除旧容器 ──
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  warn "发现已有容器 $CONTAINER_NAME，正在停止并删除…"
  docker stop "$CONTAINER_NAME" &>/dev/null || true
  docker rm   "$CONTAINER_NAME" &>/dev/null || true
fi

# ── 判断镜像来源：本地构建 or 拉取 ──
if [ -f "$(dirname "$0")/Dockerfile" ]; then
  info "检测到本地 Dockerfile，执行本地构建…"
  docker build -t "$IMAGE_NAME" "$(dirname "$0")"
elif [ -n "$IMAGE_NAME" ] && docker image inspect "$IMAGE_NAME" &>/dev/null; then
  info "使用本地已有镜像 $IMAGE_NAME"
else
  # 尝试从 GitHub Container Registry 拉取
  GHCR_IMAGE="${GHCR_IMAGE:-ghcr.io/hewenze11/art-platform:latest}"
  info "尝试拉取镜像 $GHCR_IMAGE …"
  docker pull "$GHCR_IMAGE" && docker tag "$GHCR_IMAGE" "$IMAGE_NAME" || {
    warn "拉取失败，尝试本地构建（需要在项目目录执行）…"
    [ -f "app.py" ] || die "未找到 app.py，请在项目目录运行此脚本，或设置 GHCR_IMAGE 环境变量"
    docker build -t "$IMAGE_NAME" .
  }
fi

# ── 启动容器 ──
info "启动容器 $CONTAINER_NAME，端口 $PORT …"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "$PORT:8899" \
  -v "$DATA_DIR:/data" \
  -v "$CONFIG_DIR/project.yaml:/app/project.yaml" \
  -e CONFIG_PATH=/app/project.yaml \
  -e DATA_DIR=/data \
  "$IMAGE_NAME"

# ── 健康检查 ──
info "等待服务启动…"
sleep 3
for i in 1 2 3 4 5; do
  if curl -sf "http://localhost:${PORT}/api/stats" &>/dev/null; then
    break
  fi
  sleep 2
done

if curl -sf "http://localhost:${PORT}/api/stats" &>/dev/null; then
  success "服务已启动！"
  echo ""
  echo -e "${GREEN}================================================${NC}"
  echo -e "${GREEN}   ✅ 部署成功${NC}"
  echo -e "${GREEN}================================================${NC}"
  echo ""
  echo -e "  🌐 访问地址：  ${YELLOW}http://$(hostname -I | awk '{print $1}'):${PORT}${NC}"
  echo -e "  📁 数据目录：  ${DATA_DIR}"
  echo -e "  ⚙️  配置文件：  ${CONFIG_DIR}/project.yaml"
  echo ""
  echo -e "  ${CYAN}下一步：编辑配置文件绑定你的游戏项目${NC}"
  echo -e "  ${CYAN}  vi ${CONFIG_DIR}/project.yaml${NC}"
  echo -e "  ${CYAN}或通过 API 让 AI 填写：${NC}"
  echo -e "  ${CYAN}  curl -X PUT http://localhost:${PORT}/api/config/project \\${NC}"
  echo -e "  ${CYAN}    -H 'Content-Type: application/json' \\${NC}"
  echo -e '  '"${CYAN}"'    -d '"'"'{"project":{"name":"我的游戏"},"cicd":{"repo_url":"https://github.com/..."}}'"'"'${NC}"
  echo -e "  ${CYAN}完整 API 文档：http://localhost:${PORT}/api/docs${NC}"
  echo ""
else
  warn "服务可能尚未完全启动，请手动检查："
  echo "  docker logs $CONTAINER_NAME"
fi
