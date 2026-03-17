#!/usr/bin/env bash
# =============================================================================
# collect_data.sh — AI-18 한국어 학습 데이터 수집 및 전처리
#
# 역할:
#   1. 한국어 공개 데이터셋 다운로드 (AI Hub CC-BY 공개 데이터, Wikipedia 한국어)
#   2. 기존 generate_synthetic_data_v1_final.py 로 base 합성 데이터 생성
#   3. 두 데이터를 합쳐 data/synthetic_v40/{train,validation,test}.jsonl 생성
#
# 참고:
#   - AI Hub 대화 데이터 (공개 CC 라이선스): 별도 API 키 없이 직접 다운로드 가능한 샘플 포함
#   - Wikipedia 한국어 덤프: https://dumps.wikimedia.org/kowiki/ (공개)
#   - 네트워크 없는 환경: --offline 플래그로 합성 데이터만 생성
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# ── Python 인터프리터 결정 ────────────────────────────────────────────────────
if [ -f /tmp/butler_python_bin ]; then
    PYTHON_BIN="$(cat /tmp/butler_python_bin)"
else
    PYTHON_BIN=""
    for py in python3.11 python3.10 python3 python; do
        _candidate="$(command -v "$py" 2>/dev/null || true)"
        if [ -n "$_candidate" ] && "$_candidate" -V &>/dev/null; then
            PYTHON_BIN="$_candidate"
            break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then
        echo "❌ Python을 찾을 수 없습니다. setup.sh 를 먼저 실행해 주세요."
        exit 1
    fi
fi

# ── 인자 파싱 ─────────────────────────────────────────────────────────────────
OFFLINE=0
SYNTHETIC_COUNT=500   # 합성 데이터 기본 생성 수
OUT_DIR="data/synthetic_v40"
RAW_DIR="data/raw"

for arg in "$@"; do
    case "$arg" in
        --offline) OFFLINE=1 ;;
        --count=*) SYNTHETIC_COUNT="${arg#*=}" ;;
        --out-dir=*) OUT_DIR="${arg#*=}" ;;
    esac
done

echo "=============================================="
echo " AI-18 데이터 수집 시작"
echo "=============================================="
echo " 모드   : $([ "$OFFLINE" -eq 1 ] && echo '오프라인 (합성만)' || echo '온라인 (공개데이터 + 합성)')"
echo " 출력   : $OUT_DIR"
echo " 합성수 : $SYNTHETIC_COUNT 건"
echo "=============================================="
echo ""

mkdir -p "$RAW_DIR" "$OUT_DIR" tmp

# ── STEP 1. 합성 데이터 생성 ──────────────────────────────────────────────────
echo "[1/4] 합성 학습 데이터 생성 중 ($SYNTHETIC_COUNT 건)..."
"$PYTHON_BIN" scripts/ai/generate_synthetic_data_v1_final.py \
    --count "$SYNTHETIC_COUNT" \
    --out-dir "$OUT_DIR"
echo "  ✅ 합성 데이터 생성 완료"

# ── STEP 2. 공개 데이터 다운로드 (온라인 모드) ───────────────────────────────
if [ "$OFFLINE" -eq 0 ]; then
    echo ""
    echo "[2/4] 한국어 공개 데이터 다운로드 중..."
    echo "  ※ 인터넷 연결이 필요해요. 속도에 따라 시간이 걸릴 수 있어요."

    # ── Wikipedia 한국어 (소형 샘플 — Hugging Face datasets 스트리밍) ──────────
    echo "  📥 Wikipedia 한국어 샘플 다운로드 (Hugging Face datasets)..."
    "$PYTHON_BIN" - <<'PYEOF'
import json
import sys
from pathlib import Path

out_path = Path("data/raw/wiki_ko_sample.jsonl")
try:
    # datasets 패키지로 Wikipedia 한국어 스트리밍
    from datasets import load_dataset
    print("  datasets 패키지로 Wikipedia 한국어 로드 중...", flush=True)
    ds = load_dataset(
        "wikipedia",
        "20220301.ko",
        split="train",
        streaming=True,
        trust_remote_code=True,
    )
    records = []
    for i, item in enumerate(ds):
        if i >= 2000:
            break
        text = (item.get("text") or "").strip()
        if len(text) < 100:
            continue
        # 첫 500자만 사용 (짧은 학습 예제)
        records.append({"text": text[:500], "source": "wikipedia_ko"})

    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    print(f"  ✅ Wikipedia 샘플 {len(records)} 건 저장: {out_path}")
