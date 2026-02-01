export type Semver = { major: number; minor: number; patch: number };

export function parseSemverStrict(s: string): Semver | null {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(s.trim());
  if (!m) return null;
  const major = Number(m[1]), minor = Number(m[2]), patch = Number(m[3]);
  if (![major, minor, patch].every(Number.isInteger)) return null;
  return { major, minor, patch };
}

export function compareSemver(a: string, b: string): -1 | 0 | 1 | null {
  const pa = parseSemverStrict(a);
  const pb = parseSemverStrict(b);
  if (!pa || !pb) return null;
  if (pa.major !== pb.major) return pa.major < pb.major ? -1 : 1;
  if (pa.minor !== pb.minor) return pa.minor < pb.minor ? -1 : 1;
  if (pa.patch !== pb.patch) return pa.patch < pb.patch ? -1 : 1;
  return 0;
}

