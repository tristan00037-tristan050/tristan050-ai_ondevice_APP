# A-2 repo probe evidence

## git
/Users/kimsunghoon/Desktop/butler/box3-draft-v1-2
d3b8398fc6b976bb61362dd55e1b5d392ad74e5c

## package manager / test runner
package-lock.json
package.json
--- package.json scripts (발췌) ---
{
  "name": "butler-desktop",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest",
    "test:run": "vitest run",
    "tauri": "tauri"
  },
  "deps": [
    "@tauri-apps/api",
    "@tauri-apps/plugin-dialog",
    "@tauri-apps/plugin-fs",
    "lucide-react",
    "react",
    "react-dom",
    "react-markdown",
    "remark-breaks",
    "remark-gfm"
  ],
  "dev": [
    "@tauri-apps/cli",
    "@testing-library/jest-dom",
    "@testing-library/react",
    "@testing-library/user-event",
    "@types/node",
    "@types/react",
    "@types/react-dom",
    "@vitejs/plugin-react",
    "jsdom",
    "typescript",
    "vite",
    "vitest"
  ]
}

## frontend admin-context search
src/App.tsx:14:import { AdminPolicyConsole } from './components/v1_1/AdminPolicyConsole';
src/App.tsx:15:import { CompanyFormatConsole } from './components/v1_1/CompanyFormatConsole';
src/App.tsx:60:  const [adminPolicyConsoleOpen, setAdminPolicyConsoleOpen] = useState(false);
src/App.tsx:61:  const [companyFormatConsoleOpen, setCompanyFormatConsoleOpen] = useState(false);
src/App.tsx:473:              onClick={() => setAdminPolicyConsoleOpen(true)}
src/App.tsx:488:              onClick={() => setCompanyFormatConsoleOpen(true)}
src/App.tsx:583:        <AdminPolicyConsole onClose={() => setAdminPolicyConsoleOpen(false)} />
src/App.tsx:586:        <CompanyFormatConsole onClose={() => setCompanyFormatConsoleOpen(false)} />
src/components/v1_1/CompanyFormatConsole.tsx:35:  authMethod: 'tauri_secure_invoke',
src/components/v1_1/CompanyFormatConsole.tsx:66:export function CompanyFormatConsole({ onClose }: { onClose: () => void }) {
src/components/v1_1/CompanyFormatConsole.tsx:156:                  <option value="tauri_secure_invoke">tauri_secure_invoke</option>
src/__tests__/CompanyFormatConsole.test.tsx:3:import { CompanyFormatConsole } from '../components/v1_1/CompanyFormatConsole';
src/__tests__/CompanyFormatConsole.test.tsx:21:describe('CompanyFormatConsole v1.2', () => {
src/__tests__/CompanyFormatConsole.test.tsx:45:    render(<CompanyFormatConsole onClose={() => undefined} />);
src/__tests__/CompanyFormatConsole.test.tsx:65:    render(<CompanyFormatConsole onClose={() => undefined} />);
src/__tests__/CompanyFormatConsole.test.tsx:72:    render(<CompanyFormatConsole onClose={() => undefined} />);
src/__tests__/CompanyFormatConsole.test.tsx:81:    render(<CompanyFormatConsole onClose={() => undefined} />);
src/components/v1_1/AdminPolicyConsole.tsx:41:  authMethod: 'tauri_secure_invoke',
src/components/v1_1/AdminPolicyConsole.tsx:91:export function AdminPolicyConsole({ onClose }: { onClose: () => void }) {
src/components/v1_1/AdminPolicyConsole.tsx:176:                  <option value="tauri_secure_invoke">tauri_secure_invoke</option>
src/__tests__/AdminPolicyConsole.test.tsx:3:import { AdminPolicyConsole } from '../components/v1_1/AdminPolicyConsole';
src/__tests__/AdminPolicyConsole.test.tsx:15:describe('AdminPolicyConsole v1.2', () => {
src/__tests__/AdminPolicyConsole.test.tsx:36:    render(<AdminPolicyConsole onClose={() => undefined} />);
src/__tests__/AdminPolicyConsole.test.tsx:55:    render(<AdminPolicyConsole onClose={() => undefined} />);
src/__tests__/AdminPolicyConsole.test.tsx:69:    render(<AdminPolicyConsole onClose={() => undefined} />);
src/lib/admin_policy/contracts.ts:12:export type AdminAuthMethod = 'os_keychain' | 'tauri_secure_invoke' | 'test_only';
src/lib/admin_policy/contracts.ts:89:  admin_id_digest: Sha256Digest;
src/lib/admin_policy/contracts.ts:90:  admin_session_digest: Sha256Digest;
src/lib/admin_policy/contracts.ts:212:  if (!['os_keychain', 'tauri_secure_invoke', 'test_only'].includes(input.authMethod)) {
src/lib/admin_policy/contracts.ts:217:    admin_id_digest: requireSha256Digest(input.adminIdDigest, 'ADMIN_ID'),
src/lib/admin_policy/contracts.ts:218:    admin_session_digest: requireSha256Digest(input.adminSessionDigest, 'ADMIN_SESSION'),
src/lib/admin_policy/client.ts:34:    'X-Admin-Id-Digest': admin.admin_id_digest,
src/lib/admin_policy/client.ts:35:    'X-Admin-Session-Digest': admin.admin_session_digest,

## tauri command/keychain search
src-tauri/src/lib.rs:180:#[tauri::command]
src-tauri/src/lib.rs:233:        .invoke_handler(tauri::generate_handler![get_sidecar_capability_token])

## Step 1 판정 — 기존 admin-context provider (재사용 대상, 신규 생성 금지)

기존 admin-context 취득 방식은 **폼 입력 → 검증 빌더** 패턴이다. zero-arg async provider/Tauri command/keychain flow는 존재하지 않는다(Tauri command은 `get_sidecar_capability_token` 1개뿐).

| 항목 | 파일 | 심볼 | 비고 |
|---|---|---|---|
| admin-context 빌더(provider) | `src/lib/admin_policy/contracts.ts` | `buildAdminHeadersInput(input)` | role/auth_method/sha256 digest 검증 후 `AdminHeaders` 반환. A-2 어댑터가 그대로 재사용 |
| 반환 shape | `src/lib/admin_policy/contracts.ts` | `type AdminHeaders` | `{ role, admin_id_digest, admin_session_digest, auth_method }` — A-2 요구 필드와 일치 |
| digest 검증 | `src/lib/admin_policy/contracts.ts` | `isSha256Digest` / `requireSha256Digest` | `^sha256:[0-9a-f]{64}$` |
| 입력 UI 패턴 | `src/components/v1_1/AdminPolicyConsole.tsx` | useState 폼 + `<input aria-label="Admin ID digest">` 등 | 사용자가 digest/auth_method 입력 → `buildAdminHeadersInput` 호출 |
| admin 헤더 부착 | `src/lib/admin_policy/client.ts` | `buildAdminHeaderRecord(admin)` | `X-Admin-Role/Id-Digest/Session-Digest/Auth-Method` |
| sidecar capability token | `src/lib/connect_loop/sidecarAuth.ts` | `getSidecarCapabilityToken()` → `invoke('get_sidecar_capability_token')` | POST 후보 승인/폐기에 Bearer로 부착 |
| 공통 sidecar fetch | `src/lib/sidecarFetch.ts` | `sidecarFetch()` | Bearer 자동 첨부(참고). A-2 client는 동일 토큰을 직접 부착 |

### 반환값 shape (최소 필요 필드 확인)
```
AdminHeaders = {
  role:               'admin' | 'manager' | 'employee'
  admin_id_digest:    `sha256:${string}`
  admin_session_digest: `sha256:${string}`
  auth_method:        'os_keychain' | 'tauri_secure_invoke' | 'test_only'
}
```
A-2 필수 필드(`admin_id_digest`, `admin_session_digest`, `role`, `auth_method`) 모두 충족.

### 판정 결과
- **PASS**: 기존 provider(`buildAdminHeadersInput`) + 입력 패턴(`AdminPolicyConsole`) + 토큰(`getSidecarCapabilityToken`) 확인됨.
- A-2 `adminContext.ts`는 신규 인증 체계가 아니라 **`buildAdminHeadersInput` 출력 → `AdminContextForSidecar` 정렬 adapter**로만 작성한다.
- 신규 Tauri command / `get_admin_context` / keychain flow는 생성하지 않는다. BLOCKED 보고서 불필요.

## package manager / test runner 판정
- lock 파일: `package-lock.json` (npm).
- 테스트: `npm run test:run` (vitest, jsdom + @testing-library/react). 기존 `src/__tests__/*.test.tsx` 패턴 재사용.
- 타입체크: `npm run build`의 `tsc` 단계 또는 `npx tsc --noEmit`.
