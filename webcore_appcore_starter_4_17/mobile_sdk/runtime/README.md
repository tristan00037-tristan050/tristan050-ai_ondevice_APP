# Mobile SDK Runtime Adapter v1

## Overview

On-device ML runtime adapter with offline-first operation, deterministic inference, and meta-only performance metrics.

## Features

- **Offline-first**: Runs without network connection
- **Deterministic inference**: Same model + input => same output
- **Meta-only perf metrics**: No user text, only numerical metrics
- **Runtime abstraction**: Interface-based design for multiple runtime backends

## Architecture

```
RuntimeAdapter (interface)
  └── SimpleRuntimeAdapter (implementation)
      ├── loadModel() - Load from local file
      ├── infer() - Run inference (deterministic)
      └── getPerfMetrics() - Get meta-only metrics
```

## Performance Metrics

All metrics are meta-only (numerical values only):

- `inferenceCount`: Total number of inferences
- `latencyP50Ms`: P50 latency (milliseconds)
- `latencyP95Ms`: P95 latency (milliseconds)
- `peakMemoryBytes`: Peak memory usage (bytes)

## Usage

```kotlin
val adapter = SimpleRuntimeAdapter()

// Load model (offline)
adapter.loadModel("/path/to/model.bin")

// Run inference (deterministic)
val input = floatArrayOf(1.0f, 2.0f, 3.0f)
val output = adapter.infer(input)

// Get perf metrics (meta-only)
val metrics = adapter.getPerfMetrics()
println("P50: ${metrics.latencyP50Ms}ms")
println("P95: ${metrics.latencyP95Ms}ms")
println("Peak Memory: ${metrics.peakMemoryBytes} bytes")

// Release resources
adapter.release()
```

## Testing

Run integration tests:

```bash
kotlinc -include-runtime -d test.jar runtime/tests/*.kt
java -jar test.jar
```

Expected output:
```
ONDEVICE_INFER_OK=1
PERF_P50_P95_KEYS_PRESENT=1
PERF_MEMORY_PEAK_KEY_PRESENT=1
```

