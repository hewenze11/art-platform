#!/bin/bash
# =============================================================
# 🎨 美术资源审核平台 - 一键安装脚本
# 
# 使用方法（在目标项目服务器上执行）：
#   curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/art-platform/main/install.sh | bash
#
# 或指定端口：
#   curl -fsSL .../install.sh | PORT=9000 bash
#
# 或指定安装目录：
#   curl -fsSL .../install.sh | INSTALL_DIR=/opt/art bash
# =============================================================

set -e

# ─── 配置 ────────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/art-platform}"
PORT="${PORT:-8899}"
IMAGE="${IMAGE:-art-platform:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-art-platform}"

# GitHub 仓库地址（如果需要从 GHCR 拉取镜像，修改此处）
# GHCR_IMAGE="ghcr.io/your-org/art-platform:latest"

# ─── 颜色输出 ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

banner() {
  echo ""
  echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${CYAN}║    🎨 美术资源审核平台  一键部署脚本      ║${NC}"
  echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${NC}"
  echo ""
}

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()      { echo -e "${GREEN}[ OK ]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERR ]${NC} $1"; exit 1; }
step()    { echo ""; echo -e "${BOLD}▶ $1${NC}"; }

# ─── 检查依赖 ─────────────────────────────────────────────────
check_deps() {
  step "检查依赖..."
  for cmd in docker; do
    if command -v $cmd &>/dev/null; then
      ok "$cmd 已安装"
    else
      error "$cmd 未找到，请先安装 Docker: https://docs.docker.com/get-docker/"
    fi
  done

  # 检查 docker compose (v2) 或 docker-compose (v1)
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    ok "docker compose (v2) 已安装"
  elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
    ok "docker-compose (v1) 已安装"
  else
    warn "未找到 docker-compose，将使用 docker run 方式启动"
    COMPOSE_CMD=""
  fi
}

# ─── 创建目录结构 ─────────────────────────────────────────────
setup_dirs() {
  step "创建安装目录: $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR/data"
  ok "目录创建完成"
}

# ─── 写入配置文件 ─────────────────────────────────────────────
setup_config() {
  local cfg="$INSTALL_DIR/project.yaml"
  if [ -f "$cfg" ]; then
    warn "project.yaml 已存在，跳过（保留现有配置）"
    return
  fi
  step "生成默认项目配置文件..."
  cat > "$cfg" << 'YAML'
# ============================================================
# 美术资源审核平台 - 项目配置文件
# 请修改以下配置以绑定本项目的信息
# ============================================================

project:
  name: "我的游戏项目"           # 改成你的项目名称
  description: "游戏美术资源审核平台"
  logo_url: ""

cicd:
  repo_url: ""                   # CI/CD 仓库地址，如 https://github.com/org/repo
  branch: "main"
  ci_token: ""                   # GitHub Token（触发 CI 用）
  webhook_url: ""                # CI/CD Webhook URL

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
  feishu_webhook: ""             # 飞书 Webhook（任务变更通知）
  wecom_webhook: ""              # 企业微信 Webhook

server:
  port: 8899
  debug: false
YAML
  ok "project.yaml 已生成: $cfg"
}

# ─── 写入 docker-compose.yaml ─────────────────────────────────
setup_compose() {
  step "生成 docker-compose.yaml..."
  cat > "$INSTALL_DIR/docker-compose.yaml" << COMPOSE
version: "3.8"
services:
  art-platform:
    image: ${IMAGE}
    container_name: ${CONTAINER_NAME}
    restart: unless-stopped
    ports:
      - "${PORT}:8899"
    volumes:
      - ./data:/data
      - ./project.yaml:/app/project.yaml
    environment:
      - CONFIG_PATH=/app/project.yaml
      - DATA_DIR=/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8899/api/stats"]
      interval: 30s
      timeout: 10s
      retries: 3
COMPOSE
  ok "docker-compose.yaml 已生成"
}

