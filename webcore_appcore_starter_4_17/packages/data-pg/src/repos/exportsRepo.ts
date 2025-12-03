/**
 * Export Jobs 리포지토리
 * 
 * @module data-pg/repos/exportsRepo
 */

import { exec, type ExportJobRow } from '../index.js';

export class PgExportRepo {
  async get(jobId: string): Promise<ExportJobRow | null> {
    const r = await exec('SELECT * FROM export_jobs WHERE job_id=$1', [jobId]);
    return r.rows[0] ?? null;
  }

  async getByIdem(tenant: string, idem: string): Promise<ExportJobRow | null> {
    const r = await exec('SELECT * FROM export_jobs WHERE tenant=$1 AND idem_key=$2', [tenant, idem]);
    return r.rows[0] ?? null;
  }

  async insert(row: ExportJobRow): Promise<void> {
    await exec(
      `INSERT INTO export_jobs(job_id,tenant,status,created_at,exp,sha256,manifest,filters,idem_key)
       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
      [row.job_id, row.tenant, row.status, row.created_at, row.exp, row.sha256, row.manifest, row.filters, row.idem_key]
    );
  }
}


