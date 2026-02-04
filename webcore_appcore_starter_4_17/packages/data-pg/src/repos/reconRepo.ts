/**
 * Reconciliation Sessions 리포지토리
 * 
 * @module data-pg/repos/reconRepo
 */

import { exec, type ReconSessionRow } from '../index.js';

export class PgReconRepo {
  async get(sessionId: string): Promise<ReconSessionRow | null> {
    const r = await exec('SELECT * FROM recon_sessions WHERE session_id=$1', [sessionId]);
    return r.rows[0] ?? null;
  }

  async getByIdem(tenant: string, idem: string): Promise<ReconSessionRow | null> {
    const r = await exec('SELECT * FROM recon_sessions WHERE tenant=$1 AND idem_key=$2', [tenant, idem]);
    return r.rows[0] ?? null;
  }

  async insert(row: ReconSessionRow): Promise<void> {
    await exec(
      `INSERT INTO recon_sessions(session_id,tenant,created_at,matches,unmatched_bank,unmatched_ledger,idem_key)
       VALUES($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7)`,
      [
        row.session_id,
        row.tenant,
        row.created_at,
        typeof row.matches === 'string' ? row.matches : JSON.stringify(row.matches),
        typeof row.unmatched_bank === 'string' ? row.unmatched_bank : JSON.stringify(row.unmatched_bank),
        typeof row.unmatched_ledger === 'string' ? row.unmatched_ledger : JSON.stringify(row.unmatched_ledger),
        row.idem_key
      ]
    );
  }

  async upsertMatch(sessionId: string, matches: any, unmatchedBank: any, unmatchedLedger: any): Promise<void> {
    await exec(
      `UPDATE recon_sessions
         SET matches=$2::jsonb, unmatched_bank=$3::jsonb, unmatched_ledger=$4::jsonb
       WHERE session_id=$1`,
      [
        sessionId,
        typeof matches === 'string' ? matches : JSON.stringify(matches),
        typeof unmatchedBank === 'string' ? unmatchedBank : JSON.stringify(unmatchedBank),
        typeof unmatchedLedger === 'string' ? unmatchedLedger : JSON.stringify(unmatchedLedger)
      ]
    );
  }
}


