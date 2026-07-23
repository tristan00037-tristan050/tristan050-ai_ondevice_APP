#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-}"
APP="${2:-}"
SERVICE_NAME="com.butler.a4-verifier-authority"
XPC_BUNDLE="$APP/Contents/XPCServices/A4VerifierAuthority.xpc"
XPC_EXE="$XPC_BUNDLE/Contents/MacOS/A4VerifierAuthority"
BRIDGE="$APP/Contents/Resources/butler_pc_core/a4_verifier/libButlerA4AuthorityBridge.dylib"
APP_PYTHON="$APP/Contents/Resources/python/bin/python3"

fail() { echo "A4_AUTHORITY_XPC_BUILD_OK=0 ERROR_CODE=$1"; exit 1; }
cdhash_digest() {
  local target="$1" cdhash
  cdhash="$(codesign -d --verbose=4 "$target" 2>&1 | sed -n 's/^CDHash=//p' | head -1)"
  [[ "$cdhash" =~ ^[0-9a-fA-F]{40,64}$ ]] || return 1
  python3 -c 'import hashlib,sys; print(hashlib.sha256(bytes.fromhex(sys.argv[1])).hexdigest())' "$cdhash"
}
[[ "$(uname -s)" == "Darwin" ]] || fail BLOCK_MACOS_REQUIRED
[[ "$MODE" == "--install-helper" || "$MODE" == "--finalize-app" ]] || fail BLOCK_ARGUMENT
[[ -d "$APP/Contents" ]] || fail BLOCK_APP_BUNDLE_MISSING

