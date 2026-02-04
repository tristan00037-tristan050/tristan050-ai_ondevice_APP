import { forbidMockModeNetwork } from "../../gateway/mw/mock_network_zero_gate";

function mkRes() {
  const res: any = {};
  res.statusCode = 0;
  res.body = null;
  res.status = (c: number) => { res.statusCode = c; return res; };
  res.json = (v: any) => { res.body = v; return res; };
  return res;
}

test("[EVID:MOCK_NETWORK_ZERO_OK] mock mode request must be blocked", () => {
  const req: any = { headers: { "x-os-mode": "mock" } };
  const res = mkRes();
  let nextCalled = false;
  const next = () => { nextCalled = true; };

  forbidMockModeNetwork(req, res as any, next);

  expect(nextCalled).toBe(false);
  expect(res.statusCode).toBe(400);
  expect(res.body?.reason_code).toBe("MOCK_MODE_NETWORK_FORBIDDEN");
});

test("[EVID:MOCK_NETWORK_ZERO_OK] live mode request must pass", () => {
  const req: any = { headers: { "x-os-mode": "live" } };
  const res = mkRes();
  let nextCalled = false;
  const next = () => { nextCalled = true; };

  forbidMockModeNetwork(req, res as any, next);

  expect(nextCalled).toBe(true);
});

