import CryptoKit
import Darwin
import Foundation
import Security
import XPC

@_silgen_name("butler_secure_zero")
private func secureZero(_ pointer: UnsafeMutableRawPointer?, _ length: Int)

@_silgen_name("butler_deny_debugger")
private func denyDebugger() -> Int32

private let keychainService = "com.butler.a4.verifier-authority"
private let signingKeyAccount = "ed25519.production.v1"
private let trustWatermarkAccount = "trust-watermark.v5.3"
private let workerSlots = DispatchSemaphore(value: 4)
private let replayLedger = try? A4ReplayLedger()

private struct AuthorityTrust {
    let authorityID: String
    let signerKeyID: String
    let publicKey: Data
    let keyEpoch: Int
    let minimumKeyEpoch: Int
    let trustDigest: String
    let expectedAuthorityCDHash: String
    let expectedVerifierCDHash: String
}

private struct SessionChallenge {
    let sessionID: String
    let requestID: String
    let nonce: Data
    let callerCDHash: String
    let deadlineUnixMS: Int64

    var nonceDigest: String { a4SHA256Hex(nonce) }

    var object: [String: Any] {
        [
            "schema_version": a4ChallengeSchema,
            "protocol_version": a4ProtocolVersion,
            "session_id": sessionID,
            "request_id": requestID,
            "nonce_b64": nonce.base64EncodedString(),
            "caller_cdhash": callerCDHash,
            "deadline_unix_ms": deadlineUnixMS,
        ]
    }
}

private final class PeerSession {
    private let lock = NSLock()
    private var challenge: SessionChallenge?
    private var consumed = false
    let callerCDHash: String

    init(callerCDHash: String) {
        self.callerCDHash = callerCDHash
    }

    func issue() throws -> SessionChallenge {
        lock.lock()
        defer { lock.unlock() }
        var random = Data(count: 32)
        let status = random.withUnsafeMutableBytes { buffer in
            SecRandomCopyBytes(kSecRandomDefault, buffer.count, buffer.baseAddress!)
        }
        guard status == errSecSuccess else { throw A4NativeError.internalFailure }
        let value = SessionChallenge(
            sessionID: UUID().uuidString.lowercased(),
            requestID: UUID().uuidString.lowercased(),
            nonce: random,
            callerCDHash: callerCDHash,
            deadlineUnixMS: Int64(Date().timeIntervalSince1970 * 1_000) + 30_000
        )
        challenge = value
        consumed = false
        return value
    }

    func consume() throws -> SessionChallenge {
        lock.lock()
        defer { lock.unlock() }
        guard let value = challenge, !consumed else { throw A4NativeError.nonceBinding }
        consumed = true
        guard Int64(Date().timeIntervalSince1970 * 1_000) <= value.deadlineUnixMS else {
            throw A4NativeError.requestDeadline
        }
        return value
    }
}

private func mainAppURL() throws -> URL {
    let xpcBundle = Bundle.main.bundleURL.standardizedFileURL
    let app = xpcBundle
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
    guard app.pathExtension == "app" else { throw A4NativeError.bundleContainment }
    return app
}

private func fixedResources() throws -> (python: URL, verifier: URL, trust: URL, build: URL) {
    let app = try mainAppURL()
    let resources = app.appendingPathComponent("Contents/Resources", isDirectory: true)
    let values = try resources.resourceValues(forKeys: [.volumeIsLocalKey])
    guard values.volumeIsLocal == true else { throw A4NativeError.unsafeVolume }
    let result = (
        resources.appendingPathComponent("python/bin/python3"),
        resources.appendingPathComponent("butler_pc_core/a4_verifier/cli.py"),
        resources.appendingPathComponent(
            "butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json"
        ),
        resources.appendingPathComponent("BUILD_INFO.json")
    )
    for url in [result.0, result.1, result.2, result.3] {
        let resolved = url.resolvingSymlinksInPath().standardizedFileURL
        guard resolved.path.hasPrefix(resources.standardizedFileURL.path + "/"),
              FileManager.default.isReadableFile(atPath: resolved.path) else {
            throw A4NativeError.bundleContainment
        }
    }
    return result
}

