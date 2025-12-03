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
       VALUES($1,$2,$3,$4,$5,$6,$7)`,
      [row.session_id, row.tenant, row.created_at, row.matches, row.unmatched_bank, row.unmatched_ledger, row.idem_key]
    );
  }

  async upsertMatch(sessionId: string, matches: any, unmatchedBank: any, unmatchedLedger: any): Promise<void> {
    await exec(
      `UPDATE recon_sessions
         SET matches=$2, unmatched_bank=$3, unmatched_ledger=$4
       WHERE session_id=$1`,
      [sessionId, matches, unmatchedBank, unmatchedLedger]
    );
  }
}


