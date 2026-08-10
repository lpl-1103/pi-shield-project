#!/bin/bash
# 把整個工作區打包成可搬移的壓縮檔。
#
# ## 為什麼需要這支
#
# 整個資料夾 9.6GB，但其中**只有一小部分是不可取代的**：
#
#     7.2G  黃金照片        不可取代（公司多年歷史資料）
#     1.2G  訓練資料集      **可重新產生**（有腳本）
#     394M  已封存的舊產物  確認後可刪
#      40M  程式碼+文件+DB  真正的專案本體
#
# 所以打包分三種模式，依用途選：
#
#     code    只有程式碼、文件、資料庫（約 40MB）—— 換電腦、備份、給人看
#     full    加上模型權重與 NPU artifacts（約 200MB）—— 換機器要能直接跑
#     all     全部，含黃金照片（9.6GB）—— 整批搬走
#
# ## 為什麼可以安全搬移
#
# 2026-08-10 掃過全部程式碼，**沒有寫死專案路徑**：路徑都是從
# `Path(__file__).resolve().parent` 推出來的相對位置。唯一的絕對路徑是
# Homebrew 的函式庫（`/Users/lpl/homebrew/lib/...`），而且那幾處都寫成
# 候選清單有 fallback，換機器不會壞。
#
# 用法:
#     scripts/pack.sh code            # 預設
#     scripts/pack.sh full
#     scripts/pack.sh all /Volumes/USB
set -euo pipefail

MODE="${1:-code}"
OUTDIR="${2:-$HOME/Desktop}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="hardware-dev-$(date +%Y%m%d)-$MODE"
OUT="$OUTDIR/$NAME.tar.gz"

# 任何模式都不打包的東西
COMMON_EXCLUDE=(
    --exclude='.git'                    # 版本歷史另外用 git clone 帶
    --exclude='.venv'
    --exclude='__pycache__'
    --exclude='.DS_Store'
    --exclude='*.pyc'
    --exclude='.claude'
    --exclude='.embedder'
    --exclude='_archive'                # 已確認不用的舊產物
)

case "$MODE" in
  code)
    EXTRA=(
        --exclude='golden_samples/黃金資料'
        --exclude='dataset_vision' --exclude='dataset_synth' --exclude='dataset'
        --exclude='runs_vision' --exclude='runs_final' --exclude='runs'
        --exclude='artifacts_am62a' --exclude='*.onnx' --exclude='*.pt'
        --exclude='data/erp-history'
    ) ;;
  full)
    EXTRA=(
        --exclude='golden_samples/黃金資料'
        --exclude='dataset_vision' --exclude='dataset_synth' --exclude='dataset'
    ) ;;
  all)
    EXTRA=() ;;
  *)
    echo "用法: pack.sh [code|full|all] [輸出目錄]"; exit 2 ;;
esac

echo "打包模式 $MODE  ->  $OUT"
tar czf "$OUT" -C "$(dirname "$ROOT")" "${COMMON_EXCLUDE[@]}" "${EXTRA[@]}" \
    "$(basename "$ROOT")"

SIZE=$(du -h "$OUT" | cut -f1)
echo "✅ $OUT  ($SIZE)"
echo
echo "還原："
echo "  tar xzf $NAME.tar.gz -C <目標目錄>"
if [ "$MODE" = "code" ]; then
    echo
    echo "⚠ code 模式**不含**黃金照片、訓練資料集、模型權重。"
    echo "  模型權重要另外帶（models/*/runs*/、*.onnx、artifacts_am62a/），"
    echo "  否則辨識那條路跑不起來（條碼那條不受影響）。"
fi