private func verifyStaticCode(_ url: URL, requirementText: String) throws -> String {
    var staticCode: SecStaticCode?
    guard SecStaticCodeCreateWithPath(url as CFURL, [], &staticCode) == errSecSuccess,
          let staticCode else {
        throw A4NativeError.verifierIdentity
    }
    var requirement: SecRequirement?
    guard SecRequirementCreateWithString(
        requirementText as CFString,
        SecCSFlags(),
        &requirement
    ) == errSecSuccess,
    let requirement else {
        throw A4NativeError.verifierIdentity
    }
    let flags = SecCSFlags(rawValue: kSecCSStrictValidate | kSecCSCheckAllArchitectures)
    guard SecStaticCodeCheckValidity(staticCode, flags, requirement) == errSecSuccess else {
        throw A4NativeError.verifierIdentity
    }
    var information: CFDictionary?
    guard SecCodeCopySigningInformation(
        staticCode,
        SecCSFlags(rawValue: kSecCSSigningInformation),
        &information
    ) == errSecSuccess,
    let dictionary = information as? [String: Any],
    let unique = dictionary[kSecCodeInfoUnique as String] as? Data,
    !unique.isEmpty else {
        throw A4NativeError.verifierIdentity
    }
    return a4SHA256Hex(unique)
}

private func callerCDHash(_ peer: xpc_connection_t) throws -> String {
    let pid = xpc_connection_get_pid(peer)
    guard pid > 1 else { throw A4NativeError.callerIdentity }
    let attributes = [kSecGuestAttributePid as String: NSNumber(value: pid)] as CFDictionary
    var code: SecCode?
    guard SecCodeCopyGuestWithAttributes(nil, attributes, [], &code) == errSecSuccess,
          let code else {
        throw A4NativeError.callerIdentity
    }
    var requirement: SecRequirement?
    guard SecRequirementCreateWithString(
        a4ExpectedCallerRequirement as CFString,
        SecCSFlags(),
        &requirement
    ) == errSecSuccess,
    let requirement,
    SecCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSStrictValidate), requirement) == errSecSuccess else {
        throw A4NativeError.callerIdentity
    }
    var executablePath = [CChar](repeating: 0, count: 4 * 1_024)
    guard proc_pidpath(pid, &executablePath, UInt32(executablePath.count)) > 0 else {
        throw A4NativeError.callerIdentity
    }
    let callerURL = URL(fileURLWithPath: String(cString: executablePath)) as CFURL
    var staticCode: SecStaticCode?
    guard SecStaticCodeCreateWithPath(callerURL, SecCSFlags(), &staticCode) == errSecSuccess,
          let staticCode,
          SecStaticCodeCheckValidity(
              staticCode,
              SecCSFlags(rawValue: kSecCSStrictValidate | kSecCSCheckAllArchitectures),
              requirement
          ) == errSecSuccess else {
        throw A4NativeError.callerIdentity
    }
    var information: CFDictionary?
    guard SecCodeCopySigningInformation(
        staticCode,
        SecCSFlags(rawValue: kSecCSSigningInformation),
        &information
    ) == errSecSuccess,
    let dictionary = information as? [String: Any],
    let unique = dictionary[kSecCodeInfoUnique as String] as? Data,
    !unique.isEmpty else {
        throw A4NativeError.callerIdentity
    }
    if let entitlements = dictionary[kSecCodeInfoEntitlementsDict as String] as? [String: Any],
       entitlements["com.apple.security.get-task-allow"] as? Bool == true {
        throw A4NativeError.callerIdentity
    }
    return a4SHA256Hex(unique)
}

private typealias SetPeerRequirement = @convention(c) (xpc_connection_t, UnsafePointer<CChar>) -> Void

private func enforceKernelPeerRequirement(_ peer: xpc_connection_t) throws {
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "xpc_connection_set_peer_requirement") else {
        throw A4NativeError.callerIdentity
    }
    let function = unsafeBitCast(symbol, to: SetPeerRequirement.self)
    a4ExpectedCallerRequirement.withCString { function(peer, $0) }
}

