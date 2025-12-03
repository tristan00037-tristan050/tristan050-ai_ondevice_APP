import React, { useEffect, useState } from 'react';

type ExportJob = {
  job_id: string;
  status: string;
  created_at: string;
  tenant: string;
};

export default function ExportJobs() {
  const [rows, setRows] = useState<ExportJob[]>([]);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>('');
  const pageSize = 20;

  useEffect(() => {
    // TODO: 실제 BFF API 엔드포인트로 교체
    // const u = new URL('/v1/accounting/exports/reports', window.location.origin);
    // u.searchParams.set('page', String(page));
    // u.searchParams.set('page_size', String(pageSize));
    // if (status) u.searchParams.set('status', status);
    // fetch(u.toString(), {
    //   headers: {
    //     'X-Tenant': 'default',
    //     'X-User-Id': 'operator-ui',
    //     'X-User-Role': 'operator',
    //   },
    // })
    //   .then((r) => r.json())
    //   .then((d) => setRows(d.items || []));
    
    // 임시: 빈 배열
    setRows([]);
  }, [page, status]);

  return (
    <div>
      <h2>Export Jobs</h2>
      <div style={{ display: 'flex', gap: 8 }}>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All Status</option>
          <option value="pending">Pending</option>
          <option value="running">Running</option>
          <option value="done">Done</option>
          <option value="failed">Failed</option>
          <option value="expired">Expired</option>
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>Job ID</th>
            <th>Status</th>
            <th>Created At</th>
            <th>Tenant</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.job_id}</td>
              <td>{r.status}</td>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td>{r.tenant}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 8 }}>
        <button onClick={() => setPage(Math.max(1, page - 1))}>Prev</button>
        <span style={{ margin: '0 8px' }}>Page {page}</span>
        <button onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

