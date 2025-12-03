import React, { useEffect, useState } from 'react';

type ReconSession = {
  session_id: string;
  tenant: string;
  created_at: string;
  matches: any;
  unmatched_bank: any;
  unmatched_ledger: any;
};

export default function ReconSessions() {
  const [rows, setRows] = useState<ReconSession[]>([]);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  useEffect(() => {
    // TODO: 실제 BFF API 엔드포인트로 교체
    // const u = new URL('/v1/accounting/reconciliation/sessions', window.location.origin);
    // u.searchParams.set('page', String(page));
    // u.searchParams.set('page_size', String(pageSize));
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
  }, [page]);

  return (
    <div>
      <h2>Reconciliation Sessions</h2>
      <table>
        <thead>
          <tr>
            <th>Session ID</th>
            <th>Matches</th>
            <th>Unmatched Bank</th>
            <th>Unmatched Ledger</th>
            <th>Created At</th>
            <th>Tenant</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.session_id}</td>
              <td>{Array.isArray(r.matches) ? r.matches.length : 0}</td>
              <td>{Array.isArray(r.unmatched_bank) ? r.unmatched_bank.length : 0}</td>
              <td>{Array.isArray(r.unmatched_ledger) ? r.unmatched_ledger.length : 0}</td>
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

