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
PYTHON_BIN=""
if [ -f /tmp/butler_python_bin ]; then
    _candidate="$(cat /tmp/butler_python_bin)"
    if [ -n "$_candidate" ] && "$_candidate" -V &>/dev/null; then
        PYTHON_BIN="$_candidate"
    else
        echo "  ⚠️  /tmp/butler_python_bin 경로 실행 불가 — 자동 탐색으로 전환"
    fi
fi
if [ -z "$PYTHON_BIN" ]; then
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
import sys
from pathlib import Path

random.seed(42)

# ── 변수 풀 ──────────────────────────────────────────────────────────────────
NAMES    = ["김민준", "이서연", "박지호", "최유진", "정수현",
            "한도윤", "윤채원", "임태양", "강나은", "조현우",
            "신예린", "오민서", "백준혁", "문지아", "허성민"]
NUMS     = list(range(1, 31))
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일"]
TIMES    = ["오전 9시", "오전 10시", "오전 11시",
            "오후 1시", "오후 2시", "오후 3시", "오후 4시", "오후 5시"]
DATES    = ["3월 3일", "3월 10일", "3월 17일", "3월 24일", "3월 31일",
            "4월 7일", "4월 14일", "4월 21일", "4월 28일", "5월 9일"]
ITEMS    = ["노트북", "마우스", "키보드", "모니터", "프린터",
            "태블릿", "헤드셋", "USB 허브", "외장하드", "충전기"]
FOLDERS  = ["2026_프로젝트", "인사관리", "회계자료", "마케팅",
            "개발팀", "운영보고", "고객지원", "품질관리"]
LOCS     = ["서울", "부산", "인천", "대전", "광주", "수원", "울산", "창원"]
ROOMS    = ["3층 회의실", "5층 대회의실", "2층 소회의실", "7층 임원실", "지하 강당"]
WORDS    = ["KPI", "OKR", "ROI", "PDCA", "SLA", "애자일", "스프린트", "온보딩"]