# ─── 构建或拉取镜像 ───────────────────────────────────────────
setup_image() {
  step "准备 Docker 镜像..."

  # 检查镜像是否已存在
  if docker image inspect "$IMAGE" &>/dev/null 2>&1; then
    ok "镜像 $IMAGE 已存在，跳过构建"
    return
  fi

  # 判断是本地构建还是从 Registry 拉取
  if echo "$IMAGE" | grep -q "ghcr.io\|docker.io\|registry"; then
    info "从 Registry 拉取镜像: $IMAGE"
    docker pull "$IMAGE" || error "镜像拉取失败，请检查镜像地址或网络"
  else
    # 从当前目录构建（适用于本地开发）
    if [ -f "$(dirname $0)/Dockerfile" ] || [ -f "./Dockerfile" ]; then
      info "从 Dockerfile 构建镜像..."
      docker build -t "$IMAGE" "$(dirname $0)" || docker build -t "$IMAGE" . || error "镜像构建失败"
    else
      warn "未找到 Dockerfile，尝试从 Docker Hub 拉取..."
      docker pull "$IMAGE" 2>/dev/null || error "无法获取镜像 $IMAGE，请确认镜像地址正确"
    fi
  fi
  ok "镜像准备完成"
}

# ─── 启动服务 ──────────────────────────────────────────────────
start_service() {
  step "启动服务..."

  # 停止已有容器
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "发现已有容器 $CONTAINER_NAME，停止并重建..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm   "$CONTAINER_NAME" 2>/dev/null || true
  fi

  cd "$INSTALL_DIR"

  if [ -n "$COMPOSE_CMD" ]; then
    $COMPOSE_CMD up -d
  else
    docker run -d \
      --name "$CONTAINER_NAME" \
      --restart unless-stopped \
      -p "${PORT}:8899" \
      -v "${INSTALL_DIR}/data:/data" \
      -v "${INSTALL_DIR}/project.yaml:/app/project.yaml" \
      -e "CONFIG_PATH=/app/project.yaml" \
      -e "DATA_DIR=/data" \
      "$IMAGE"
  fi

  ok "容器已启动"
}

# ─── 等待健康检查 ──────────────────────────────────────────────
wait_ready() {
  step "等待服务就绪..."
  local max=30 i=0
  while [ $i -lt $max ]; do
    if curl -sf "http://localhost:${PORT}/api/stats" >/dev/null 2>&1; then
      ok "服务已就绪！"
      return
    fi
    sleep 2
    i=$((i+1))
    echo -n "."
  done
  echo ""
  warn "服务未在 ${max} 次检测内就绪，请检查日志: docker logs $CONTAINER_NAME"
}

# ─── 完成提示 ──────────────────────────────────────────────────
print_done() {
  echo ""
  echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}${GREEN}║   ✅  美术资源审核平台部署完成！                      ║${NC}"
  echo -e "${BOLD}${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
  echo -e "${BOLD}${GREEN}║                                                      ║${NC}"
  echo -e "${BOLD}${GREEN}║   访问地址:  http://$(hostname -I | awk '{print $1}'):${PORT}                  ║${NC}"
  echo -e "${BOLD}${GREEN}║   安装目录:  $INSTALL_DIR             ║${NC}"
  echo -e "${BOLD}${GREEN}║                                                      ║${NC}"
  echo -e "${BOLD}${GREEN}║   ⚙️  配置项目信息（重要！）：                        ║${NC}"
  echo -e "${BOLD}${GREEN}║   编辑 $INSTALL_DIR/project.yaml  ║${NC}"
  echo -e "${BOLD}${GREEN}║   填写 CI/CD 仓库地址、审核员、飞书 Webhook 等        ║${NC}"
  echo -e "${BOLD}${GREEN}║                                                      ║${NC}"
  echo -e "${BOLD}${GREEN}║   常用命令：                                          ║${NC}"
  echo -e "${BOLD}${GREEN}║   查看日志  docker logs -f $CONTAINER_NAME           ║${NC}"
  echo -e "${BOLD}${GREEN}║   停止服务  docker stop $CONTAINER_NAME              ║${NC}"
  echo -e "${BOLD}${GREEN}║   重启服务  docker restart $CONTAINER_NAME           ║${NC}"
  echo -e "${BOLD}${GREEN}║                                                      ║${NC}"
  echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
  echo ""
}

# ─── MAIN ────────────────────────────────────────────────────
banner
check_deps
setup_dirs
setup_config
setup_compose
setup_image
start_service
wait_ready
print_done
