#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-}"
APP="${2:-}"
HELPER_ID="com.butler.box5.user-authority.v2"
BOX5_DIR="$APP/Contents/Resources/box5"
HELPER="$BOX5_DIR/Box5UserAuthority"
POLICY="$BOX5_DIR/authorization-trust-policy-v2.json"

fail() { echo "BOX5_AUTHORITY_HELPER_OK=0 ERROR_CODE=$1"; exit 1; }
sha256_file() { shasum -a 256 "$1" | awk '{print $1}'; }

[[ "$(uname -s)" == "Darwin" ]] || fail BLOCK_MACOS_REQUIRED
[[ "$MODE" == "--install-helper" || "$MODE" == "--finalize-app" ]] || fail BLOCK_ARGUMENT
[[ -d "$APP/Contents/Resources" && ! -L "$APP" ]] || fail BLOCK_APP_BUNDLE_MISSING

AUTH_IDENTITY="${BUTLER_BOX5_AUTHORITY_CODESIGN_IDENTITY:-}"
APP_IDENTITY="${BUTLER_APP_CODESIGN_IDENTITY:-}"
ACCESS_GROUP="${BUTLER_BOX5_KEYCHAIN_ACCESS_GROUP:-}"
PROFILE="${BUTLER_BOX5_AUTHORITY_PROVISIONING_PROFILE:-}"
CALLER_REQUIREMENT="${BUTLER_BOX5_CALLER_DESIGNATED_REQUIREMENT:-}"
POLICY_SOURCE="${BUTLER_BOX5_APPROVED_TRUST_POLICY:-}"
POLICY_DIGEST="${BUTLER_BOX5_APPROVED_TRUST_POLICY_SHA256:-}"
KEYCHAIN_SERVICE="${BUTLER_BOX5_KEYCHAIN_SERVICE:-com.butler.box5.user-authority.v2}"
KEY_ACCOUNT="${BUTLER_BOX5_SIGNING_KEY_ACCOUNT:-ed25519.production.v2}"
ENROLLMENT_ACCOUNT="${BUTLER_BOX5_ENROLLMENT_ACCOUNT:-enrollment.production.v2}"

[[ -n "$AUTH_IDENTITY" && -n "$APP_IDENTITY" && "$AUTH_IDENTITY" != "$APP_IDENTITY" ]] \
  || fail BLOCK_SIGNING_IDENTITY
[[ "$ACCESS_GROUP" =~ ^([A-Z0-9]{10}\.[A-Za-z0-9.-]+|group\.[A-Za-z0-9.-]+)$ ]] \
  || fail BLOCK_KEYCHAIN_ACCESS_GROUP
