import { useEffect, useState } from 'react';

export default function AccountingCard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch('/v1/accounting/os/summary', {
      headers: {
        'X-Tenant': 'default',
        'X-User-Id': 'ops',
        'X-User-Role': 'admin',
      },
    })
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, []);

  if (!data) return <div>Accounting: Loading…</div>;

  return (
    <div>
      <h3>Accounting</h3>
      <div>
        Approvals ✓ {data.approvals.approved} / ✗ {data.approvals.rejected}
      </div>
      <div>
        Exports total {data.exports.total}, failed {data.exports.failed}, expired{' '}
        {data.exports.expired}
      </div>
      <div>Recon open {data.recon.open}</div>
      <div>Errors(5xx) last hour {data.errors.err5xx}</div>
    </div>
  );
}