AUTH_IDENTITY="${BUTLER_A4_AUTHORITY_CODESIGN_IDENTITY:-}"
APP_IDENTITY="${BUTLER_APP_CODESIGN_IDENTITY:-}"
ACCESS_GROUP="${BUTLER_A4_KEYCHAIN_ACCESS_GROUP:-}"
PROFILE="${BUTLER_A4_AUTHORITY_PROVISIONING_PROFILE:-}"
CALLER_REQUIREMENT="${BUTLER_A4_CALLER_DESIGNATED_REQUIREMENT:-}"
AUTHORITY_REQUIREMENT="${BUTLER_A4_AUTHORITY_DESIGNATED_REQUIREMENT:-}"
VERIFIER_REQUIREMENT="${BUTLER_A4_VERIFIER_DESIGNATED_REQUIREMENT:-}"
[[ -n "$AUTH_IDENTITY" && -n "$APP_IDENTITY" && "$AUTH_IDENTITY" != "$APP_IDENTITY" ]] || fail BLOCK_SIGNING_IDENTITY
[[ "$ACCESS_GROUP" =~ ^([A-Z0-9]{10}\.[A-Za-z0-9.-]+|group\.[A-Za-z0-9.-]+)$ ]] || fail BLOCK_KEYCHAIN_ACCESS_GROUP
[[ -f "$PROFILE" && ! -L "$PROFILE" ]] || fail BLOCK_PROVISIONING_PROFILE
for requirement in "$CALLER_REQUIREMENT" "$AUTHORITY_REQUIREMENT" "$VERIFIER_REQUIREMENT"; do
  [[ -n "$requirement" && ${#requirement} -le 2048 && "$requirement" != *$'\n'* ]] || fail BLOCK_CODE_REQUIREMENT
done

TMP="$(mktemp -d "${TMPDIR:-/tmp}/butler-a4-xpc.XXXXXX")"
INSTALL_COMMITTED=0
cleanup() {
  rm -rf "$TMP"
  if [[ "$MODE" == "--install-helper" && "$INSTALL_COMMITTED" != "1" ]]; then
    rm -rf "$XPC_BUNDLE" "$BRIDGE"
  fi
}
trap cleanup EXIT

if [[ "$MODE" == "--install-helper" ]]; then
  NATIVE="$ROOT/butler-desktop/src-tauri/native"
  SOURCES=(
    "$NATIVE/a4_verifier_authority_launcher.swift"
    "$NATIVE/a4_secure_memory.swift"
    "$NATIVE/a4_authority_protocol.swift"
    "$NATIVE/a4_authority_canonical.swift"
    "$NATIVE/a4_authority_replay.swift"
  )
  BRIDGE_SOURCES=(
    "$NATIVE/a4_authority_bridge.swift"
    "$NATIVE/a4_authority_protocol.swift"
  )
  ZERO_SOURCE="$NATIVE/a4_secure_zero.c"
  for source in "${SOURCES[@]}" "${BRIDGE_SOURCES[@]}" "$ZERO_SOURCE"; do
    [[ -f "$source" && ! -L "$source" ]] || fail BLOCK_HELPER_SOURCE
  done
  TRUST="$APP/Contents/Resources/butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json"
  [[ -f "$TRUST" && ! -L "$TRUST" ]] || fail BLOCK_AUTHORITY_TRUST
  python3 -c 'import base64,json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); assert d.get("schema_version")=="butler.box5.a4.verifier_authority_trust.v5.3" and d.get("enabled") is True and d.get("environment")=="PRODUCTION" and d.get("transport")=="native-xpc-v5.3" and d.get("algorithm")=="Ed25519" and len(base64.b64decode(d.get("public_key_b64",""),validate=True))==32 and int(d.get("key_epoch",-1))>=int(d.get("minimum_key_epoch",0))>=0 and d.get("signer_key_id") not in d.get("revoked_key_ids",[])' "$TRUST" \
    || fail BLOCK_AUTHORITY_TRUST
  security cms -D -i "$PROFILE" > "$TMP/profile.plist" 2>/dev/null \
    || fail BLOCK_PROVISIONING_PROFILE
  python3 -c 'import plistlib,sys; d=plistlib.load(open(sys.argv[1],"rb")); e=d.get("Entitlements",{}); groups=e.get("keychain-access-groups",[]); assert sys.argv[2] in groups; app_id=e.get("com.apple.application-identifier") or e.get("application-identifier"); assert isinstance(app_id,str) and (app_id.endswith(".com.butler.a4-verifier-authority") or app_id.endswith(".*"))' "$TMP/profile.plist" "$ACCESS_GROUP" \
    || fail BLOCK_PROVISIONING_PROFILE_ENTITLEMENTS

  mkdir -p "$XPC_BUNDLE/Contents/MacOS" "$(dirname "$BRIDGE")"
  cat > "$TMP/AuthorityBuildConfig.swift" <<EOF
let a4KeychainAccessGroup = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$ACCESS_GROUP")
let a4ExpectedCallerRequirement = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$CALLER_REQUIREMENT")
let a4ExpectedAuthorityRequirement = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$AUTHORITY_REQUIREMENT")
let a4VerifierRequirement = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$VERIFIER_REQUIREMENT")
let a4XPCServiceName = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$SERVICE_NAME")
EOF
  cat > "$TMP/BridgeBuildConfig.swift" <<EOF
let a4ExpectedAuthorityRequirement = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$AUTHORITY_REQUIREMENT")
let a4XPCServiceName = $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$SERVICE_NAME")
EOF
  cat > "$XPC_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>A4VerifierAuthority</string>
  <key>CFBundleIdentifier</key><string>$SERVICE_NAME</string>
  <key>CFBundleName</key><string>A4VerifierAuthority</string>
  <key>CFBundlePackageType</key><string>XPC!</string>
  <key>CFBundleShortVersionString</key><string>5.3.0</string>
  <key>CFBundleVersion</key><string>53</string>
  <key>XPCService</key><dict>
    <key>ServiceType</key><string>Application</string>
    <key>RunLoopType</key><string>dispatch_main</string>
    <key>MachServices</key><dict><key>$SERVICE_NAME</key><true/></dict>
  </dict>
</dict></plist>
EOF
  cp "$PROFILE" "$XPC_BUNDLE/Contents/embedded.provisionprofile"
  xcrun clang -O2 -fno-builtin-memset -c "$ZERO_SOURCE" -o "$TMP/a4_secure_zero.o" \
    || fail BLOCK_HELPER_COMPILE
  xcrun swiftc -O -whole-module-optimization -module-cache-path "$TMP/service-module-cache" \
    "${SOURCES[@]}" "$TMP/AuthorityBuildConfig.swift" "$TMP/a4_secure_zero.o" \
    -framework Foundation -framework Security -framework CryptoKit \
    -lsqlite3 -o "$XPC_EXE" || fail BLOCK_HELPER_COMPILE
  xcrun swiftc -O -whole-module-optimization -emit-library \
    -module-cache-path "$TMP/bridge-module-cache" \
    "${BRIDGE_SOURCES[@]}" "$TMP/BridgeBuildConfig.swift" \
    -framework Foundation -o "$BRIDGE" || fail BLOCK_BRIDGE_COMPILE
  cat > "$TMP/authority.entitlements" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>keychain-access-groups</key><array><string>$ACCESS_GROUP</string></array>
</dict></plist>
EOF
  codesign --force --options runtime --timestamp \
    --identifier "$SERVICE_NAME" --entitlements "$TMP/authority.entitlements" \
    --sign "$AUTH_IDENTITY" "$XPC_BUNDLE" || fail BLOCK_HELPER_CODESIGN
  codesign --force --options runtime --timestamp --sign "$APP_IDENTITY" "$BRIDGE" \
    || fail BLOCK_BRIDGE_CODESIGN
  codesign --verify --strict --verbose=2 "$XPC_BUNDLE" >/dev/null 2>&1 \
    || fail BLOCK_HELPER_CODESIGN_VERIFY
  codesign --verify --strict --verbose=2 "$BRIDGE" >/dev/null 2>&1 \
    || fail BLOCK_BRIDGE_CODESIGN_VERIFY
  [[ -x "$APP_PYTHON" && ! -L "$APP_PYTHON" ]] || fail BLOCK_AUTHORITY_PYTHON
  codesign --force --options runtime --timestamp --sign "$APP_IDENTITY" "$APP_PYTHON" \
    || fail BLOCK_AUTHORITY_PYTHON_CODESIGN
  AUTHORITY_CDHASH="$(cdhash_digest "$XPC_BUNDLE")" || fail BLOCK_HELPER_CDHASH
  VERIFIER_CDHASH="$(cdhash_digest "$APP_PYTHON")" || fail BLOCK_VERIFIER_CDHASH
  python3 -c 'import json,os,sys,tempfile; p=sys.argv[1]; d=json.load(open(p,encoding="utf-8")); d["expected_authority_cdhash"]=sys.argv[2]; d["expected_verifier_cdhash"]=sys.argv[3]; fd,tmp=tempfile.mkstemp(prefix=".a4-trust-",dir=os.path.dirname(p)); os.write(fd,json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()); os.fsync(fd); os.close(fd); os.chmod(tmp,0o600); os.replace(tmp,p)' "$TRUST" "$AUTHORITY_CDHASH" "$VERIFIER_CDHASH" \
    || fail BLOCK_AUTHORITY_TRUST
  INSTALL_COMMITTED=1
  echo "A4_AUTHORITY_XPC_BUILD_OK=1"
  exit 0
fi

[[ -x "$XPC_EXE" && ! -L "$XPC_EXE" && -f "$BRIDGE" && ! -L "$BRIDGE" ]] \
  || fail BLOCK_HELPER_MISSING
cat > "$TMP/app.entitlements" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict></dict></plist>
EOF
codesign --force --options runtime --timestamp \
  --entitlements "$TMP/app.entitlements" --sign "$APP_IDENTITY" "$APP" \
  || fail BLOCK_APP_CODESIGN
codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1 || fail BLOCK_APP_CODESIGN_VERIFY
TRUST="$APP/Contents/Resources/butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json"
AUTHORITY_CDHASH="$(cdhash_digest "$XPC_BUNDLE")" || fail BLOCK_HELPER_CDHASH
VERIFIER_CDHASH="$(cdhash_digest "$APP_PYTHON")" || fail BLOCK_VERIFIER_CDHASH
python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); bad={"0"*64,"f"*64}; assert d.get("expected_authority_cdhash")==sys.argv[2] not in bad and d.get("expected_verifier_cdhash")==sys.argv[3] not in bad and re.fullmatch(r"[0-9a-f]{64}",sys.argv[2]) and re.fullmatch(r"[0-9a-f]{64}",sys.argv[3])' "$TRUST" "$AUTHORITY_CDHASH" "$VERIFIER_CDHASH" \
  || fail BLOCK_AUTHORITY_CDHASH_BINDING
codesign -d --entitlements :- "$XPC_BUNDLE" > "$TMP/authority.actual.plist" 2>/dev/null || fail BLOCK_HELPER_ENTITLEMENTS
codesign -d --entitlements :- "$APP" > "$TMP/app.actual.plist" 2>/dev/null || fail BLOCK_APP_ENTITLEMENTS
codesign -d --entitlements :- "$APP_PYTHON" > "$TMP/python.actual.plist" 2>/dev/null || fail BLOCK_AUTHORITY_PYTHON_ENTITLEMENTS
[[ "$(/usr/libexec/PlistBuddy -c 'Print :keychain-access-groups:0' "$TMP/authority.actual.plist" 2>/dev/null)" == "$ACCESS_GROUP" ]] \
  || fail BLOCK_HELPER_ACCESS_GROUP_MISMATCH
if /usr/libexec/PlistBuddy -c 'Print :keychain-access-groups' "$TMP/app.actual.plist" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c 'Print :keychain-access-groups' "$TMP/python.actual.plist" >/dev/null 2>&1; then
  fail BLOCK_PRODUCT_HAS_AUTHORITY_ACCESS_GROUP
fi
for entitlements in "$TMP/authority.actual.plist" "$TMP/app.actual.plist" "$TMP/python.actual.plist"; do
  if /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "$entitlements" >/dev/null 2>&1; then
    fail BLOCK_DEBUG_ENTITLEMENT
  fi
done
[[ "$(codesign -d --verbose=4 "$XPC_BUNDLE" 2>&1 | sed -n 's/^Identifier=//p')" == "$SERVICE_NAME" ]] \
  || fail BLOCK_HELPER_IDENTIFIER
for target in "$XPC_BUNDLE" "$BRIDGE" "$APP" "$APP_PYTHON"; do
  codesign -d --verbose=4 "$target" 2>&1 | grep -Eq '^CodeDirectory .*flags=.*runtime' \
    || fail BLOCK_HARDENED_RUNTIME
done
if rg -n --glob '!tests/**' --glob '!*.md' \
  'signing-key-fd|serve-authority|BUTLER_A4_VERIFIER_AUTHORITY_SOCKET|Ed25519PrivateKey' \
  "$APP/Contents/Resources/butler_pc_core" >/dev/null; then
  fail BLOCK_PRIVATE_KEY_EXPORT_PATH
fi
echo "A4_AUTHORITY_XPC_FINALIZE_OK=1"
