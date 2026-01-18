# Admin Console MVP

## Overview

Enterprise Admin Console MVP for onboarding via UI. Uses SVR-01 Control Plane API (OpenAPI v1).

## Features

- **Tenant Management**: Create and manage tenants
- **User Management**: Create and manage users
- **Role Management**: Create and manage roles with permissions
- **Onboarding Flow**: Complete enterprise onboarding via UI
- **RBAC Enforcement**: UI reflects denied actions gracefully
- **No Secrets in Storage**: Only standard tokens/session in browser storage

## Architecture

```
App
  ├── RBACProvider (permissions context)
  ├── ErrorBoundary (handles 401/403)
  └── Pages
      ├── OnboardingPage (e2e onboarding)
      ├── TenantsPage
      ├── UsersPage
      └── RolesPage
```

## Components

### RBACGuard
- Shows/hides content based on permissions
- Gracefully handles denied actions
- RBACButton: Disables button if no permission

### ErrorBoundary
- Handles API errors (401/403)
- Redirects to login on 401
- Shows error message on 403

### API Client
- Communicates with SVR-01 Control Plane API
- Uses standard sessionStorage for auth token
- Handles 401/403 errors gracefully

## Usage

```typescript
// Set auth token (standard session storage)
sessionStorage.setItem('auth_token', 'your-jwt-token');

// Use RBAC guard
<RBACGuard permission="tenant:write" fallback={<p>No permission</p>}>
  <button>Create Tenant</button>
</RBACGuard>

// Use RBAC button
<RBACButton permission="user:write" onClick={handleCreate}>
  Create User
</RBACButton>
```

## Testing

Run integration tests:

```bash
npm test
```

Expected output:
```
CONSOLE_ONBOARDING_DONE_OK=1
RBAC_UI_ENFORCE_OK=1
```

## Security

- **No Secrets in Storage**: Only standard JWT tokens in sessionStorage
- **RBAC Enforced**: UI reflects denied actions gracefully
- **401 Handling**: Redirects to login on unauthorized
- **403 Handling**: Shows error message on forbidden