private func strictTrust(_ url: URL) throws -> AuthorityTrust {
    let raw = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard raw.count <= 32_768 else { throw A4NativeError.trustPolicy }
    let object = try a4StrictCanonicalObject(raw)
    let required: Set<String> = [
        "schema_version", "enabled", "environment", "authority_id", "transport",
        "algorithm", "signer_key_id", "public_key_b64", "key_epoch",
        "minimum_key_epoch", "revoked_key_ids", "not_before_utc", "not_after_utc",
        "expected_authority_cdhash", "expected_verifier_cdhash",
    ]
    guard Set(object.keys) == required,
          object["schema_version"] as? String == "butler.box5.a4.verifier_authority_trust.v5.3",
          object["enabled"] as? Bool == true,
          object["environment"] as? String == "PRODUCTION",
          object["transport"] as? String == "native-xpc-v5.3",
          object["algorithm"] as? String == "Ed25519",
          let authorityID = object["authority_id"] as? String,
          let signerKeyID = object["signer_key_id"] as? String,
          let publicText = object["public_key_b64"] as? String,
          let publicKey = Data(base64Encoded: publicText), publicKey.count == 32,
          let keyEpoch = object["key_epoch"] as? Int,
          let minimumKeyEpoch = object["minimum_key_epoch"] as? Int,
          keyEpoch >= minimumKeyEpoch, minimumKeyEpoch >= 0,
          let revoked = object["revoked_key_ids"] as? [String],
          !revoked.contains(signerKeyID),
          let notBeforeText = object["not_before_utc"] as? String,
          let notAfterText = object["not_after_utc"] as? String,
          let expectedAuthorityCDHash = object["expected_authority_cdhash"] as? String,
          let expectedVerifierCDHash = object["expected_verifier_cdhash"] as? String,
          expectedAuthorityCDHash.range(of: "^(?!0{64}$|f{64}$)[0-9a-f]{64}$", options: .regularExpression) != nil,
          expectedVerifierCDHash.range(of: "^(?!0{64}$|f{64}$)[0-9a-f]{64}$", options: .regularExpression) != nil else {
        throw A4NativeError.trustPolicy
    }
    let formatter = ISO8601DateFormatter()
    guard let notBefore = formatter.date(from: notBeforeText),
          let notAfter = formatter.date(from: notAfterText),
          notBefore <= Date(), Date() < notAfter else {
        throw A4NativeError.trustExpired
    }
    let trust = AuthorityTrust(
        authorityID: authorityID,
        signerKeyID: signerKeyID,
        publicKey: publicKey,
        keyEpoch: keyEpoch,
        minimumKeyEpoch: minimumKeyEpoch,
        trustDigest: a4SHA256Hex(raw),
        expectedAuthorityCDHash: expectedAuthorityCDHash,
        expectedVerifierCDHash: expectedVerifierCDHash
    )
    try enforceTrustWatermark(trust)
    return trust
}

private func keychainQuery(account: String) -> [CFString: Any] {
    [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: keychainService,
        kSecAttrAccount: account,
        kSecAttrAccessGroup: a4KeychainAccessGroup,
        kSecUseDataProtectionKeychain: true,
    ]
}

private func enforceTrustWatermark(_ trust: AuthorityTrust) throws {
    var query = keychainQuery(account: trustWatermarkAccount)
    query[kSecReturnData] = true
    query[kSecMatchLimit] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    let watermark = try a4CanonicalJSON([
        "key_epoch": trust.keyEpoch,
        "trust_digest": trust.trustDigest,
    ])
    if status == errSecItemNotFound {
        var add = keychainQuery(account: trustWatermarkAccount)
        add[kSecValueData] = watermark
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else {
            throw A4NativeError.trustRollback
        }
        return
    }
    guard status == errSecSuccess,
          let existing = result as? Data,
          let object = try? a4StrictCanonicalObject(existing),
          let epoch = object["key_epoch"] as? Int,
          let digest = object["trust_digest"] as? String,
          epoch <= trust.keyEpoch,
          epoch != trust.keyEpoch || digest == trust.trustDigest else {
        throw A4NativeError.trustRollback
    }
    if epoch < trust.keyEpoch {
        let update = [kSecValueData: watermark] as CFDictionary
        guard SecItemUpdate(keychainQuery(account: trustWatermarkAccount) as CFDictionary, update) == errSecSuccess else {
            throw A4NativeError.trustRollback
        }
    }
}

private func loadSigningSeed(expectedPublicKey: Data) throws -> Data {
    var query = keychainQuery(account: signingKeyAccount)
    query[kSecReturnData] = true
    query[kSecMatchLimit] = kSecMatchLimitOne
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let seed = result as? Data,
          seed.count == 32 else {
        throw A4NativeError.keyUnavailable
    }
    let key = try Curve25519.Signing.PrivateKey(rawRepresentation: seed)
    guard key.publicKey.rawRepresentation == expectedPublicKey else {
        throw A4NativeError.keyEpoch
    }
    return seed
}

