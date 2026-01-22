/**
 * In-memory store for attestation decisions
 * Tracks allow/deny counts per tenant
 */

interface AttestationRecord {
  tenant_id: string;
  timestamp: number;
  allowed: boolean;
  reason_code?: string;
}

class AttestationStore {
  private records: AttestationRecord[] = [];

  /**
   * Record an attestation decision
   */
  record(tenant_id: string, allowed: boolean, reason_code?: string): void {
    this.records.push({
      tenant_id,
      timestamp: Date.now(),
      allowed,
      reason_code,
    });
  }

  /**
   * Get allow count for a tenant
   */
  getAllowCount(tenant_id: string): number {
    return this.records.filter(
      (r) => r.tenant_id === tenant_id && r.allowed === true
    ).length;
  }

  /**
   * Get deny count for a tenant
   */
  getDenyCount(tenant_id: string): number {
    return this.records.filter(
      (r) => r.tenant_id === tenant_id && r.allowed === false
    ).length;
  }

  /**
   * Get total count for a tenant
   */
  getTotalCount(tenant_id: string): number {
    return this.records.filter((r) => r.tenant_id === tenant_id).length;
  }

  /**
   * Clear all records (for testing)
   */
  clear(): void {
    this.records = [];
  }

  /**
   * Get all records for a tenant
   */
  getRecords(tenant_id: string): AttestationRecord[] {
    return this.records.filter((r) => r.tenant_id === tenant_id);
  }
}

// Singleton instance
export const attestationStore = new AttestationStore();

// Export for testing
export function clearStore(): void {
  attestationStore.clear();
}

