# FirstScreen v2.3 재현 절차

지원 정본은 Python 3.12, Node.js 24, npm lockfile, Rust 1.97.1이다. 모든 verifier는 성공 시
한 줄의 `*_OK=1`만 출력하고 누락·변조·schema drift에는 non-zero로 종료한다.

## 1. 단일 제품 ZIP과 source ZIP 검증

```bash
python3 VERIFY_BUNDLE.py Butler_FirstScreen_v2_3_Product.zip
python3 VERIFY_SOURCE.py \
  --extract-to verified-source \
  --manifest artifacts/SOURCE_ARCHIVE_MANIFEST.json \
  --archive artifacts/Butler_Source.zip
```

두 단계가 모두 PASS하기 전에는 내부 코드·보고서·SBOM을 신뢰하지 않는다.

## 2. `.git` 없는 source 제품 검증

```bash
cd verified-source/source
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-firstscreen-ci.lock
.venv/bin/python scripts/verify/verify_storage_risk_acceptance.py
.venv/bin/python scripts/release/generate_cyclonedx_sbom.py \
  --commit HEAD --build-info BUILD_INFO.json \
  --source-manifest ../SOURCE_ARCHIVE_MANIFEST.json \
  --output ../butler.cdx.json \
  --npm-lock butler-desktop/package-lock.json \
  --python-requirements requirements-firstscreen-ci.lock
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest -q --junitxml=../pytest-repository.xml
bash scripts/verify/verify_repo_contracts.sh
```

미서명 위험 결정, 저장소 실패 또는 contract 실패가 하나라도 있으면 `CODE_PASS=NO`이다.

## 3. 실제 웹 제품

```bash
cd butler-desktop
npm ci
npm run test:run
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

## 4. macOS 제품 게이트

macOS 15 arm64 clean runner에서 Rust 1.97.1로 `cargo check --locked`와 signed app package/install을
실행한다. 이어 설치→대화→종료→재시작→복호화·Keychain continuity, VoiceOver, M3 Metal·memory·
thermal·power raw evidence를 별도 프로세스에서 검증한다. 이 실측 전에는 release-ready가 아니다.
