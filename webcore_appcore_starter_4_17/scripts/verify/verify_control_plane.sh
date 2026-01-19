#!/bin/bash
# verify_control_plane.sh
# Output-based DoD verification for Control Plane
# Emits *_OK keys only on success (exit 0)

set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel)"
cd "${TOPLEVEL}/webcore_appcore_starter_4_17/backend/control_plane"

# Initialize OK flags
TENANT_ISOLATION_OK=0
AUDIT_DENY_COVERAGE_OK=0
AUDIT_ALLOW_COVERAGE_OK=0
AUDIT_APPEND_ONLY_OK=0
RBAC_DEFAULT_DENY_OK=0

# Function to extract OK keys from test output
extract_ok_keys() {
  local test_output="$1"
  # Extract OK keys from test output
  echo "${test_output}" | grep -E "^(TENANT_ISOLATION_OK|AUDIT_DENY_COVERAGE_OK|AUDIT_ALLOW_COVERAGE_OK|AUDIT_APPEND_ONLY_OK|RBAC_DEFAULT_DENY_OK)=[01]$" || true
}

# Run tenant isolation tests
echo "Running tenant isolation tests..."
if tenant_output=$(node -e "
  const {getCallerContext, isSuperAdmin} = require('./services/auth_context.ts');
  const req = {callerContext: {tenant_id: 't1', user_id: 'u1', roles: [], permissions: []}};
  const ctx = getCallerContext(req);
  if (ctx && ctx.tenant_id === 't1' && !isSuperAdmin(ctx)) {
    console.log('TENANT_ISOLATION_OK=1');
  } else {
    console.log('TENANT_ISOLATION_OK=0');
  }
" 2>&1); then
  if echo "${tenant_output}" | grep -q "TENANT_ISOLATION_OK=1"; then
    TENANT_ISOLATION_OK=1
  fi
else
  echo "WARN: Tenant isolation test failed"
fi

# Run audit coverage tests
echo "Running audit coverage tests..."
if audit_output=$(node -e "
  const {clearAuditLogs, queryAuditLogs} = require('./audit/service.ts');
  const {auditDeny, auditAllow} = require('./audit/hooks.ts');
  const {getCallerContext} = require('./services/auth_context.ts');
  
  clearAuditLogs();
  const context = {tenant_id: 't1', user_id: 'u1', roles: [], permissions: []};
  const req = {method: 'POST', path: '/api/v1/iam/users', ip: '127.0.0.1', headers: {}};
  
  // Test DENY
  auditDeny(req, context, 'user:write', 'user', 'new', 'Permission denied');
  const denyLogs = queryAuditLogs('t1', {action: 'permission_denied'});
  if (denyLogs.length > 0 && !denyLogs[0].success) {
    console.log('AUDIT_DENY_COVERAGE_OK=1');
  } else {
    console.log('AUDIT_DENY_COVERAGE_OK=0');
  }
  
  // Test ALLOW
  auditAllow(req, context, 'create', 'user', 'user-123');
  const allowLogs = queryAuditLogs('t1', {action: 'create'});
  if (allowLogs.length > 0 && allowLogs[0].success) {
    console.log('AUDIT_ALLOW_COVERAGE_OK=1');
  } else {
    console.log('AUDIT_ALLOW_COVERAGE_OK=0');
  }
  
  // Test append-only
  const log = allowLogs[0];
  const originalId = log.id;
  log.id = 'modified';
  const log2 = queryAuditLogs('t1', {action: 'create'})[0];
  if (log2 && log2.id === originalId) {
    console.log('AUDIT_APPEND_ONLY_OK=1');
  } else {
    console.log('AUDIT_APPEND_ONLY_OK=0');
  }
" 2>&1); then
  if echo "${audit_output}" | grep -q "AUDIT_DENY_COVERAGE_OK=1"; then
    AUDIT_DENY_COVERAGE_OK=1
  fi
  if echo "${audit_output}" | grep -q "AUDIT_ALLOW_COVERAGE_OK=1"; then
    AUDIT_ALLOW_COVERAGE_OK=1
  fi
  if echo "${audit_output}" | grep -q "AUDIT_APPEND_ONLY_OK=1"; then
    AUDIT_APPEND_ONLY_OK=1
  fi
else
  echo "WARN: Audit coverage test failed"
fi

# Run RBAC default deny tests
echo "Running RBAC default deny tests..."
if rbac_output=$(node -e "
  const {hasPermissionFromContext} = require('./auth/rbac.ts');
  const context = {tenant_id: 't1', user_id: 'u1', roles: [], permissions: []};
  const hasAccess = hasPermissionFromContext(context, 'user:read');
  if (!hasAccess) {
    console.log('RBAC_DEFAULT_DENY_OK=1');
  } else {
    console.log('RBAC_DEFAULT_DENY_OK=0');
  }
" 2>&1); then
  if echo "${rbac_output}" | grep -q "RBAC_DEFAULT_DENY_OK=1"; then
    RBAC_DEFAULT_DENY_OK=1
  fi
else
  echo "WARN: RBAC default deny test failed"
fi

# Emit OK keys only if all tests passed
if [ "${TENANT_ISOLATION_OK}" -eq 1 ] && \
   [ "${AUDIT_DENY_COVERAGE_OK}" -eq 1 ] && \
   [ "${AUDIT_ALLOW_COVERAGE_OK}" -eq 1 ] && \
   [ "${AUDIT_APPEND_ONLY_OK}" -eq 1 ] && \
   [ "${RBAC_DEFAULT_DENY_OK}" -eq 1 ]; then
  echo "TENANT_ISOLATION_OK=1"
  echo "AUDIT_DENY_COVERAGE_OK=1"
  echo "AUDIT_ALLOW_COVERAGE_OK=1"
  echo "AUDIT_APPEND_ONLY_OK=1"
  echo "RBAC_DEFAULT_DENY_OK=1"
  exit 0
else
  echo "FAIL: One or more verification checks failed"
  echo "TENANT_ISOLATION_OK=${TENANT_ISOLATION_OK}"
  echo "AUDIT_DENY_COVERAGE_OK=${AUDIT_DENY_COVERAGE_OK}"
  echo "AUDIT_ALLOW_COVERAGE_OK=${AUDIT_ALLOW_COVERAGE_OK}"
  echo "AUDIT_APPEND_ONLY_OK=${AUDIT_APPEND_ONLY_OK}"
  echo "RBAC_DEFAULT_DENY_OK=${RBAC_DEFAULT_DENY_OK}"
  exit 1
fi