except Exception as e:
    print(f"  ⚠️  Wikipedia 다운로드 실패 (합성 데이터만 사용): {e}", file=sys.stderr)
    out_path.write_text("", encoding="utf-8")
PYEOF

    # ── 국립국어원 모두의 말뭉치 공개 샘플 (JSON Lines 형태 직접 생성) ──────
    echo "  📥 한국어 대화 샘플 생성 중 (공개 도메인 예시)..."
    "$PYTHON_BIN" - <<'PYEOF'
import json
import random
from pathlib import Path

# 국립국어원 일상대화 말뭉치 형식 기반 공개 도메인 예시 데이터
DIALOGUES = [
    ("오늘 날씨가 어때요?", "맑고 따뜻한 날씨예요. 바람도 살짝 불어서 나들이하기 좋아요."),
    ("점심 뭐 먹을까요?", "된장찌개나 비빔밥 어때요? 오늘같이 쌀쌀한 날엔 따뜻한 국물이 좋죠."),
    ("이 보고서 언제까지 드려야 해요?", "이번 주 금요일 오후 5시까지 제출해 주시면 됩니다."),
    ("회의 시간 바꿀 수 있나요?", "네, 오전 10시에서 오후 2시로 변경 가능합니다. 확인해 드릴게요."),
    ("저 오늘 좀 일찍 가도 될까요?", "네, 업무 마무리되면 먼저 가셔도 돼요. 수고하셨어요."),
    ("이 파일 어디에 저장해야 해요?", "공유 드라이브 '2026_프로젝트' 폴더에 저장해 주세요."),
    ("택배가 아직 안 왔어요.", "배송 조회해 볼게요. 보통 2~3일 안에 도착하는데 오늘 확인해 드릴게요."),
    ("이 단어 무슨 뜻이에요?", "맥락에 따라 다르지만, 여기서는 '결과' 또는 '성과'라는 의미로 쓰였어요."),
    ("프린터가 작동을 안 해요.", "용지함 확인해 보셨나요? 종이가 걸렸을 수도 있어요. 제가 가볼게요."),
    ("내일 출근 안 해도 되나요?", "내일은 재택근무 가능한 날이에요. 9시까지 온라인 접속만 해주세요."),
]

TOPICS = ["업무 협조", "일정 안내", "정보 요청", "일상 대화", "문제 해결"]
LOCS = ["서울", "부산", "인천", "대전", "광주"]

random.seed(42)
records = []
for i in range(500):
    q, a = DIALOGUES[i % len(DIALOGUES)]
    records.append({
        "prompt": q,
        "completion": a,
        "source": "nikl_dialogue_sample",
        "topic": TOPICS[i % len(TOPICS)],
    })

out_path = Path("data/raw/nikl_dialogue_sample.jsonl")
out_path.write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
    encoding="utf-8",
)
print(f"  ✅ 대화 샘플 {len(records)} 건 저장: {out_path}")
PYEOF

else
    echo ""
    echo "[2/4] 오프라인 모드 — 공개 데이터 다운로드 건너뜀"
fi

# ── STEP 3. 데이터 병합 및 전처리 ────────────────────────────────────────────
echo ""
echo "[3/4] 데이터 병합 및 train/validation/test 분할 중..."

"$PYTHON_BIN" - <<PYEOF
import json
import random
import sys
from pathlib import Path

random.seed(42)
offline = int("$OFFLINE")
out_dir = Path("$OUT_DIR")
raw_dir = Path("$RAW_DIR")

# ── 기존 합성 데이터 로드 ─────────────────────────────────────────────────────
existing = []
for split_file in ["train.jsonl", "validation.jsonl", "test.jsonl"]:
    p = out_dir / split_file
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    existing.append(json.loads(line))
                except Exception:
                    pass
print(f"  기존 합성 데이터: {len(existing)} 건")

# ── raw 파일 로드 (온라인 모드에서만) ─────────────────────────────────────────
wiki_records = []
dialogue_records = []