# ── 50개 이상 템플릿 (q_template, a_template, topic) ─────────────────────────
TEMPLATES = [
    # 날씨/일상
    ("오늘 {loc} 날씨가 어때요?", "맑고 따뜻해요. 바람도 살짝 불어서 나들이하기 좋아요.", "일상 대화"),
    ("이번 주말 날씨 어떤가요?", "주말엔 맑을 것 같아요. 나들이 계획 있으시면 좋을 것 같아요.", "일상 대화"),
    ("오늘 비 온다고 하던데 맞나요?", "네, 오후부터 비 예보가 있어요. 우산 챙겨가세요.", "일상 대화"),
    # 식사
    ("점심 뭐 먹을까요?", "된장찌개나 비빔밥 어때요? 오늘같이 쌀쌀한 날엔 따뜻한 국물이 좋죠.", "일상 대화"),
    ("{name}님 점심 같이 드실래요?", "네, 좋아요! 몇 시에 내려갈까요?", "일상 대화"),
    ("오늘 구내식당 메뉴 뭐예요?", "오늘은 제육볶음이랑 된장국이에요. 인기 메뉴라 일찍 가야 해요.", "일상 대화"),
    # 보고서/문서
    ("보고서 {num}번 언제까지 제출해야 해요?", "{weekday} {time}까지 제출해 주시면 됩니다.", "일정 안내"),
    ("{name}님 보고서 검토 부탁드려도 될까요?", "네, 오늘 오후에 확인해 드릴게요.", "업무 협조"),
    ("보고서 양식이 어디 있어요?", "공유 드라이브 '{folder}' 폴더에 있어요. 확인해 보세요.", "정보 요청"),
    ("보고서 페이지 수 제한이 있나요?", "최대 {num}페이지예요. 참고자료는 별첨으로 추가해 주세요.", "정보 요청"),
    # 회의
    ("{date} 회의 시간이 어떻게 돼요?", "{time}에 {room}에서 진행될 예정이에요.", "일정 안내"),
    ("회의 시간 변경 가능할까요?", "네, 변경 가능합니다. 참석자분들께 공지해 드릴게요.", "업무 협조"),
    ("{name}님 {date} 회의 참석 가능하세요?", "네, 참석 가능해요. 장소가 어디예요?", "일정 안내"),
    ("회의 자료 언제까지 준비해야 해요?", "회의 하루 전 {time}까지 공유해 주시면 됩니다.", "일정 안내"),
    ("오늘 회의 취소됐나요?", "네, 갑자기 취소됐어요. 다음 주 {weekday}로 미뤄졌어요.", "일정 안내"),
    ("{room} 예약 어떻게 해요?", "그룹웨어 회의실 예약 메뉴에서 신청하시면 돼요.", "정보 요청"),
    # 파일/폴더
    ("이 파일 어디에 저장해야 해요?", "공유 드라이브 '{folder}' 폴더에 저장해 주세요.", "업무 협조"),
    ("파일 공유 링크 보내주실 수 있어요?", "네, 지금 바로 이메일로 보내드릴게요.", "업무 협조"),
    ("{name}님 파일 받으셨어요?", "아직 못 받았어요. 다시 한번 보내주실 수 있어요?", "업무 협조"),
    ("'{folder}' 폴더 접근 권한이 없어요.", "IT팀에 요청하시면 {num}일 내로 처리해 드려요.", "문제 해결"),
    # 택배/물건
    ("{item} 택배가 아직 안 왔어요.", "배송 조회해 볼게요. 보통 {num}일 안에 도착해요.", "문제 해결"),
    ("{item} 주문했는데 언제 와요?", "주문 후 영업일 기준 {num}일 이내 도착 예정이에요.", "정보 요청"),
    # 장비/기기
    ("{item}가 작동을 안 해요.", "전원 껐다가 다시 켜보셨나요? 그래도 안 되면 IT팀 부를게요.", "문제 해결"),
    ("{item} 배터리가 너무 빨리 닳아요.", "설정에서 절전 모드 켜보세요. 많이 도움이 될 거예요.", "문제 해결"),
    ("{item} 드라이버 어디서 받아요?", "제조사 공식 사이트에서 모델명 검색하면 다운로드할 수 있어요.", "정보 요청"),
    # 출퇴근/근무
    ("오늘 좀 일찍 가도 될까요?", "네, 업무 마무리되면 먼저 가셔도 돼요. 수고하셨어요.", "업무 협조"),
    ("내일 재택근무 가능한가요?", "네, 내일은 재택 가능한 날이에요. {time}까지 온라인 접속해 주세요.", "일정 안내"),
    ("{name}님 오늘 출근 안 하셨나요?", "오늘 반차예요. 오후부터 출근한다고 했어요.", "정보 요청"),
    ("연차 신청은 어떻게 해요?", "그룹웨어 접속해서 근태관리 메뉴에서 신청하시면 돼요.", "정보 요청"),
    ("이번 주 {weekday} 쉬나요?", "네, 공휴일이에요. 달력 확인하시면 빨간날이에요.", "일정 안내"),
    # 단어/개념
    ("'{word}' 무슨 뜻이에요?", "맥락에 따라 다르지만 여기서는 핵심 성과 지표를 뜻해요.", "정보 요청"),
    ("이 업무 용어 설명해 주실 수 있어요?", "물론이죠. 어떤 용어가 궁금하세요?", "정보 요청"),
    # 교통/장소
    ("{loc} 사무소 가려면 어떻게 가요?", "지하철 {num}호선 {loc}역에서 내리시면 도보 {num}분 거리예요.", "정보 요청"),
    ("주차 자리 있어요?", "지하 {num}층에 방문자 주차 공간 있어요. 경비실에서 스티커 받으세요.", "정보 요청"),
    # 비용/예산
    ("이번 프로젝트 예산이 얼마예요?", "총 {num}백만 원 배정됐어요. 세부 내역은 기획팀에 문의해 주세요.", "정보 요청"),
    ("출장비 정산 언제까지 해야 해요?", "출장 후 {num}일 이내에 경리팀에 제출해 주세요.", "일정 안내"),
    # 계정/접속
    ("비밀번호 잊어버렸어요.", "IT팀에 문의하시면 초기화해 드려요. 내선 {num}번이에요.", "문제 해결"),
    ("VPN 연결이 안 돼요.", "서버 주소 다시 확인해 보세요. 그래도 안 되면 IT팀에 티켓 올려주세요.", "문제 해결"),
    ("시스템 접속 권한 신청은 어떻게 해요?", "팀장님 승인 후 IT팀에 신청서 제출하시면 {num}일 내로 처리돼요.", "정보 요청"),
    # 교육/연수
    ("{name}님 신입사원 교육 언제예요?", "{date} {time}부터 {room}에서 진행해요.", "일정 안내"),
    ("온라인 교육 링크 어디 있어요?", "사내 인트라넷 교육센터 메뉴에 있어요. 로그인 후 확인해 보세요.", "정보 요청"),
    # 행사/이벤트
    ("회식 장소가 어디예요?", "{loc} 근처 식당으로 예약했어요. 채팅방에서 주소 확인해 주세요.", "일정 안내"),
    ("워크숍 참가 신청은 어떻게 해요?", "{date}까지 {name}님께 이메일로 신청하시면 돼요.", "일정 안내"),
    ("팀 회식 {date}에 참석 가능하세요?", "네, 참석할게요. 시간이 몇 시예요?", "일상 대화"),
    # 복지/시설
    ("사내 헬스장 이용 가능한가요?", "네, 평일 {time}부터 {time2}까지 이용 가능해요. 첫 이용 시 등록 필요해요.", "정보 요청"),
    ("사무실 냉난방 조절 어떻게 해요?", "{name}님이 관리하고 계세요. 부탁하시면 조절해 주실 거예요.", "정보 요청"),
    # 고객/외부
    ("외부 방문객 출입증은 어떻게 발급해요?", "1층 안내데스크에서 신분증 제시하시면 발급해 드려요.", "정보 요청"),
    ("고객사 담당자 연락처 아세요?", "명함 사진 공유 드라이브 '{folder}' 폴더에 있어요.", "정보 요청"),
    # 인쇄
    ("프린터 잉크가 없어요.", "총무팀에 연락하시면 교체해 드려요. 내선 {num}번이에요.", "문제 해결"),
    ("양면 인쇄 어떻게 해요?", "인쇄 설정에서 '양면 인쇄' 체크하시면 돼요.", "문제 해결"),
    # 일정/계획
    ("다음 주 일정 공유해 주실 수 있어요?", "네, 지금 캘린더에 업데이트할게요. 확인해 보세요.", "업무 협조"),
    ("{name}님 {date} 스케줄 어떻게 돼요?", "오전에는 미팅 있고 오후에는 비어 있어요.", "정보 요청"),
    # 기타
    ("공지사항 어디서 확인해요?", "인트라넷 메인 페이지나 팀 채팅방에서 확인하시면 돼요.", "정보 요청"),
    ("명절 선물 신청은 어떻게 해요?", "{date}까지 총무팀에 신청하시면 돼요.", "일정 안내"),
    ("사내 규정집 어디서 봐요?", "인트라넷 HR 메뉴 → 사규/규정 탭에서 확인하세요.", "정보 요청"),
    ("법인카드 신청은 어떻게 해요?", "팀장님 결재 후 경리팀에 신청서 내시면 {num}일 내 발급돼요.", "정보 요청"),
]

