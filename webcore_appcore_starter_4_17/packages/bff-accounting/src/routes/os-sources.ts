import { Router } from 'express';
import { pool } from '@appcore/data-pg';

const router = Router();

router.get('/v1/accounting/os/sources', async (req: any, res: any, next: any) => {
  try {
    const tenant = req?.ctx?.tenant || req.header('X-Tenant') || '';
    const r = await pool.query(
      `
      SELECT source, last_cursor, last_ts, updated_at
      FROM external_ledger_offset WHERE tenant=$1 ORDER BY source ASC
    `,
      [tenant]
    );
    res.json({ items: r.rows });
  } catch (e) {
    next(e);
  }
});

export default router;

