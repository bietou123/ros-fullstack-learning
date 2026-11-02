#!/usr/bin/env bash
# 打包 Debian 安装包（amd64 / arm64）：内容包 + 前端 → 桌面端资源 → electron-builder。
# 用法：pnpm package:deb（需在 Linux / WSL 中执行）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"
export CSC_IDENTITY_AUTO_DISCOVERY=false

pnpm build
node scripts/scan-secrets.mjs
node scripts/verify.mjs --strict

rm -rf apps/desktop/web
cp -r apps/web/dist apps/desktop/web

pnpm --filter @rl/desktop exec electron-builder --linux deb --x64 --arm64

mkdir -p release
VERSION="$(node -p "require('./package.json').version")"
found=0
for f in "dist/ros-fullstack-learning_${VERSION}_amd64.deb" "dist/ros-fullstack-learning_${VERSION}_arm64.deb"; do
  [ -e "$f" ] || continue
  cp -f "$f" release/
  size=$(du -m "$f" | cut -f1)
  hash=$(sha256sum "$f" | cut -d' ' -f1)
  echo "RELEASE $(basename "$f") ${size} MB sha256=${hash}"
  found=$((found + 1))
done

if [ "$found" -ne 2 ]; then
  echo "deb 产物不完整：期望 amd64/arm64 各一个，实际找到 ${found} 个" >&2
  exit 1
fi
