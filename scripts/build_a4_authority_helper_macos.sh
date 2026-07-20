#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-}"
APP="${2:-}"
HELPER_APP="$APP/Contents/Helpers/A4VerifierAuthority.app"
HELPER_EXE="$HELPER_APP/Contents/MacOS/A4VerifierAuthority"
AUTHORITY_PYTHON="$APP/Contents/Resources/python/bin/python3"

fail() { echo "A4_AUTHORITY_HELPER_BUILD_OK=0 ERROR_CODE=$1"; exit 1; }
[[ "$(uname -s)" == "Darwin" ]] || fail BLOCK_MACOS_REQUIRED
[[ "$MODE" == "--install-helper" || "$MODE" == "--finalize-app" ]] || fail BLOCK_ARGUMENT
[[ -d "$APP/Contents" ]] || fail BLOCK_APP_BUNDLE_MISSING

AUTH_IDENTITY="${BUTLER_A4_AUTHORITY_CODESIGN_IDENTITY:-}"
APP_IDENTITY="${BUTLER_APP_CODESIGN_IDENTITY:-}"
ACCESS_GROUP="${BUTLER_A4_KEYCHAIN_ACCESS_GROUP:-}"
PROFILE="${BUTLER_A4_AUTHORITY_PROVISIONING_PROFILE:-}"
[[ -n "$AUTH_IDENTITY" && -n "$APP_IDENTITY" && "$AUTH_IDENTITY" != "$APP_IDENTITY" ]] || fail BLOCK_SIGNING_IDENTITY
[[ "$ACCESS_GROUP" =~ ^([A-Z0-9]{10}\.[A-Za-z0-9.-]+|group\.[A-Za-z0-9.-]+)$ ]] || fail BLOCK_KEYCHAIN_ACCESS_GROUP
[[ -f "$PROFILE" && ! -L "$PROFILE" ]] || fail BLOCK_PROVISIONING_PROFILE

TMP="$(mktemp -d "${TMPDIR:-/tmp}/butler-a4-helper.XXXXXX")"
INSTALL_COMMITTED=0
cleanup() {
  rm -rf "$TMP"
  if [[ "$MODE" == "--install-helper" && "$INSTALL_COMMITTED" != "1" ]]; then
    rm -rf "$HELPER_APP"
  fi
}
trap cleanup EXIT

if [[ "$MODE" == "--install-helper" ]]; then
  SOURCE="$ROOT/butler-desktop/src-tauri/native/a4_verifier_authority_launcher.swift"
  ZERO_SOURCE="$ROOT/butler-desktop/src-tauri/native/a4_secure_zero.c"
  [[ -f "$SOURCE" && ! -L "$SOURCE" && -f "$ZERO_SOURCE" && ! -L "$ZERO_SOURCE" ]] || fail BLOCK_HELPER_SOURCE
  TRUST="$APP/Contents/Resources/butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json"
  [[ -f "$TRUST" && ! -L "$TRUST" ]] || fail BLOCK_AUTHORITY_TRUST
  python3 -c 'import base64,json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); assert d.get("enabled") is True and d.get("environment")=="PRODUCTION" and d.get("algorithm")=="Ed25519" and len(base64.b64decode(d.get("public_key_b64",""),validate=True))==32 and int(d.get("revocation_epoch",-1))>=0' "$TRUST" \
    || fail BLOCK_AUTHORITY_TRUST
  security cms -D -i "$PROFILE" > "$TMP/profile.plist" 2>/dev/null \
    || fail BLOCK_PROVISIONING_PROFILE
  python3 -c 'import plistlib,sys; d=plistlib.load(open(sys.argv[1],"rb")); e=d.get("Entitlements",{}); groups=e.get("keychain-access-groups",[]); assert sys.argv[2] in groups; app_id=e.get("com.apple.application-identifier") or e.get("application-identifier"); assert isinstance(app_id,str) and (app_id.endswith(".com.butler.a4-verifier-authority") or app_id.endswith(".*"))' "$TMP/profile.plist" "$ACCESS_GROUP" \
    || fail BLOCK_PROVISIONING_PROFILE_ENTITLEMENTS
  mkdir -p "$HELPER_APP/Contents/MacOS"
  cat > "$TMP/BuildConfig.swift" <<EOF
let a4KeychainAccessGroup = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$ACCESS_GROUP")
EOF
  cat > "$HELPER_APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>A4VerifierAuthority</string>
  <key>CFBundleIdentifier</key><string>com.butler.a4-verifier-authority</string>
  <key>CFBundleName</key><string>A4VerifierAuthority</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundleVersion</key><string>1</string>
</dict></plist>
EOF
  cp "$PROFILE" "$HELPER_APP/Contents/embedded.provisionprofile"
  xcrun clang -O2 -fno-builtin-memset -c "$ZERO_SOURCE" -o "$TMP/a4_secure_zero.o" \
    || fail BLOCK_HELPER_COMPILE
  xcrun swiftc -O -whole-module-optimization -module-cache-path "$TMP/module-cache" \
    "$SOURCE" "$TMP/BuildConfig.swift" "$TMP/a4_secure_zero.o" \
    -framework Foundation -framework Security -framework CryptoKit \
    -o "$HELPER_EXE" || fail BLOCK_HELPER_COMPILE
  cat > "$TMP/helper.entitlements" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>keychain-access-groups</key><array><string>$ACCESS_GROUP</string></array>