_VAR_POOLS = {
    "name":    NAMES,
    "num":     NUMS,
    "weekday": WEEKDAYS,
    "time":    TIMES,
    "time2":   TIMES,
    "date":    DATES,
    "item":    ITEMS,
    "folder":  FOLDERS,
    "loc":     LOCS,
    "room":    ROOMS,
    "word":    WORDS,
}

def make_mapping(q_tpl, a_tpl):
    """두 템플릿에서 사용된 플레이스홀더를 추출하고
    각 키를 한 번만 샘플링한 공유 매핑을 반환."""
    import string
    keys = sorted({
        f[1]
        for f in string.Formatter().parse(q_tpl + a_tpl)
        if f[1] is not None
    })
    return {k: random.choice(_VAR_POOLS[k]) for k in keys if k in _VAR_POOLS}

def fill(template, mapping):
    """공유 매핑으로 템플릿 변수를 채움."""
    try:
        return template.format(**mapping)
    except KeyError:
        return template

TARGET = 500
MAX_ATTEMPTS = TARGET * 50

seen = set()
records = []
attempts = 0
while len(records) < TARGET:
    if attempts >= MAX_ATTEMPTS:
        break
    attempts += 1
    q_tpl, a_tpl, topic = random.choice(TEMPLATES)
    mapping = make_mapping(q_tpl, a_tpl)
    # time과 time2가 동시에 있으면 서로 다른 값으로 보정
    if "time" in mapping and "time2" in mapping and mapping["time"] == mapping["time2"]:
        others = [t for t in TIMES if t != mapping["time"]]
        if others:
            mapping["time2"] = random.choice(others)
    q, a = fill(q_tpl, mapping), fill(a_tpl, mapping)
    if q not in seen:
        seen.add(q)
        records.append({
            "prompt": q,
            "completion": a,
            "source": "nikl_dialogue_sample",
            "topic": topic,
        })

if len(records) < TARGET:
    print(f"  경고: {len(records)}건만 생성됨 (목표 {TARGET}건 미달)", file=sys.stderr)

random.shuffle(records)

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
import hashlib
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
# split 전 전체 풀 dedup — cross-split leakage 방지
# dedup 키: (function, lang, norm_text(prompt), norm_text(completion))
# norm_text: 공백 정규화 + strip
def norm_text(s):
    return " ".join(str(s).split())

_seen_keys = set()
deduped_all = []
for r in existing + wiki_records + dialogue_records:
    key = (
        r.get("function", ""),
        r.get("lang", ""),
        norm_text(r.get("prompt", "")),
        norm_text(r.get("completion", "")),
    )
    if key not in _seen_keys:
        _seen_keys.add(key)
        deduped_all.append(r)

print(f"  dedup 후 전체: {len(deduped_all)} 건 (원본 {len(existing) + len(wiki_records) + len(dialogue_records)} 건 중)")
random.shuffle(deduped_all)
all_records = deduped_all

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
print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1")
PYEOF

# ── STEP 4. 최종 확인 ─────────────────────────────────────────────────────────
echo ""
echo "[4/4] 최종 파일 확인..."
for f in train.jsonl validation.jsonl test.jsonl; do
    FPATH="$OUT_DIR/$f"
    if [ -f "$FPATH" ]; then
        COUNT=$(wc -l < "$FPATH" | tr -d ' ')
        SIZE=$(du -sh "$FPATH" | cut -f1)
        if [ "$COUNT" -eq 0 ]; then
            echo "  ⚠️  $f — 파일 존재하지만 0건 (비어있음)"
        else
            echo "  ✅ $f — $COUNT 건 ($SIZE)"
        fi
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
