# 대표 M3 — production 서명키 provisioning + 정식 실측 (복사용 명령)

키 내용·passphrase는 화면/로그/커밋에 절대 출력하지 않는다. 아래 `<repo>`는 저장소 루트
절대경로, 모델 경로는 승인 자산 경로로 치환한다. 각 명령의 정상 출력을 함께 표기했다.

## 1단계 — production 서명키 생성 (1회)

```bash
# (1) 저장소·release 밖의 owner-owned 디렉터리 (0700)
umask 077; mkdir -p "$HOME/.butler_m3"
```
정상 출력: (없음)

```bash
# (2) 32-byte Ed25519 seed를 0600으로 생성 — 내용은 출력하지 않는다
python3 - <<'PY'
import os, secrets
p = os.path.expanduser("~/.butler_m3/owner_signing_seed.hex")
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, secrets.token_hex(32).encode()); os.close(fd)
print("KEY_WRITTEN=1")
PY
```
정상 출력: `KEY_WRITTEN=1`

```bash
# (3) 파일 속성만 확인 (키 내용 미출력)
stat -f "mode=%Sp uid=%u nlink=%l" "$HOME/.butler_m3/owner_signing_seed.hex"
```
정상 출력 예: `mode=-rw------- uid=<owner uid> nlink=1`  (0600, owner 소유, hardlink 1)

```bash
# (4) PUBLIC key만 도출 (공개값 — 안전)
PYTHONPATH="<repo>" python3 - <<'PY'
import importlib.util, os
spec = importlib.util.spec_from_file_location("v", "<repo>/bench/model_tier_b/offline_verifier/verify.py")
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
seed = bytes.fromhex(open(os.path.expanduser("~/.butler_m3/owner_signing_seed.hex")).read().strip())
print("APPROVED_PUBLIC_KEY=" + v.ed25519_publickey(seed).hex())
PY
```
정상 출력: `APPROVED_PUBLIC_KEY=<64 hex>`

**(5) trust policy 교체 승인 commit** — `bench/model_tier_b/policy/m3_owner_trust_policy.json`
에서 `public_key`/`public_key_sha256`/`accepted_key_ids`를 위 `<64 hex>` 및 그 sha256으로
교체(현재 `0x00…` → 실제 공개키), `policy_version`을 2로 올리고 CODEOWNERS 승인 commit.
`revoked_key_ids`의 노출 old key id는 그대로 유지한다. 정책 파일만 변경한다.

**(6) production 하드닝(선택, 부품화 단계 권장)** — seed 파일을 Keychain passphrase로
at-rest 암호화 보관하고 signer가 one-shot FD로 복호화해 사용:
```bash
security add-generic-password -a "$USER" -s butler-m3-owner-signing -w
```
passphrase는 대화형(에코 없음). 이후 서명 시 `security find-generic-password ... -w`를 FD로만 전달.

## 2단계 — 정식 실측

```bash
export BUTLER_MODEL_ASSET_ROOT="<box3_model 디렉터리>"
export BUTLER_BOX3_1_7B_MODEL_RELATIVE="butler-1.7b-v9-2-r2b-q4_k_m.gguf"
echo '{"models":[{"variant_id":"butler-1.7b-v9-2-r2b","path":"<1.7B 절대경로>"},{"variant_id":"qwen3-4b-q4_k_m","path":"<4B 절대경로>"}]}' \
  | PYTHONPATH="<repo>" python3 <repo>/bench/model_tier_b/measure/measure_runner.py
```
정상 출력: `{"schema_version":"butler.bench.formal-measurement.v1", ... "results":[...], "g1_ready":false, ...}`
(1.7B·4B 각 cold3+warm10 p50/p95, TTFT, decode tok/s, peak RSS, Metal offload)

```bash
# 서명된 owner E2E evidence root (production 키 + 커밋 정책)
export BUTLER_BENCH_SIGNING_KEY_FILE="$HOME/.butler_m3/owner_signing_seed.hex"
export BUTLER_BENCH_TRUST_POLICY="<repo>/bench/model_tier_b/policy/m3_owner_trust_policy.json"
export BUTLER_BENCH_TRUST_POLICY_SHA256="$(shasum -a 256 <repo>/bench/model_tier_b/policy/m3_owner_trust_policy.json | cut -d' ' -f1)"
PYTHONPATH="<repo>" python3 <repo>/bench/model_tier_b/owner_e2e/run_owner_e2e.py <output_root>
```
정상 출력: `"structural_verify":"PASS","semantic_verify":"PASS","offline_verifier_exit_code":0`,
그리고 `"m3_evidence_valid":false,"g1_ready":false,"runtime_activation_allowed":0` (자동 승격 금지).

## 불변
- production key는 저장소·release 밖에서만 존재. 저장소 개인키 0.
- M3 실측 성공해도 `M3_EVIDENCE_VALID`까지만. G1/활성화 자동 승격 없음(M4는 별도 게이트).
- 숫자만 보고. 모델 우열·tier 판정 없음.
