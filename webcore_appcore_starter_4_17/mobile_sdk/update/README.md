# Mobile SDK Update Pipeline v1

## Overview

Safe update pipeline: fetch (ETag/TTL) + verify (hash/signature) + stage + atomic swap + rollback.

## Features

- **ETag/TTL Cache**: Efficient cache with ETag support and TTL expiration
- **Secure Verification**: Hash and signature verification before staging
- **Atomic Swap**: No partial state visible to inference path
- **Rollback Support**: Restore previous version if needed
- **Fail-Closed**: Verification failure => never apply
- **Offline Resilience**: Keep last-known-good version

## Architecture

```
Fetch (ETag/TTL)
  ↓
Verify (Hash/Signature) → Fail-Closed if invalid
  ↓
Stage (Secure Storage)
  ↓
Atomic Swap (No partial state)
  ↓
Active (Inference path uses this)
```

## Components

### Config Fetcher
- Fetches config with ETag/TTL cache support
- Returns cached content on ETag hit (304 Not Modified)
- Offline resilience: returns cached content if network fails

### Model Fetcher
- Fetches model with ETag/TTL cache support
- Downloads to temporary file, then atomic rename
- Offline resilience: returns cached model if network fails

### Secure Storage
- Verifies hash/signature before staging
- Fail-Closed: verification failure => never stage
- Manages staged, active, and backup directories

### Atomic Swap
- Performs atomic swap: staged → active
- No partial state visible to inference path
- Creates backup before swap (for rollback)

## Usage

```kotlin
// 1. Fetch config
val configFetcher = ConfigFetcher(cacheDir)
val configResult = configFetcher.fetch("https://api.example.com/config")

// 2. Verify and stage
val secureStorage = SecureStorage(storageDir, secretKey)
val hash = secureStorage.calculateHash(configResult.content!!)
val verifyResult = secureStorage.stage(
    configResult.content!!,
    expectedHash = hash,
    fileName = "config.json"
)

if (!verifyResult.valid) {
    // Fail-Closed: never apply
    return
}

// 3. Atomic swap
val atomicSwap = AtomicSwap(secureStorage, "config.json")
val swapResult = atomicSwap.swap()

if (!swapResult.success) {
    // Rollback if needed
    atomicSwap.rollback()
}
```

## Testing

Run integration tests:

```bash
kotlinc -include-runtime -d test.jar update/tests/*.kt
java -jar test.jar
```

Expected output:
```
CACHE_ETAG_HIT_OK=1
ATOMIC_SWAP_OK=1
APPLY_FAILCLOSED_OK=1
```

## Fail-Closed Guarantees

1. **Verification Failure**: Hash/signature mismatch => never stage
2. **No Staged File**: No staged file => swap fails
3. **Atomic Swap**: Either all or nothing (no partial state)
4. **Offline Resilience**: Always keep last-known-good version

