type Flushable = { flushNow: () => void };

const regs = new Set<Flushable>();

export function registerPersist(f: Flushable) {
  regs.add(f);
}

export function flushAllPersistNow() {
  for (const f of regs) {
    try { f.flushNow(); } catch {}
  }
}

let hooked = false;
export function hookProcessFlush() {
  if (hooked) return;
  hooked = true;

  const run = () => flushAllPersistNow();

  process.on("exit", run);
  process.on("SIGINT", () => { run(); process.exit(0); });
  process.on("SIGTERM", () => { run(); process.exit(0); });
}

