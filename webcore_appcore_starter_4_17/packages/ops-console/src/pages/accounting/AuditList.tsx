import React, { useEffect, useState } from 'react';

type AuditRow = {
  ts: string;
  action: string;
  subject_type: string;
  subject_id: string;
  actor: string;
  tenant: string;
};

export default function AuditList() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<string>('');
  const [actor, setActor] = useState<string>('');
  const pageSize = 20;

  useEffect(() => {
    const u = new URL('/v1/accounting/audit', window.location.origin);
    u.searchParams.set('page', String(page));
    u.searchParams.set('page_size', String(pageSize));
    if (action) u.searchParams.set('action', action);
    if (actor) u.searchParams.set('actor', actor);
    fetch(u.toString(), {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'auditor-ui',
        'X-User-Role': 'auditor',
      },
    })
      .then((r) => r.json())
      .then((d) => setRows(d.items || []));
  }, [page, action, actor]);

  return (
    <div>
      <h2>Audit Events</h2>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          placeholder="action filter"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        />
        <input
          placeholder="actor filter"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
      </div>
      <table>
        <thead>
          <tr>
            <th>ts</th>
            <th>action</th>
            <th>subject</th>
            <th>actor</th>
            <th>tenant</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{new Date(r.ts).toLocaleString()}</td>
              <td>{r.action}</td>
              <td>
                {r.subject_type}#{r.subject_id}
              </td>
              <td>{r.actor}</td>
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

