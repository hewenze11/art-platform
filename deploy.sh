#!/bin/bash
# ============================================================
# 美术资源审核平台 - 一键部署脚本
# 支持：Ubuntu / Debian / CentOS / RHEL / Fedora / Alpine
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/hewenze11/art-platform/main/deploy.sh | bash
#   PORT=9000 curl -fsSL ... | bash
# ============================================================
set -e

REPO="hewenze11/art-platform"
BRANCH="${BRANCH:-main}"
IMAGE_NAME="art-platform"
CONTAINER_NAME="art-platform"
PORT="${PORT:-80}"
DATA_DIR="${DATA_DIR:-/opt/art-platform/data}"
CONFIG_DIR="${CONFIG_DIR:-/opt/art-platform/config}"
SRC_DIR="/opt/art-platform/src"

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

# ── 检测 OS ──
OS=""
PKG=""
if [ -f /etc/os-release ]; then
  . /etc/os-release
  case "$ID" in
    ubuntu|debian|linuxmint) OS="debian"; PKG="apt-get" ;;
    centos|rhel|almalinux|rocky) OS="rhel"; PKG="yum" ;;
    fedora) OS="fedora"; PKG="dnf" ;;
    alpine) OS="alpine"; PKG="apk" ;;
    *) OS="unknown" ;;
  esac
fi
info "检测到系统：${PRETTY_NAME:-$OS}"

# ── 安装基础依赖（curl / tar / git） ──
install_deps() {
  case "$PKG" in
    apt-get)
      apt-get update -qq
      apt-get install -y -qq curl tar git ca-certificates >/dev/null 2>&1
      ;;
    yum)
      yum install -y -q curl tar git ca-certificates >/dev/null 2>&1
      ;;
    dnf)
      dnf install -y -q curl tar git ca-certificates >/dev/null 2>&1
      ;;
    apk)
      apk add --no-cache curl tar git ca-certificates >/dev/null 2>&1
      ;;
    *)
      warn "未知包管理器，跳过基础依赖安装"
      ;;
  esac
}

command -v curl &>/dev/null || { info "安装 curl …"; install_deps; }
command -v tar  &>/dev/null || { info "安装 tar …";  install_deps; }

# ── 安装 Docker（如果没有）──
install_docker() {
  info "未检测到 Docker，开始自动安装…"
  case "$PKG" in
    apt-get)
      apt-get update -qq
      apt-get install -y -qq ca-certificates curl gnupg lsb-release >/dev/null 2>&1
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
        $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -qq
      apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null 2>&1
      ;;
    yum)
      yum install -y -q yum-utils >/dev/null 2>&1
      yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo >/dev/null 2>&1
      yum install -y -q docker-ce docker-ce-cli containerd.io >/dev/null 2>&1
      systemctl enable --now docker >/dev/null 2>&1
      ;;
    dnf)
      dnf install -y -q dnf-plugins-core >/dev/null 2>&1
      dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo >/dev/null 2>&1
      dnf install -y -q docker-ce docker-ce-cli containerd.io >/dev/null 2>&1
      systemctl enable --now docker >/dev/null 2>&1
      ;;
    apk)
      apk add --no-cache docker >/dev/null 2>&1
      rc-update add docker default >/dev/null 2>&1
      service docker start >/dev/null 2>&1 || true
      ;;
    *)
      # 万能 fallback：官方一键安装脚本
      warn "使用 Docker 官方安装脚本…"
      curl -fsSL https://get.docker.com | sh
      ;;
  esac
  success "Docker 安装完成"
}

if ! command -v docker &>/dev/null; then
  install_docker
else
  info "Docker 版本：$(docker --version)"
fi

# 确保 Docker 守护进程运行
if ! docker info &>/dev/null; then
  info "启动 Docker 服务…"
  systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
  sleep 2
fi
docker info &>/dev/null || die "Docker 守护进程无法启动，请手动排查"

# ── 下载源码 ──
info "从 GitHub 下载源码 (${REPO}@${BRANCH})…"
mkdir -p "$SRC_DIR" "$DATA_DIR" "$CONFIG_DIR"

# 方式1：tar 直接解压（无需 git）
if curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz" \
     -o /tmp/art-platform-src.tar.gz 2>/dev/null; then
  tar xzf /tmp/art-platform-src.tar.gz -C "$SRC_DIR" --strip-components=1
  rm -f /tmp/art-platform-src.tar.gz
  success "源码下载完成"
else
  # 方式2：git clone 备用
  warn "tar 下载失败，尝试 git clone…"
  command -v git &>/dev/null || install_deps
  rm -rf "$SRC_DIR"
  git clone --depth=1 -b "$BRANCH" "https://github.com/${REPO}.git" "$SRC_DIR"
  success "git clone 完成"