[[ -f "$PROFILE" && ! -L "$PROFILE" ]] || fail BLOCK_PROVISIONING_PROFILE
[[ -n "$CALLER_REQUIREMENT" && ${#CALLER_REQUIREMENT} -le 2048 && "$CALLER_REQUIREMENT" != *$'\n'* ]] \
  || fail BLOCK_CODE_REQUIREMENT
[[ "$KEYCHAIN_SERVICE" =~ ^[A-Za-z0-9.-]{1,160}$ ]] || fail BLOCK_KEYCHAIN_SERVICE
[[ "$KEY_ACCOUNT" =~ ^[A-Za-z0-9._-]{1,80}$ ]] || fail BLOCK_KEY_ACCOUNT
[[ "$ENROLLMENT_ACCOUNT" =~ ^[A-Za-z0-9._-]{1,80}$ ]] || fail BLOCK_ENROLLMENT_ACCOUNT
[[ "$POLICY_DIGEST" =~ ^[0-9a-f]{64}$ ]] || fail BLOCK_APPROVED_POLICY_DIGEST

TMP="$(mktemp -d "${TMPDIR:-/tmp}/butler-box5-authority.XXXXXX")"
INSTALL_COMMITTED=0
cleanup() {
  rm -rf "$TMP"
  if [[ "$MODE" == "--install-helper" && "$INSTALL_COMMITTED" != "1" ]]; then
    rm -rf "$BOX5_DIR"
  fi
}
trap cleanup EXIT

if [[ "$MODE" == "--install-helper" ]]; then
  [[ -f "$POLICY_SOURCE" && ! -L "$POLICY_SOURCE" ]] || fail BLOCK_APPROVED_POLICY_UNAVAILABLE
  [[ "$(sha256_file "$POLICY_SOURCE")" == "$POLICY_DIGEST" ]] || fail BLOCK_APPROVED_POLICY_DIGEST
  python3 - "$POLICY_SOURCE" <<'PY'
import base64, hashlib, json, re, sys, time
raw = open(sys.argv[1], 'rb').read()
assert 0 < len(raw) <= 32768
doc = json.loads(raw)
assert raw.rstrip(b'\n') == json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
assert set(doc) == {'schema_version','policy_id','issuer','audience','not_before','expires_at','keys'}
assert doc['schema_version'] == '2.0' and doc['audience'] == 'butler-box5-accounting'
assert re.fullmatch(r'[A-Za-z0-9._-]{1,80}', doc['policy_id'])
assert type(doc['not_before']) is int and type(doc['expires_at']) is int
assert doc['not_before'] <= int(time.time()) < doc['expires_at']
active = []
for key in doc['keys']:
    assert set(key) == {'key_id','alg','public_key_b64url','status'}
    assert key['alg'] == 'EdDSA' and key['status'] in {'ACTIVE','RETIRED_VERIFY_ONLY'}
    assert re.fullmatch(r'[A-Za-z0-9._-]{1,80}', key['key_id'])
    text = key['public_key_b64url']
    raw_key = base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    assert len(raw_key) == 32 and base64.urlsafe_b64encode(raw_key).decode().rstrip('=') == text
    if key['status'] == 'ACTIVE': active.append(key)
assert len(active) == 1
PY
  security cms -D -i "$PROFILE" > "$TMP/profile.plist" 2>/dev/null \
    || fail BLOCK_PROVISIONING_PROFILE
  python3 -c 'import plistlib,sys; d=plistlib.load(open(sys.argv[1],"rb")); e=d.get("Entitlements",{}); assert sys.argv[2] in e.get("keychain-access-groups",[]); a=e.get("com.apple.application-identifier") or e.get("application-identifier"); assert isinstance(a,str) and (a.endswith(".com.butler.box5.user-authority.v2") or a.endswith(".*"))' "$TMP/profile.plist" "$ACCESS_GROUP" \
    || fail BLOCK_PROVISIONING_PROFILE_ENTITLEMENTS

  NATIVE="$ROOT/butler-desktop/src-tauri/native"
  SOURCES=(
    "$NATIVE/box5_user_authority_protocol.swift"
    "$NATIVE/box5_user_authority_launcher.swift"
  )
  for source in "${SOURCES[@]}"; do
    [[ -f "$source" && ! -L "$source" ]] || fail BLOCK_HELPER_SOURCE
  done
  python3 - "$TMP/Box5BuildConfig.swift" "$POLICY_DIGEST" "$ACCESS_GROUP" \
    "$CALLER_REQUIREMENT" "$KEYCHAIN_SERVICE" "$KEY_ACCOUNT" "$ENROLLMENT_ACCOUNT" <<'PY'
import json, sys
names = [
    'box5ApprovedPolicySHA256', 'box5KeychainAccessGroup',
    'box5ExpectedCallerRequirement', 'box5KeychainService',
    'box5SigningKeyAccount', 'box5EnrollmentAccount',
]
with open(sys.argv[1], 'w', encoding='utf-8', newline='\n') as out:
    for name, value in zip(names, sys.argv[2:]):
        out.write(f'let {name} = {json.dumps(value)}\n')
PY
  mkdir -p "$BOX5_DIR"
  xcrun swiftc -O -whole-module-optimization \
    -module-cache-path "$TMP/module-cache" \
    "${SOURCES[@]}" "$TMP/Box5BuildConfig.swift" \
    -framework Foundation -framework Security -framework CryptoKit \
    -framework LocalAuthentication -o "$TMP/Box5UserAuthority" \
    || fail BLOCK_HELPER_COMPILE
  cat > "$TMP/helper.entitlements" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>keychain-access-groups</key><array><string>$ACCESS_GROUP</string></array>
</dict></plist>
EOF
  codesign --force --options runtime --timestamp --identifier "$HELPER_ID" \
    --entitlements "$TMP/helper.entitlements" --sign "$AUTH_IDENTITY" \
    "$TMP/Box5UserAuthority" || fail BLOCK_HELPER_CODESIGN
  codesign --verify --strict --verbose=2 "$TMP/Box5UserAuthority" >/dev/null 2>&1 \
    || fail BLOCK_HELPER_CODESIGN_VERIFY
  install -m 0755 "$TMP/Box5UserAuthority" "$HELPER"
  install -m 0444 "$POLICY_SOURCE" "$POLICY"
  [[ "$(sha256_file "$POLICY")" == "$POLICY_DIGEST" ]] || fail BLOCK_APPROVED_POLICY_DIGEST
  INSTALL_COMMITTED=1
  echo "BOX5_AUTHORITY_HELPER_OK=1 HELPER_SHA256=$(sha256_file "$HELPER") POLICY_SHA256=$POLICY_DIGEST"
  exit 0
fi

[[ -x "$HELPER" && ! -L "$HELPER" && -f "$POLICY" && ! -L "$POLICY" ]] \
  || fail BLOCK_HELPER_MISSING
[[ "$(sha256_file "$POLICY")" == "$POLICY_DIGEST" ]] || fail BLOCK_APPROVED_POLICY_DIGEST
codesign --verify --strict --verbose=2 "$HELPER" >/dev/null 2>&1 \
  || fail BLOCK_HELPER_CODESIGN_VERIFY
[[ "$(codesign -d --verbose=4 "$HELPER" 2>&1 | sed -n 's/^Identifier=//p')" == "$HELPER_ID" ]] \
  || fail BLOCK_HELPER_IDENTIFIER
codesign -d --entitlements :- "$HELPER" > "$TMP/helper.actual.plist" 2>/dev/null \
  || fail BLOCK_HELPER_ENTITLEMENTS
[[ "$(/usr/libexec/PlistBuddy -c 'Print :keychain-access-groups:0' "$TMP/helper.actual.plist" 2>/dev/null)" == "$ACCESS_GROUP" ]] \
  || fail BLOCK_HELPER_ACCESS_GROUP_MISMATCH
if /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "$TMP/helper.actual.plist" >/dev/null 2>&1; then
  fail BLOCK_DEBUG_ENTITLEMENT
fi
codesign -d --verbose=4 "$HELPER" 2>&1 | grep -Eq '^CodeDirectory .*flags=.*runtime' \
  || fail BLOCK_HARDENED_RUNTIME

cat > "$TMP/app.entitlements" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict></dict></plist>
EOF
codesign --force --options runtime --timestamp --entitlements "$TMP/app.entitlements" \
  --sign "$APP_IDENTITY" "$APP" || fail BLOCK_APP_CODESIGN
codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1 \
  || fail BLOCK_APP_CODESIGN_VERIFY
codesign -d --entitlements :- "$APP" > "$TMP/app.actual.plist" 2>/dev/null \
  || fail BLOCK_APP_ENTITLEMENTS
if /usr/libexec/PlistBuddy -c 'Print :keychain-access-groups' "$TMP/app.actual.plist" >/dev/null 2>&1; then
  fail BLOCK_PRODUCT_HAS_AUTHORITY_ACCESS_GROUP
fi
echo "BOX5_AUTHORITY_HELPER_OK=1 HELPER_SHA256=$(sha256_file "$HELPER") POLICY_SHA256=$POLICY_DIGEST"
