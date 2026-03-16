# 네이버클라우드 GPU 서버로 AI 학습하기
> AI-16 Phase B — Qwen2.5-7B-Instruct QLoRA 파인튜닝 완전 가이드

이 가이드를 따라하면 **GPU 서버 만들기 → 코드 올리기 → AI 학습 → 파일 받기 → 서버 삭제**까지
처음 하는 분도 혼자 완료할 수 있습니다.

---

## 목차

1. [준비물 확인](#step-0-준비물-확인)
2. [네이버클라우드 가입 및 크레딧 충전](#step-1-네이버클라우드-가입)
3. [GPU 서버 만들기](#step-2-gpu-서버-만들기)
4. [서버에 접속하기](#step-3-서버에-접속하기)
5. [코드 내려받기 & 환경 세팅](#step-4-코드-내려받기--환경-세팅)
6. [AI 학습 실행하기](#step-5-ai-학습-실행하기)
7. [모델 파일 받아오기](#step-6-모델-파일-받아오기)
8. **[⚠️ 서버 삭제하기 — 가장 중요!](#step-7-서버-삭제하기)**

---

## STEP 0. 준비물 확인

시작하기 전에 아래를 준비해 주세요.

| 항목 | 설명 |
|------|------|
| 💳 네이버클라우드 계정 | 없으면 새로 가입 (무료) |
| 💰 결제 수단 | 신용카드 또는 선불 충전 |
| 💻 로컬 PC 터미널 | macOS: 터미널 앱 / Windows: PowerShell 또는 PuTTY |
| 🔑 SSH 키 | 서버 접속에 필요 (아래에서 만드는 방법 설명) |

> 💡 **GPU 서버 예상 비용**: V100 16GB 기준 시간당 약 1,300~1,600원.
> 학습 시간은 약 4~8시간이므로 **최대 1만 원 내외**입니다.
> **학습이 끝나면 즉시 서버를 삭제하세요!**

---

## STEP 1. 네이버클라우드 가입

### 1-1. 회원가입

1. 웹 브라우저를 열고 **www.ncloud.com** 에 접속합니다.
2. 오른쪽 위 **[회원가입]** 버튼을 클릭합니다.
3. 이메일 주소와 비밀번호를 입력하고 가입 완료합니다.
4. 이메일 인증 메일이 오면 **[이메일 인증하기]** 를 클릭합니다.

### 1-2. 결제 수단 등록

1. 로그인 후 오른쪽 위 프로필 아이콘 → **[마이페이지]** 클릭
2. **[결제 수단]** → **[카드 등록]** 클릭
3. 신용카드 정보를 입력하고 등록합니다.

> 💡 결제 수단이 없으면 서버를 만들 수 없습니다. 먼저 등록해 주세요.

---

## STEP 2. GPU 서버 만들기

### 2-1. 콘솔 접속

1. **www.ncloud.com** 로그인 후 오른쪽 위 **[콘솔]** 버튼 클릭
2. 왼쪽 메뉴에서 **[Services]** → **[Compute]** → **[Server]** 클릭

### 2-2. 서버 생성

1. 오른쪽 위 **[서버 생성]** 버튼 클릭
2. 아래 설정을 순서대로 입력합니다.

**① 서버 이미지 선택**
- 운영체제: **Ubuntu**
- 버전: **Ubuntu Server 22.04 LTS** 선택
- 다음 클릭

**② 서버 타입 선택**
- 왼쪽 필터에서 **[GPU]** 탭 클릭
- **V100** 또는 **A100** 타입 선택
  - 추천: `v1.g1.24xlarge` (V100 1개, 16GB VRAM)
- 스토리지: **100GB SSD** 이상 선택 (모델 파일이 큽니다)
- 다음 클릭

**③ 인증 키 설정 (SSH 키)**

처음이라면 새로 만들기:
1. **[인증 키 생성]** 클릭
2. 키 이름: `ai-training-key` 입력
3. **[생성 및 저장]** 클릭
4. `ai-training-key.pem` 파일이 자동으로 다운로드됩니다.
   **→ 이 파일을 절대 잃어버리지 마세요! 없으면 서버에 접속할 수 없습니다.**

**④ 네트워크 ACL / 보안 그룹**
- 기본값 그대로 유지 (SSH 22번 포트 허용됨)

**⑤ 최종 확인 및 생성**
- 설정 내용 확인 후 **[서버 생성]** 클릭
- 서버 생성까지 약 2~5분 소요됩니다.

### 2-3. 공인 IP 할당

서버만 만들면 외부에서 접속이 안 됩니다. 공인 IP를 붙여야 합니다.

1. 왼쪽 메뉴 **[Compute]** → **[Public IP]** 클릭
2. **[공인 IP 신청]** 클릭 → **[확인]** 클릭
3. 생성된 공인 IP를 클릭 → **[서버 적용]** 클릭
4. 방금 만든 서버를 선택 → **[적용]** 클릭
5. 서버 목록으로 돌아가면 **공인 IP 컬럼**에 숫자가 표시됩니다.
   예: `223.xxx.xxx.xxx` — 이 숫자가 **서버 주소**입니다. 메모해 두세요!

---

## STEP 3. 서버에 접속하기

### 3-1. 관리자 비밀번호 확인

1. 서버 목록에서 만든 서버 클릭
2. 오른쪽 위 **[서버 관리 및 설정 변경]** → **[관리자 비밀번호 확인]** 클릭
3. 아까 다운로드한 `ai-training-key.pem` 파일을 업로드
4. **비밀번호**가 화면에 표시됩니다. 메모해 두세요.

### 3-2. SSH로 접속

**macOS / Linux 사용자**

터미널을 열고 아래 명령어를 입력합니다:

```bash
# 1. 키 파일 권한 설정 (처음 한 번만)
chmod 400 ~/Downloads/ai-training-key.pem

# 2. 서버 접속 (서버 IP를 실제 IP로 바꾸세요)
ssh -i ~/Downloads/ai-training-key.pem root@223.xxx.xxx.xxx
```

처음 접속하면 이런 메시지가 나옵니다:
```
Are you sure you want to continue connecting (yes/no)?
```
→ `yes` 를 입력하고 Enter를 누릅니다.

**Windows 사용자**

PowerShell을 열고 동일하게 입력합니다:
```powershell
ssh -i C:\Users\사용자이름\Downloads\ai-training-key.pem root@223.xxx.xxx.xxx
```

> 💡 `root@223.xxx.xxx.xxx:~#` 이 나오면 접속 성공입니다! 🎉

---

## STEP 4. 코드 내려받기 & 환경 세팅

서버에 접속된 상태에서 아래를 순서대로 입력합니다.
각 명령어 입력 후 **Enter**를 눌러주세요.

### 4-1. 필요한 프로그램 설치

```bash
apt-get update -y && apt-get install -y git screen
```

> `screen` 은 터미널을 꺼도 학습이 계속 돌아가게 해주는 프로그램입니다.

### 4-2. 레포지토리 내려받기

```bash
git clone https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP.git
cd tristan050-ai_ondevice_APP
```

### 4-3. 학습 데이터 생성

```bash
python3 scripts/ai/generate_synthetic_data_v1_final.py \
    --count 200 \
    --out-dir data/synthetic_v40
```

완료되면 이런 메시지가 나옵니다:
```
DATASET_SPLIT_TAXONOMY_V1_OK=1
...
```

### 4-4. 환경 세팅 스크립트 실행

```bash
bash scripts/cloud/setup.sh
```

완료되면 이런 메시지가 나옵니다:
```
 환경 세팅 완료! 🎉
 다음 단계: bash scripts/cloud/run_training.sh
```

> 설치 중 오류가 나면 화면에 표시된 오류 메시지를 팀에 공유해 주세요.

---

## STEP 5. AI 학습 실행하기

> ⏱ **학습 시간은 4~8시간** 정도 걸립니다.
> 터미널이 꺼져도 학습이 계속되도록 **screen**을 사용합니다.

### 5-1. screen 세션 시작

```bash
screen -S training
```

검은 화면이 나오면 정상입니다. 그 안에서 계속 진행합니다.

### 5-2. 학습 시작

```bash
bash scripts/cloud/run_training.sh
```

화면에 이런 내용이 흘러갑니다:
```
=== QLoRA 파인튜닝 시작 ===
trainable params: 39,976,960 || all params: ...
{'loss': 2.xxx, 'learning_rate': ...}
```

이건 정상입니다. 숫자가 계속 바뀌면서 학습이 진행되는 것입니다.

### 5-3. 터미널 닫아도 되는 방법

학습 중 터미널을 안전하게 닫으려면:
- 키보드에서 **Ctrl + A** 를 누른 다음 **D** 를 누릅니다.
- `[detached from ...]` 메시지가 나오면 터미널을 닫아도 됩니다.

### 5-4. 나중에 다시 접속해서 진행 상황 보기

```bash
# 서버에 다시 SSH 접속 후:
screen -r training
```

### 5-5. 학습 완료 확인

학습이 끝나면 이런 메시지가 출력됩니다:
```
 학습완료! 이제 파일을 다운로드하세요 🎉
 다음 단계: bash scripts/cloud/download_and_cleanup.sh
```

---

## STEP 6. 모델 파일 받아오기

### 6-1. 압축 스크립트 실행

```bash
bash scripts/cloud/download_and_cleanup.sh
```

완료되면 현재 폴더에 `butler_model_v1.tar.gz` 파일이 생깁니다.

### 6-2. 로컬 PC로 파일 다운로드

서버에서 **Ctrl + A → D** 로 screen에서 나온 다음,
**로컬 PC의 터미널**을 새로 열고 아래를 입력합니다:

```bash
# 모델 파일 다운로드
scp -i ~/Downloads/ai-training-key.pem \
    root@223.xxx.xxx.xxx:/root/tristan050-ai_ondevice_APP/butler_model_v1.tar.gz \
    ./

# 체크섬 파일 다운로드
scp -i ~/Downloads/ai-training-key.pem \
    root@223.xxx.xxx.xxx:/root/tristan050-ai_ondevice_APP/butler_model_v1.tar.gz.sha256 \
    ./
```

### 6-3. 다운로드 완료 확인

```bash
# 파일이 정상인지 확인
shasum -a 256 butler_model_v1.tar.gz

# 서버의 체크섬 파일과 비교
cat butler_model_v1.tar.gz.sha256
```

두 줄의 첫 번째 긴 숫자(해시값)가 **같으면** 파일이 완전히 받아진 것입니다. ✅

---

## STEP 7. 서버 삭제하기

> # ⚠️ 경고: 이 단계를 반드시 실행하세요!
> **GPU 서버는 켜져 있는 동안 매 시간 요금이 청구됩니다.**
> 파일을 다 받은 후에는 **반드시 즉시 서버를 삭제**해 주세요!

> # ⚠️ 다시 한번 경고합니다!
> 서버를 삭제하지 않으면 **매달 수십만 원의 요금**이 청구될 수 있습니다.
> 파일을 로컬에 받은 것을 확인한 즉시 아래 단계를 따라 서버를 삭제하세요.

> # ⚠️ 마지막 경고: 스크립트는 서버를 삭제하지 않습니다!
> `download_and_cleanup.sh` 는 **서버를 삭제하지 않습니다.**
> 서버 삭제는 아래 단계를 따라 **사람이 직접** 해야 합니다.

### 7-1. 공인 IP 반납

1. 네이버클라우드 콘솔 → **[Compute]** → **[Public IP]** 클릭
2. 할당된 공인 IP 체크박스 클릭
3. **[서버 적용 해제]** 클릭 → **[확인]**
4. 다시 해당 IP 선택 → **[공인 IP 반납]** 클릭 → **[확인]**

> 공인 IP를 반납하지 않으면 IP 비용도 따로 청구됩니다!

### 7-2. 서버 삭제

1. **[Compute]** → **[Server]** 클릭
2. 만들었던 서버 체크박스 클릭
3. 상단 **[서버 관리 및 설정 변경]** → **[서버 종료]** 클릭 → **[확인]**
4. 서버 상태가 **"정지"** 로 바뀔 때까지 기다립니다. (1~3분)
5. 다시 서버 체크박스 클릭 → **[서버 삭제]** 클릭 → **[확인]**

### 7-3. 삭제 확인

서버 목록이 **비어 있으면** 삭제 완료입니다. ✅

---

## 자주 묻는 질문 (FAQ)

**Q. screen 세션이 사라졌어요!**
```bash
screen -ls          # 남아있는 세션 목록 확인
screen -r training  # 세션 이름으로 복귀
```

**Q. 학습 중간에 에러가 났어요.**

`output/training.log` 파일에 에러가 기록됩니다:
```bash
tail -50 output/training.log
```
에러 내용을 복사해서 팀에 공유해 주세요.

**Q. 체크포인트에서 이어서 학습하고 싶어요.**

`run_training.sh` 안의 `run_finetune` 호출에 `--resume` 인자를 추가합니다:
```bash
python3 scripts/ai/finetune_qlora_v3_5.py \
    ... \
    --resume output/butler_model_v1/checkpoint-400
```

**Q. 파일이 너무 커서 scp가 느려요.**

네이버클라우드 Object Storage (S3 호환)에 올리면 더 빠릅니다:
```bash
# aws cli 설치 후
aws s3 cp butler_model_v1.tar.gz s3://<버킷명>/ \
    --endpoint-url https://kr.object.ncloudstorage.com
```

---

## 요약 — 한눈에 보기

```
[로컬 PC]                          [네이버클라우드 서버]
    |                                      |
    |-- STEP 1: 가입 & 결제 등록 ----------|
    |-- STEP 2: GPU 서버 & 공인IP 생성 ----|
    |-- STEP 3: SSH 접속 ---------------->|
    |                           STEP 4: git clone & setup.sh
    |                           STEP 5: run_training.sh (4~8시간)
    |                           STEP 6-1: download_and_cleanup.sh
    |<-- STEP 6-2: scp 로 파일 받기 -------|
    |-- STEP 7: 콘솔에서 서버 삭제 --------|  ⚠️ 반드시!
```

---

> 이 가이드에서 막히는 부분이 있으면 해당 단계 번호와 화면에 나온 메시지를 팀에 공유해 주세요.
> Last updated: 2026-03-17
