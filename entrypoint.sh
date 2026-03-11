#!/bin/sh
# 如果 project.yaml 不存在（首次启动），复制默认配置
if [ ! -f /app/project.yaml ]; then
  echo "[INIT] project.yaml 不存在，使用默认配置..."
  cp /app/project.yaml.default /app/project.yaml
fi

echo "[START] 启动美术资源审核平台..."
exec gunicorn app:app \
  --bind 0.0.0.0:${PORT:-8899} \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
