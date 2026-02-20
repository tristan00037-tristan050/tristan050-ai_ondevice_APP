import process from "node:process";

function percentile(values, p) {
  const a = [...values].sort((x, y) => x - y);
  if (a.length === 0) return NaN;
  const idx = Math.floor((p / 100) * (a.length - 1));
  return a[idx];
}

const runs = Number(process.argv[2]);
if (!Number.isFinite(runs) || runs <= 0 || runs > 200) {
  console.error("BAD_RUNS");
  process.exit(2);
}

const samples = [];
let sum = 0;

for (let i = 0; i < runs; i++) {
  const start = process.cpuUsage();
  let acc = 0;
  for (let j = 0; j < 20000; j++) acc += (j % 7);
  const du = process.cpuUsage(start); // microseconds
  const ms = (du.user + du.system) / 1000.0; // µs -> ms
  samples.push(ms);
  sum += ms;
}

const p50 = percentile(samples, 50);

process.stdout.write(JSON.stringify({
  sample_count: samples.length,
  sum_ms: sum,
  p50_ms: p50
}));
