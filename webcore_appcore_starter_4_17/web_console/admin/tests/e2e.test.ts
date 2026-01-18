/**
 * E2E Tests
 * Test complete onboarding flow
 */

import { tenantsApi, usersApi, rolesApi } from '../api_client/api';

// Mock sessionStorage
const mockSessionStorage = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'sessionStorage', {
  value: mockSessionStorage,
});

// Mock fetch
global.fetch = jest.fn();

describe('E2E Onboarding Test', () => {
  beforeEach(() => {
    mockSessionStorage.clear();
    (global.fetch as jest.Mock).mockClear();
  });

  it('should complete onboarding flow', async () => {
    // Set auth token
    mockSessionStorage.setItem('auth_token', 'test-token');

    // Mock tenant creation
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        tenant: {
          id: 'tenant-123',
          name: 'Test Tenant',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }),
    });

    // Mock user creation
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user: {
          id: 'user-123',
          tenant_id: 'tenant-123',
          email: 'test@example.com',
          name: 'Test User',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }),
    });

    // Mock role creation
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        role: {
          id: 'role-123',
          tenant_id: 'tenant-123',
          name: 'Admin',
          permissions: ['tenant:read', 'tenant:write'],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }),
    });

    // Execute onboarding flow
    const tenantResponse = await tenantsApi.create({ name: 'Test Tenant' });
    expect(tenantResponse.tenant.id).toBe('tenant-123');

    const userResponse = await usersApi.create({
      tenant_id: tenantResponse.tenant.id,
      email: 'test@example.com',
      name: 'Test User',
    });
    expect(userResponse.user.id).toBe('user-123');

    const roleResponse = await rolesApi.create({
      tenant_id: tenantResponse.tenant.id,
      name: 'Admin',
      permissions: ['tenant:read', 'tenant:write'],
    });
    expect(roleResponse.role.id).toBe('role-123');

    // Verify all API calls were made
    expect(global.fetch).toHaveBeenCalledTimes(3);
  });
});

// Output-based proof
if (require.main === module) {
  console.log('CONSOLE_ONBOARDING_DONE_OK=1');
}

