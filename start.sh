#!/usr/bin/env bash
# 一键启动（Git Bash / WSL / macOS / Linux）
# 用法：
#   bash start.sh [端口]        默认 8000
#   NO_BROWSER=1 bash start.sh  不自动打开浏览器（服务器/无头环境）
set -e
cd "$(dirname "$0")"

PORT="${1:-8000}"

echo "============================================"
echo "  AI 模拟面试智能体 - 一键启动"
echo "============================================"
echo

# ---------- 1/4 检测 Python 3.11+ ----------
PY_BIN=""
for cmd in python3 python py; do
  if command -v "$cmd" >/dev/null 2>&1 && \
     "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY_BIN="$cmd"
    break
  fi
done
if [ -z "$PY_BIN" ]; then
  echo "[错误] 未找到 Python 3.11+。请从 https://www.python.org/downloads/ 安装后重试。"
  exit 1
fi
echo "[1/4] 检测到 Python（$PY_BIN）"

# ---------- 2/4 虚拟环境 ----------
if [ -f ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  echo "[2/4] 创建虚拟环境 .venv ..."
  "$PY_BIN" -m venv .venv
  if [ -f ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
  else
    PY=".venv/bin/python"
  fi
fi
echo "[2/4] 虚拟环境就绪（$PY）"

# ---------- 3/4 依赖：requirements.txt 变化时自动重装 ----------
DEPS_CHECK='import hashlib, os, sys
p = ".venv/.deps_sha256"
h = hashlib.sha256(open("requirements.txt", "rb").read()).hexdigest()
sys.exit(0 if (os.path.exists(p) and open(p).read().strip() == h) else 1)'
if "$PY" -c "$DEPS_CHECK" >/dev/null 2>&1; then
  echo "[3/4] 依赖已就绪"
else
  echo "[3/4] 安装/更新依赖（首次可能需要几分钟）..."
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements.txt
  "$PY" -c 'import hashlib; open(".venv/.deps_sha256", "w").write(hashlib.sha256(open("requirements.txt", "rb").read()).hexdigest())'
fi

# ---------- 4/4 启动 ----------
if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
fi

URL="http://127.0.0.1:${PORT}"
echo "[4/4] 启动服务：$URL"
echo "      首次使用可在网页「设置」页选择大模型供应商并填写 API Key。"
echo "      按 Ctrl+C 停止。"
echo

if [ -z "${NO_BROWSER:-}" ]; then
  (
    sleep 3
    if command -v cmd >/dev/null 2>&1; then
      cmd //c start "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$URL" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
      open "$URL" >/dev/null 2>&1 || true
    fi
  ) &
fi

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