private func framedVerifierInput(wrapper: Data, source: Data) -> Data {
    var requestLength = UInt32(wrapper.count).bigEndian
    var sourceLength = UInt64(source.count).bigEndian
    var output = Data()
    withUnsafeBytes(of: &requestLength) { output.append(contentsOf: $0) }
    output.append(wrapper)
    withUnsafeBytes(of: &sourceLength) { output.append(contentsOf: $0) }
    output.append(source)
    return output
}

private func decodeFramedObservation(_ data: Data) throws -> [String: Any] {
    guard data.count >= 4 else { throw A4NativeError.verifierIdentity }
    let size = data.prefix(4).reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
    guard size > 0, size <= a4MaximumResponseBytes, data.count == Int(size) + 4 else {
        throw A4NativeError.verifierIdentity
    }
    return try a4StrictCanonicalObject(data.subdata(in: 4..<data.count))
}

private func runVerifier(
    producerRequest: [String: Any],
    canonicalRequest: Data,
    source: Data,
    challenge: SessionChallenge,
    expectedVerifierCDHash: String
) throws -> ([String: Any], String) {
    let resources = try fixedResources()
    let verifierCDHash = try verifyStaticCode(
        resources.python,
        requirementText: a4VerifierRequirement
    )
    guard verifierCDHash == expectedVerifierCDHash else {
        throw A4NativeError.verifierIdentity
    }
    let requestDigest = a4SHA256Hex(canonicalRequest)
    let sourceDigest = a4SHA256Hex(source)
    let wrapper: [String: Any] = [
        "schema_version": a4VerifyRequestSchema,
        "protocol_version": a4ProtocolVersion,
        "challenge": challenge.object,
        "producer_request": producerRequest,
        "request_digest": requestDigest,
        "source_payload_digest": sourceDigest,
    ]
    let canonicalWrapper = try a4CanonicalJSON(wrapper)
    let input = Pipe()
    let output = Pipe()
    let process = Process()
    process.executableURL = resources.python
    process.arguments = [
        "-I", resources.verifier.path, "--verify-observation", "--require-bundled-build-stamp",
    ]
    process.standardInput = input
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    process.environment = [
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    ]
    let termination = DispatchSemaphore(value: 0)
    process.terminationHandler = { _ in termination.signal() }
    let outputReady = DispatchSemaphore(value: 0)
    let outputLock = NSLock()
    var result = Data()
    DispatchQueue.global(qos: .userInitiated).async {
        let captured = output.fileHandleForReading.readDataToEndOfFile()
        outputLock.lock()
        result = captured
        outputLock.unlock()
        outputReady.signal()
    }
    try process.run()
    input.fileHandleForReading.closeFile()
    input.fileHandleForWriting.write(framedVerifierInput(wrapper: canonicalWrapper, source: source))
    input.fileHandleForWriting.closeFile()
    let deadline = DispatchTime.now() + .seconds(30)
    guard termination.wait(timeout: deadline) == .success else {
        process.terminate()
        throw A4NativeError.authorityTimeout
    }
    guard outputReady.wait(timeout: .now() + .seconds(1)) == .success else {
        throw A4NativeError.internalFailure
    }
    outputLock.lock()
    let capturedResult = result
    outputLock.unlock()
    guard capturedResult.count <= Int(a4MaximumResponseBytes) + 4 else {
        throw A4NativeError.requestSize
    }
    guard process.terminationStatus == 0 else { throw A4NativeError.internalFailure }
    let observation = try decodeFramedObservation(capturedResult)
    let expected: Set<String> = [
        "schema_version", "protocol_version", "status", "error_code",
        "authority_session_id", "authority_request_id", "authority_nonce_digest",
        "request_digest", "source_payload_digest", "receipt",
    ]
    guard Set(observation.keys) == expected,
          observation["schema_version"] as? String == a4ObservationSchema,
          observation["protocol_version"] as? String == a4ProtocolVersion,
          observation["status"] as? String == "PASS",
          observation["error_code"] as? String == "NONE",
          observation["authority_session_id"] as? String == challenge.sessionID,
          observation["authority_request_id"] as? String == challenge.requestID,
          observation["authority_nonce_digest"] as? String == challenge.nonceDigest,
          observation["request_digest"] as? String == requestDigest,
          observation["source_payload_digest"] as? String == sourceDigest,
          let receipt = observation["receipt"] as? [String: Any],
          receipt["decision"] as? String == "PASS",
          receipt["schema_version"] as? String == a4ReceiptSchema,
          receipt["contract_id"] as? String == a4ReceiptContract else {
        throw A4NativeError.nonceBinding
    }
    return (receipt, verifierCDHash)
}

