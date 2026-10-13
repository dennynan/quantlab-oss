#!/usr/bin/env bash
# QuantLab OSS · RD-Agent「挖因子」升级补丁 —— 应用脚本
#
# 用法：
#   ./apply.sh /path/to/RD-Agent       给已克隆的 RD-Agent 打补丁（需在 v1.0.0 或兼容提交上）
#   ./apply.sh --clone [-d 目标目录]   自动克隆 microsoft/RD-Agent v1.0.0 到 ./RD-Agent 再打补丁
#
# 打完补丁后，在你的 conda 环境里执行：pip install -e /path/to/RD-Agent
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/quantlab-rdagent-factor-upgrades.patch"
PATCH_SHA256="bfa6a5abd74dcc6a8885338b57fd9b6f0408956076ebc82201c8256be966bb99"
UPSTREAM_URL="https://github.com/microsoft/RD-Agent.git"
UPSTREAM_TAG="v1.0.0"

die() { echo "✗ $*" >&2; exit 1; }

# 0) 校验补丁文件完整性
[ -f "$PATCH" ] || die "找不到补丁文件：$PATCH"
if command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$PATCH" | awk '{print $1}')"
else
  actual="$(sha256sum "$PATCH" | awk '{print $1}')"
fi
[ "$actual" = "$PATCH_SHA256" ] || die "补丁文件校验失败（sha256 不匹配）：$actual"
echo "✓ 补丁文件校验通过"

# 1) 确定目标仓库
TARGET=""
if [ "${1:-}" = "--clone" ]; then
  shift
  TARGET="./RD-Agent"
  if [ "${1:-}" = "-d" ]; then
    TARGET="${2:-}"; [ -n "$TARGET" ] || die "-d 后面缺少目录"
  fi
  [ -e "$TARGET" ] && die "$TARGET 已存在，请换个目录或先删除"
  echo "→ 克隆 $UPSTREAM_URL（$UPSTREAM_TAG）到 $TARGET ..."
  git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_URL" "$TARGET"
else
  TARGET="${1:-}"
  [ -n "$TARGET" ] || die "用法：$0 /path/to/RD-Agent   或   $0 --clone [-d 目标目录]"
fi

[ -d "$TARGET/rdagent" ] || die "$TARGET 看起来不是 RD-Agent 仓库（缺少 rdagent/ 目录）"

# 2) 检查补丁能否干净应用
if ! ( cd "$TARGET" && git apply --check "$PATCH" ); then
  die "补丁无法应用：目标 RD-Agent 的版本与补丁基线不一致（本补丁针对 v1.0.0）"
fi

# 3) 应用
( cd "$TARGET" && git apply "$PATCH" )
echo "✓ 补丁已应用（23 个文件：20 处修改 + 3 个新增模块）"
echo
echo "接下来："
echo "  1) 在装 rdagent 的 conda 环境里执行： pip install -e \"$(cd "$TARGET" && pwd)\""
echo "  2) 在 <RDAGENT_HOME>/.env 配好 LLM 凭证，即可发起因子挖掘"