</dict></plist>
EOF
  codesign --force --options runtime --timestamp \
    --identifier com.butler.a4-verifier-authority \
    --entitlements "$TMP/helper.entitlements" \
    --sign "$AUTH_IDENTITY" "$HELPER_APP" || fail BLOCK_HELPER_CODESIGN
  codesign --verify --strict --verbose=2 "$HELPER_APP" >/dev/null 2>&1 || fail BLOCK_HELPER_CODESIGN_VERIFY
  [[ -x "$AUTHORITY_PYTHON" && ! -L "$AUTHORITY_PYTHON" ]] || fail BLOCK_AUTHORITY_PYTHON
  codesign --force --options runtime --timestamp --sign "$AUTH_IDENTITY" "$AUTHORITY_PYTHON" \
    || fail BLOCK_AUTHORITY_PYTHON_CODESIGN
  codesign --verify --strict --verbose=2 "$AUTHORITY_PYTHON" >/dev/null 2>&1 \
    || fail BLOCK_AUTHORITY_PYTHON_CODESIGN_VERIFY
  INSTALL_COMMITTED=1
  echo "A4_AUTHORITY_HELPER_BUILD_OK=1"
  exit 0
fi

[[ -x "$HELPER_EXE" && ! -L "$HELPER_EXE" ]] || fail BLOCK_HELPER_MISSING
cat > "$TMP/app.entitlements" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict></dict></plist>
EOF
codesign --force --options runtime --timestamp \
  --entitlements "$TMP/app.entitlements" --sign "$APP_IDENTITY" "$APP" \
  || fail BLOCK_APP_CODESIGN
codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1 || fail BLOCK_APP_CODESIGN_VERIFY
codesign -d --entitlements :- "$HELPER_APP" > "$TMP/helper.actual.plist" 2>/dev/null || fail BLOCK_HELPER_ENTITLEMENTS
codesign -d --entitlements :- "$APP" > "$TMP/app.actual.plist" 2>/dev/null || fail BLOCK_APP_ENTITLEMENTS
codesign -d --entitlements :- "$AUTHORITY_PYTHON" > "$TMP/python.actual.plist" 2>/dev/null || fail BLOCK_AUTHORITY_PYTHON_ENTITLEMENTS
[[ "$(/usr/libexec/PlistBuddy -c 'Print :keychain-access-groups:0' "$TMP/helper.actual.plist" 2>/dev/null)" == "$ACCESS_GROUP" ]] \
  || fail BLOCK_HELPER_ACCESS_GROUP_MISMATCH
if /usr/libexec/PlistBuddy -c 'Print :keychain-access-groups' "$TMP/app.actual.plist" >/dev/null 2>&1; then
  fail BLOCK_PRODUCT_HAS_AUTHORITY_ACCESS_GROUP
fi
if /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "$TMP/helper.actual.plist" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "$TMP/app.actual.plist" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "$TMP/python.actual.plist" >/dev/null 2>&1; then
  fail BLOCK_DEBUG_ENTITLEMENT
fi
[[ "$(codesign -d --verbose=4 "$HELPER_APP" 2>&1 | sed -n 's/^Identifier=//p')" == "com.butler.a4-verifier-authority" ]] \
  || fail BLOCK_HELPER_IDENTIFIER
[[ "$(codesign -d --verbose=4 "$APP" 2>&1 | sed -n 's/^Identifier=//p')" != "com.butler.a4-verifier-authority" ]] \
  || fail BLOCK_IDENTITY_COLLISION
HELPER_AUTHORITY="$(codesign -d --verbose=4 "$HELPER_APP" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
APP_AUTHORITY="$(codesign -d --verbose=4 "$APP" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
PYTHON_AUTHORITY="$(codesign -d --verbose=4 "$AUTHORITY_PYTHON" 2>&1 | sed -n 's/^Authority=//p' | head -1)"
[[ -n "$HELPER_AUTHORITY" && -n "$APP_AUTHORITY" && "$HELPER_AUTHORITY" != "$APP_AUTHORITY" \
  && "$PYTHON_AUTHORITY" == "$HELPER_AUTHORITY" ]] \
  || fail BLOCK_SIGNING_IDENTITY_COLLISION
codesign -d --verbose=4 "$HELPER_APP" 2>&1 | grep -Eq '^CodeDirectory .*flags=.*runtime' \
  || fail BLOCK_HELPER_HARDENED_RUNTIME
codesign -d --verbose=4 "$APP" 2>&1 | grep -Eq '^CodeDirectory .*flags=.*runtime' \
  || fail BLOCK_APP_HARDENED_RUNTIME
codesign -d --verbose=4 "$AUTHORITY_PYTHON" 2>&1 | grep -Eq '^CodeDirectory .*flags=.*runtime' \
  || fail BLOCK_AUTHORITY_PYTHON_HARDENED_RUNTIME
echo "A4_AUTHORITY_APP_FINALIZE_OK=1"
