/**
 * Audit Tests
 * Verify immutable append-only behavior
 */

import { createAuditLog, queryAuditLogs, clearAuditLogs } from '../audit/service';
import { CreateAuditLogRequest } from '../models/audit';

describe('Audit Tests', () => {
  beforeEach(() => {
    // Clear audit logs before each test
    clearAuditLogs();
  });

  it('should create immutable audit log entries', () => {
    const request: CreateAuditLogRequest = {
      tenant_id: 'tenant1',
      user_id: 'user1',
      action: 'create',
      resource_type: 'user',
      resource_id: 'user123',
      success: true,
    };

    const log1 = createAuditLog(request);
    const log2 = createAuditLog(request);

    // Each log should have unique ID
    expect(log1.id).not.toBe(log2.id);
    expect(log1.created_at).toBeInstanceOf(Date);
    expect(log2.created_at).toBeInstanceOf(Date);
  });

  it('should block cross-tenant access in queries', () => {
    // Create logs for different tenants
    createAuditLog({
      tenant_id: 'tenant1',
      user_id: 'user1',
      action: 'create',
      resource_type: 'user',
      resource_id: 'user1',
      success: true,
    });

    createAuditLog({
      tenant_id: 'tenant2',
      user_id: 'user2',
      action: 'create',
      resource_type: 'user',
      resource_id: 'user2',
      success: true,
    });

    // Query as tenant1 should only see tenant1 logs
    const logs = queryAuditLogs('tenant1');
    expect(logs.length).toBe(1);
    expect(logs[0].tenant_id).toBe('tenant1');
    expect(logs[0].resource_id).toBe('user1');
  });

  it('should filter audit logs by criteria', () => {
    createAuditLog({
      tenant_id: 'tenant1',
      user_id: 'user1',
      action: 'create',
      resource_type: 'user',
      resource_id: 'user1',
      success: true,
    });

    createAuditLog({
      tenant_id: 'tenant1',
      user_id: 'user2',
      action: 'update',
      resource_type: 'user',
      resource_id: 'user1',
      success: true,
    });

    const logs = queryAuditLogs('tenant1', {
      user_id: 'user1',
    });

    expect(logs.length).toBe(1);
    expect(logs[0].user_id).toBe('user1');
    expect(logs[0].action).toBe('create');
  });

  it('should not allow updates or deletes (append-only)', () => {
    const log = createAuditLog({
      tenant_id: 'tenant1',
      user_id: 'user1',
      action: 'create',
      resource_type: 'user',
      resource_id: 'user1',
      success: true,
    });

    const originalCreatedAt = log.created_at;
    const originalId = log.id;

    // Attempt to modify (should not affect original)
    (log as any).created_at = new Date();
    (log as any).id = 'modified';

    // Original should be unchanged (immutable)
    const logs = queryAuditLogs('tenant1');
    const found = logs.find(l => l.id === originalId);
    expect(found).toBeDefined();
    expect(found?.created_at).toEqual(originalCreatedAt);
  });
});
