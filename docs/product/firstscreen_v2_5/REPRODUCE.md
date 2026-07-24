# FirstScreen v2.5 재현

지원 기준은 Python 3.12, Node.js 24, npm 11, Rust 1.97.1이다. production build는 clean Git
commit과 `BUILD_CONTEXT.json`을 요구하며 개발 fallback을 허용하지 않는다.

## 단일 결과 파일의 독립 무결성 검증

```bash
python3 VERIFY_BUNDLE.py Butler_FirstScreen_v2_5_Product.zip
```

정상 출력은 다음 한 줄이다.

```text
PRODUCT_BUNDLE_INTEGRITY_OK=1 CODE_PASS=0 RELEASE_READY=0
```

이 값은 ZIP·source·web·SBOM·context 결속 통과이며 제품 출시 통과가 아니다.

## 검증된 source 추출

```bash
python3 VERIFY_SOURCE.py \
  --archive artifacts/Butler_Source.zip \
  --manifest artifacts/SOURCE_ARCHIVE_MANIFEST.json \
  --extract-to verified-source
```

## 변경 범위와 전체 저장소

```bash
python3.12 -m pip install --require-hashes -r requirements-firstscreen-ci.lock
python3.12 -m pytest -q tests/firstscreen_v2_5 tests/test_storage_risk_acceptance.py \
  --cov=butler_pc_core.firstscreen_trust --cov-branch --cov-fail-under=85
python3.12 -m pytest -q --junitxml=repository-junit.xml
bash scripts/verify/verify_repo_contracts.sh
```

## production Web

```bash
python3 scripts/release/build_safe_source_archive.py --commit HEAD --scope-baseline HEAD^ \
  --output /tmp/source.zip --manifest /tmp/SOURCE_ARCHIVE_MANIFEST.json
python3 scripts/release/build_with_git.py --output /tmp/BUILD_CONTEXT.json \
  --source-manifest /tmp/SOURCE_ARCHIVE_MANIFEST.json \
  --repository atlink/butler \
  --workflow-identity atlink/butler/.github/workflows/firstscreen-v2-5.yml@refs/heads/main \
  --toolchain-identity 'python=3.12;node=24;rust=1.97.1' --baseline HEAD^
cd butler-desktop
npm ci
npm audit --audit-level=high
npm run test:run
BUTLER_BUILD_CONTEXT_PATH=/tmp/BUILD_CONTEXT.json npm run build
```

Rust, signed app, Keychain, browser, VoiceOver, Windows와 M3 단계는 해당 플랫폼·키·실기기에서
같은 commit/tree/context digest를 사용해 실행해야 한다. 미실행은 계속 NOT_RUN이다.