fi

# ── 生成默认 project.yaml（不覆盖已有） ──
if [ ! -f "$CONFIG_DIR/project.yaml" ]; then
  info "生成默认 project.yaml…"
  cat > "$CONFIG_DIR/project.yaml" << 'YAML'
# ============================================================
# 美术资源审核平台 - 项目配置文件
# 填写后平台即绑定到对应游戏项目
# ============================================================

project:
  name: "我的游戏项目"
  description: "游戏美术资源审核平台"
  logo_url: ""

cicd:
  repo_url: ""
  branch: "main"
  ci_token: ""
  webhook_url: ""
  gitlab_token: ""
  gitlab_trigger_url: ""
  github_actions_event: "art_approved"

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
  feishu_webhook: ""
  wecom_webhook: ""

server:
  port: 8899
  debug: false
YAML
  success "project.yaml 已生成 → $CONFIG_DIR/project.yaml"
else
  warn "project.yaml 已存在，保留现有配置"
fi

# ── 停止旧容器 ──
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  warn "停止并删除旧容器 ${CONTAINER_NAME}…"
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm   "$CONTAINER_NAME" >/dev/null 2>&1 || true
fi

# ── 构建镜像 ──
info "构建 Docker 镜像（首次约需 1-2 分钟）…"
docker build -t "${IMAGE_NAME}:latest" "$SRC_DIR" \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  -q && success "镜像构建完成" || die "镜像构建失败，请查看上方错误"

# ── 启动容器 ──
info "启动服务，端口 ${PORT}…"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -p "${PORT}:8899" \
  -v "${DATA_DIR}:/data" \
  -v "${CONFIG_DIR}/project.yaml:/app/project.yaml" \
  -e CONFIG_PATH=/app/project.yaml \
  -e DATA_DIR=/data \
  "${IMAGE_NAME}:latest" >/dev/null

# ── 健康检查 ──
info "等待服务启动…"
READY=0
for i in $(seq 1 15); do
  sleep 2
  if curl -sf "http://localhost:${PORT}/api/stats" >/dev/null 2>&1; then
    READY=1; break
  fi
done

# ── 获取外网 IP ──
PUBLIC_IP=$(curl -sf --max-time 3 https://api.ipify.org 2>/dev/null || \
            curl -sf --max-time 3 https://ipecho.net/plain 2>/dev/null || \
            hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

if [ "$READY" = "1" ]; then
  # ── 复制使用手册到部署目录 ──
  if [ -f "$SRC_DIR/USAGE.md" ]; then
    cp "$SRC_DIR/USAGE.md" "$CONFIG_DIR/USAGE.md"
  fi
  if [ -f "$SRC_DIR/API_REFERENCE.md" ]; then
    cp "$SRC_DIR/API_REFERENCE.md" "$CONFIG_DIR/API_REFERENCE.md"
  fi

  echo ""
  echo -e "${GREEN}================================================${NC}"
  echo -e "${GREEN}   ✅ 部署成功！${NC}"
  echo -e "${GREEN}================================================${NC}"
  echo ""
  echo -e "  🌐 访问地址：    ${YELLOW}http://${PUBLIC_IP}:${PORT}${NC}"
  echo -e "  📖 在线接口文档：${YELLOW}http://${PUBLIC_IP}:${PORT}/api/docs${NC}"
  echo -e ""
  echo -e "  📄 本地文档："
  echo -e "     使用手册：  ${CYAN}${CONFIG_DIR}/USAGE.md${NC}"
  echo -e "     AI接口文档：${CYAN}${CONFIG_DIR}/API_REFERENCE.md${NC}"
  echo -e "     项目配置：  ${CYAN}${CONFIG_DIR}/project.yaml${NC}"
  echo -e ""
  echo -e "  ── 下一步：绑定你的游戏项目 ──"
  echo -e "  ${CYAN}vi ${CONFIG_DIR}/project.yaml${NC}"
  echo -e "  ${CYAN}或通过 API：${NC}"
  echo -e "  ${CYAN}curl -X PUT http://localhost:${PORT}/api/config/project \\${NC}"
  echo -e "  ${CYAN}  -H 'Content-Type: application/json' \\${NC}"
  echo -e "  ${CYAN}  -d '{\"project\":{\"name\":\"我的游戏\"},\"cicd\":{\"repo_url\":\"https://github.com/...\"}}' ${NC}"
  echo ""
else
  echo ""
  warn "服务未能在预期时间内响应，请检查："
  echo "  docker logs ${CONTAINER_NAME}"
  echo "  docker ps -a"
fi