private func verifyBuildBinding(_ buildURL: URL) throws {
    let raw = try Data(contentsOf: buildURL)
    let decoded = try JSONSerialization.jsonObject(with: raw, options: [])
    guard let object = decoded as? [String: Any] else {
        throw A4NativeError.codeClosure
    }
    guard let helper = object["a4_authority_helper"] as? [String: Any],
          helper["bundled"] as? Bool == true,
          let expected = helper["sha256"] as? String,
          let executable = Bundle.main.executableURL,
          a4SHA256Hex(try Data(contentsOf: executable)) == expected else {
        throw A4NativeError.codeClosure
    }
}

private func attest(
    canonicalRequest: Data,
    source: Data,
    challenge: SessionChallenge
) throws -> Data {
    guard canonicalRequest.count <= a4MaximumRequestBytes,
          !source.isEmpty, source.count <= a4MaximumSourceBytes else {
        throw A4NativeError.requestSize
    }
    let producerRequest = try a4StrictCanonicalObject(canonicalRequest)
    let required: Set<String> = [
        "schema_version", "protocol_version", "tenant_id", "source_suffix",
        "source_payload_digest", "authority_trust_digest", "evidence_files_b64",
        "finance_trust_b64", "dictionary_b64", "key_material",
    ]
    guard Set(producerRequest.keys) == required,
          producerRequest["schema_version"] as? String == "butler.box5.a4.producer_request.v5.3",
          producerRequest["protocol_version"] as? String == a4ProtocolVersion,
          producerRequest["source_payload_digest"] as? String == a4SHA256Hex(source) else {
        throw A4NativeError.requestSchema
    }
    let resources = try fixedResources()
    try verifyBuildBinding(resources.build)
    let trust = try strictTrust(resources.trust)
    guard producerRequest["authority_trust_digest"] as? String == trust.trustDigest else {
        throw A4NativeError.trustPolicy
    }
    guard let authorityExecutable = Bundle.main.executableURL else {
        throw A4NativeError.verifierIdentity
    }
    let authorityCDHash = try verifyStaticCode(
        authorityExecutable,
        requirementText: a4ExpectedAuthorityRequirement
    )
    guard authorityCDHash == trust.expectedAuthorityCDHash else {
        throw A4NativeError.verifierIdentity
    }
    let (unsignedReceipt, verifierCDHash) = try runVerifier(
        producerRequest: producerRequest,
        canonicalRequest: canonicalRequest,
        source: source,
        challenge: challenge,
        expectedVerifierCDHash: trust.expectedVerifierCDHash
    )
    var receipt = unsignedReceipt
    receipt["authority_id"] = trust.authorityID
    receipt["signer_key_id"] = trust.signerKeyID
    receipt["signer_key_epoch"] = trust.keyEpoch
    receipt["signer_trust_digest"] = trust.trustDigest
    receipt["authority_cdhash"] = authorityCDHash
    receipt["verifier_cdhash"] = verifierCDHash
    let canonicalReceipt = try a4CanonicalJSON(receipt)
    let payloadDigest = a4SHA256Hex(canonicalReceipt)
    guard let ledger = replayLedger else { throw A4NativeError.storageAtomicity }
    try ledger.reserve(
        nonceDigest: challenge.nonceDigest,
        requestID: challenge.requestID,
        payloadDigest: payloadDigest,
        keyEpoch: trust.keyEpoch
    )
    var seed = try loadSigningSeed(expectedPublicKey: trust.publicKey)
    let signature: Data
    do {
        let key = try Curve25519.Signing.PrivateKey(rawRepresentation: seed)
        signature = try key.signature(for: a4AttestationEnvelope(canonicalReceipt))
    }
    seed.withUnsafeMutableBytes { secureZero($0.baseAddress, $0.count) }
    try ledger.commit(
        nonceDigest: challenge.nonceDigest,
        signatureDigest: a4SHA256Hex(signature)
    )
    receipt["signature"] = a4Base64URL(signature)
    let response: [String: Any] = [
        "schema_version": a4ResponseSchema,
        "protocol_version": a4ProtocolVersion,
        "status": "PASS",
        "error_code": "NONE",
        "authority_session_id": challenge.sessionID,
        "authority_request_id": challenge.requestID,
        "authority_nonce_digest": challenge.nonceDigest,
        "request_digest": a4SHA256Hex(canonicalRequest),
        "source_payload_digest": a4SHA256Hex(source),
        "receipt": receipt,
    ]
    let result = try a4CanonicalJSON(response)
    guard result.count <= a4MaximumResponseBytes else { throw A4NativeError.requestSize }
    return result
}

