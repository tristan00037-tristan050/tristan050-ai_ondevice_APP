# FirstScreen v2.2 재현 절차

지원 도구 정본은 Python 3.12, Node.js 24, npm lockfile, Rust 1.97.1이다. 아래 명령은 archive 최상위에서 실행한다.

## 1. `.git` 없는 source 검증

```bash
python3 source/scripts/release/verify_source_bundle.py \
  --source-root source \
  --manifest SOURCE_ARCHIVE_MANIFEST.json \
  --archive Butler_Source.zip
```

성공 출력은 정확히 `SOURCE_BUNDLE_VERIFY_OK=1`이다. 실패 시 후속 빌드와 테스트를 중단한다.

## 2. hash-locked Python 환경과 제품 테스트

```bash
cd source
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-firstscreen-ci.lock
.venv/bin/python scripts/verify/verify_storage_risk_acceptance.py
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest -q --junitxml=pytest-repository.xml
```

repo-wide 테스트 하나라도 실패하면 `CODE_PASS=NO`이다.

## 3. 데스크톱 제품 빌드와 브라우저 E2E

```bash
cd butler-desktop
npm ci
npm run test:run
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Playwright는 실제 `butler_sidecar.py`와 Vite 제품 UI를 기동하고 axe WCAG 2.2 AA 및 keyboard 흐름을 검사한다.

## 4. macOS 제품 게이트

macOS 15 arm64 clean runner에서 다음을 수행하고 raw-safe evidence를 보존한다.

```bash
rustup toolchain install 1.97.1 --profile minimal
cd butler-desktop
npm ci
npm run build
cargo check --locked --manifest-path src-tauri/Cargo.toml
```

이 compile gate와 별도로 서명된 `.app`의 설치, 최초 대화, 종료·재시작, Keychain 복호화 연속성, VoiceOver를 실기기에서 검증해야 한다. M3·Metal·memory·thermal·power 측정과 운영 활성화 승인은 별도 게이트다.