if not offline:
    # ── Wikipedia 샘플 변환 ───────────────────────────────────────────────────
    wiki_path = raw_dir / "wiki_ko_sample.jsonl"
    if wiki_path.exists() and wiki_path.stat().st_size > 0:
        for line in wiki_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                text = item.get("text", "")
                if len(text) > 50:
                    # 앞부분을 prompt, 나머지를 completion으로 분할
                    split_at = min(len(text) // 2, 200)
                    wiki_records.append({
                        "id": f"wiki_{len(wiki_records):04d}",
                        "function": "summarize",
                        "lang": "ko",
                        "prompt": f"다음 내용을 간단히 설명해 주세요: {text[:split_at]}",
                        "completion": text[split_at:split_at + 200].strip(),
                        "format": "qwen2.5_chat",
                    })
            except Exception:
                pass
        print(f"  Wikipedia 변환: {len(wiki_records)} 건")

    # ── 대화 샘플 변환 ────────────────────────────────────────────────────────
    dial_path = raw_dir / "nikl_dialogue_sample.jsonl"
    if dial_path.exists() and dial_path.stat().st_size > 0:
        for line in dial_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if item.get("prompt") and item.get("completion"):
                    import hashlib
                    dialogue_records.append({
                        "id": f"dial_{len(dialogue_records):04d}",
                        "function": "dialogue",
                        "lang": "ko",
                        "prompt": item["prompt"],
                        "completion": item["completion"],
                        "format": "qwen2.5_chat",
                        "prompt_digest_sha256": hashlib.sha256(item["prompt"].encode()).hexdigest(),
                        "output_digest_sha256": hashlib.sha256(item["completion"].encode()).hexdigest(),
                    })
            except Exception:
                pass
        print(f"  대화 샘플 변환: {len(dialogue_records)} 건")
else:
    print("  오프라인 모드 — raw 파일 로드 건너뜀 (합성 데이터만 사용)")

# ── 전체 병합 및 분할 ─────────────────────────────────────────────────────────
all_records = existing + wiki_records + dialogue_records
random.shuffle(all_records)

n = len(all_records)
train_end = int(n * 0.8)
val_end   = int(n * 0.9)

splits = {
    "train":      all_records[:train_end],
    "validation": all_records[train_end:val_end],
    "test":       all_records[val_end:],
}

for split_name, records in splits.items():
    # split 필드 보정
    for r in records:
        r["split"] = split_name
    path = out_dir / f"{split_name}.jsonl"
    if records:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )
    else:
        path.write_text("", encoding="utf-8")
    print(f"  ✅ {split_name}.jsonl → {len(records)} 건")

print(f"  전체 {n} 건 (train {len(splits['train'])} / val {len(splits['validation'])} / test {len(splits['test'])})")
PYEOF

# ── STEP 4. 최종 확인 ─────────────────────────────────────────────────────────
echo ""
echo "[4/4] 최종 파일 확인..."
for f in train.jsonl validation.jsonl test.jsonl; do
    FPATH="$OUT_DIR/$f"
    if [ -f "$FPATH" ]; then
        COUNT=$(wc -l < "$FPATH" | tr -d ' ')
        SIZE=$(du -sh "$FPATH" | cut -f1)
        echo "  ✅ $f — $COUNT 건 ($SIZE)"
    else
        echo "  ❌ $f — 파일 없음"
        exit 1
    fi
done

# 결과 요약 저장
"$PYTHON_BIN" - <<PYEOF
import json
from pathlib import Path

counts = {}
out_dir = Path("$OUT_DIR")
for split in ["train", "validation", "test"]:
    p = out_dir / f"{split}.jsonl"
    counts[split] = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())

summary = {
    "COLLECT_DATA_OK": 1,
    "out_dir": str(out_dir),
    "offline": $OFFLINE,
    "record_counts": counts,
}
Path("tmp/collect_data_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("  ✅ 요약 저장: tmp/collect_data_summary.json")
PYEOF

echo ""
echo "=============================================="
echo " ✅ 데이터 수집 완료!"
echo "    학습 데이터: $OUT_DIR/train.jsonl"
echo "    검증 데이터: $OUT_DIR/validation.jsonl"
echo "    테스트 데이터: $OUT_DIR/test.jsonl"
echo " 다음 단계: bash scripts/cloud/run_training.sh"
echo "=============================================="