private func xpcData(_ message: xpc_object_t, key: String, maximum: Int) throws -> Data {
    var length = 0
    guard let pointer = xpc_dictionary_get_data(message, key, &length),
          length > 0, length <= maximum else {
        throw A4NativeError.requestSize
    }
    return Data(bytes: pointer, count: length)
}

private func reply(_ request: xpc_object_t, payload: Data?, error: A4NativeError?) {
    guard let response = xpc_dictionary_create_reply(request) else { return }
    if let payload {
        payload.withUnsafeBytes { buffer in
            if let baseAddress = buffer.baseAddress, buffer.count > 0 {
                xpc_dictionary_set_data(response, "payload", baseAddress, buffer.count)
            }
        }
    }
    xpc_dictionary_set_string(response, "error_code", (error?.rawValue ?? "NONE"))
    if let peer = xpc_dictionary_get_remote_connection(request) {
        xpc_connection_send_message(peer, response)
    }
}

private func handle(_ message: xpc_object_t, session: PeerSession) {
    guard xpc_get_type(message) == XPC_TYPE_DICTIONARY,
          let operationPointer = xpc_dictionary_get_string(message, "operation") else {
        reply(message, payload: nil, error: .requestSchema)
        return
    }
    let operation = String(cString: operationPointer)
    do {
        switch operation {
        case "challenge":
            guard let version = xpc_dictionary_get_string(message, "protocol_version"),
                  String(cString: version) == a4ProtocolVersion else {
                throw A4NativeError.protocolVersion
            }
            reply(message, payload: try a4CanonicalJSON(session.issue().object), error: nil)
        case "verify_and_attest":
            guard workerSlots.wait(timeout: .now()) == .success else {
                throw A4NativeError.authoritySaturated
            }
            defer { workerSlots.signal() }
            let request = try xpcData(message, key: "request", maximum: a4MaximumRequestBytes)
            let source = try xpcData(message, key: "source", maximum: a4MaximumSourceBytes)
            reply(
                message,
                payload: try attest(
                    canonicalRequest: request,
                    source: source,
                    challenge: session.consume()
                ),
                error: nil
            )
        case "health":
            let challenge = try xpcData(message, key: "challenge", maximum: 256)
            let response = try a4CanonicalJSON([
                "protocol_version": a4ProtocolVersion,
                "challenge_digest": a4SHA256Hex(challenge),
                "authority_instance": Bundle.main.bundleIdentifier ?? "unknown",
            ])
            reply(message, payload: response, error: nil)
        default:
            throw A4NativeError.requestSchema
        }
    } catch let error as A4NativeError {
        reply(message, payload: nil, error: error)
    } catch {
        reply(message, payload: nil, error: .internalFailure)
    }
}

private func accept(_ peer: xpc_connection_t) {
    do {
        try enforceKernelPeerRequirement(peer)
        let session = PeerSession(callerCDHash: try callerCDHash(peer))
        xpc_connection_set_event_handler(peer) { event in
            handle(event, session: session)
        }
        xpc_connection_resume(peer)
    } catch {
        xpc_connection_cancel(peer)
    }
}

private func run() -> Never {
    guard CommandLine.arguments.count == 1,
          denyDebugger() == 0 else {
        exit(EXIT_FAILURE)
    }
    var coreLimit = rlimit(rlim_cur: 0, rlim_max: 0)
    guard setrlimit(RLIMIT_CORE, &coreLimit) == 0 else { exit(EXIT_FAILURE) }
    _ = umask(0o077)
    xpc_main { peer in accept(peer) }
}

@main
private struct A4VerifierAuthorityService {
    static func main() {
        run()
    }
}
