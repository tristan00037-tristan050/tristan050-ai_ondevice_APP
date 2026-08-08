import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

let box5AuthoritySchema = "2.0"
let box5AuthorityAudience = "butler-box5-accounting"
let box5AuthorityHelperIdentifier = "com.butler.box5.user-authority.v2"
let box5MaximumNativeRequestBytes = 32 * 1_024

enum Box5AuthorityError: Error {
    case blocked
}

struct Box5AuthorityRequest: Decodable {
    let schema_version: String
    let request_nonce: String
    let action: String
    let resource: String
    let body_sha256: String
    let session_binding_sha256: String
}

private struct Box5TrustKey {
    let keyID: String
    let publicKey: Data
}

private struct Box5TrustPolicy {
    let policyID: String
    let issuer: String
    let audience: String
    let notBefore: Int64
    let expiresAt: Int64
    let activeKey: Box5TrustKey
}

private struct Box5Enrollment {
    let subject: String
    let tenantID: String
    let companyID: String
}

private let authorityActions: Set<String> = [
    "ASSIGNMENT_CREATE",
    "RULE_FUTURE_CREATE",
    "RULE_DEACTIVATE",
    "RULE_APPLICATION_REVERT",
    "QUARANTINE_ROW_RECOMPILE",
    "CONFLICT_RESOLVE",
]

private func exactKeys(_ object: [String: Any], _ expected: Set<String>) -> Bool {
    Set(object.keys) == expected
}

private func matches(_ value: String, _ pattern: String) -> Bool {
    value.range(of: pattern, options: .regularExpression) != nil
}

private func strictObject(_ data: Data, maximum: Int) throws -> [String: Any] {
    guard !data.isEmpty, data.count <= maximum,
          let object = try JSONSerialization.jsonObject(
              with: data,
              options: [.fragmentsAllowed]
          ) as? [String: Any] else {
        throw Box5AuthorityError.blocked
    }
    return object
}

private func canonicalJSON(_ object: [String: Any]) throws -> Data {
    guard JSONSerialization.isValidJSONObject(object) else {
        throw Box5AuthorityError.blocked
    }
    return try JSONSerialization.data(
        withJSONObject: object,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
}

private func sha256(_ data: Data) -> Data {
    Data(SHA256.hash(data: data))
}

private func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func fixedTimeEqual(_ lhs: String, _ rhs: String) -> Bool {
    let left = Array(lhs.utf8)
    let right = Array(rhs.utf8)
    guard left.count == right.count else { return false }
    var difference: UInt8 = 0
    for index in left.indices { difference |= left[index] ^ right[index] }
    return difference == 0
}

private func base64URLNoPadding(_ data: Data) -> String {
    data.base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}

private func base64URLDecode(_ text: String) throws -> Data {
    guard matches(text, "^[A-Za-z0-9_-]+$") else { throw Box5AuthorityError.blocked }
    let standard = text.replacingOccurrences(of: "-", with: "+")
        .replacingOccurrences(of: "_", with: "/")
    let padding = String(repeating: "=", count: (4 - standard.count % 4) % 4)
    guard let data = Data(base64Encoded: standard + padding),
          base64URLNoPadding(data) == text else {
        throw Box5AuthorityError.blocked
    }
    return data
}

private func randomData(count: Int) throws -> Data {
    var value = Data(count: count)
    let status = value.withUnsafeMutableBytes { buffer in
        SecRandomCopyBytes(kSecRandomDefault, count, buffer.baseAddress!)
    }
    guard status == errSecSuccess else { throw Box5AuthorityError.blocked }
    return value
}

private func fixedPolicyURL() throws -> URL {
    let executable = URL(fileURLWithPath: CommandLine.arguments[0])
        .resolvingSymlinksInPath()
        .standardizedFileURL
    let directory = executable.deletingLastPathComponent()
    guard executable.lastPathComponent == "Box5UserAuthority",
          directory.lastPathComponent == "box5" else {
        throw Box5AuthorityError.blocked
    }
    let policy = directory.appendingPathComponent("authorization-trust-policy-v2.json")
    let values = try policy.resourceValues(forKeys: [
        .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey, .volumeIsLocalKey,
    ])
    guard values.isRegularFile == true,
          values.isSymbolicLink != true,
          values.volumeIsLocal == true,
          let size = values.fileSize, (1...32_768).contains(size) else {
        throw Box5AuthorityError.blocked
    }
    return policy
}

private func loadTrustPolicy(now: Int64) throws -> Box5TrustPolicy {
    let raw = try Data(contentsOf: fixedPolicyURL(), options: [.mappedIfSafe])
    guard fixedTimeEqual(sha256Hex(raw), box5ApprovedPolicySHA256) else {
        throw Box5AuthorityError.blocked
    }
    var documentBytes = raw
    if documentBytes.last == 0x0A { documentBytes.removeLast() }
    let object = try strictObject(documentBytes, maximum: 32_768)
    guard exactKeys(object, [
        "schema_version", "policy_id", "issuer", "audience", "not_before",
        "expires_at", "keys",
    ]), try canonicalJSON(object) == documentBytes,
    object["schema_version"] as? String == box5AuthoritySchema,
    let policyID = object["policy_id"] as? String,
    matches(policyID, "^[A-Za-z0-9._-]{1,80}$"),
    let issuer = object["issuer"] as? String, (1...200).contains(issuer.utf8.count),
    let audience = object["audience"] as? String, audience == box5AuthorityAudience,
    let notBefore = object["not_before"] as? NSNumber,
    let expiresAt = object["expires_at"] as? NSNumber,
    CFGetTypeID(notBefore) != CFBooleanGetTypeID(),
    CFGetTypeID(expiresAt) != CFBooleanGetTypeID(),
    notBefore.int64Value >= 0,
    notBefore.int64Value <= now, now < expiresAt.int64Value,
    let keys = object["keys"] as? [[String: Any]], (1...8).contains(keys.count) else {
        throw Box5AuthorityError.blocked
    }
    var active: [Box5TrustKey] = []
    var seen = Set<String>()
    for key in keys {
        guard exactKeys(key, ["key_id", "alg", "public_key_b64url", "status"]),
              let keyID = key["key_id"] as? String,
              matches(keyID, "^[A-Za-z0-9._-]{1,80}$"), seen.insert(keyID).inserted,
              key["alg"] as? String == "EdDSA",
              let publicText = key["public_key_b64url"] as? String,
              let status = key["status"] as? String,
              status == "ACTIVE" || status == "RETIRED_VERIFY_ONLY" else {
            throw Box5AuthorityError.blocked
        }
        let publicKey = try base64URLDecode(publicText)
        guard publicKey.count == 32 else { throw Box5AuthorityError.blocked }
        if status == "ACTIVE" { active.append(Box5TrustKey(keyID: keyID, publicKey: publicKey)) }
    }
    guard active.count == 1 else { throw Box5AuthorityError.blocked }
    return Box5TrustPolicy(
        policyID: policyID,
        issuer: issuer,
        audience: audience,
        notBefore: notBefore.int64Value,
        expiresAt: expiresAt.int64Value,
        activeKey: active[0]
    )
}

private func verifyParentDesignatedRequirement() throws {
    let parentPID = getppid()
    guard parentPID > 1 else { throw Box5AuthorityError.blocked }
    let attributes = [kSecGuestAttributePid as String: NSNumber(value: parentPID)] as CFDictionary
    var parentCode: SecCode?
    guard SecCodeCopyGuestWithAttributes(nil, attributes, [], &parentCode) == errSecSuccess,
          let parentCode else { throw Box5AuthorityError.blocked }
    var requirement: SecRequirement?
    guard SecRequirementCreateWithString(
        box5ExpectedCallerRequirement as CFString,
        SecCSFlags(),
        &requirement
    ) == errSecSuccess,
    let requirement,
    SecCodeCheckValidity(
        parentCode,
        SecCSFlags(rawValue: kSecCSStrictValidate),
        requirement
    ) == errSecSuccess else {
        throw Box5AuthorityError.blocked
    }
    // Check immutable product constraints against the live guest as a dynamic
    // SecCode. SecCodeCopySigningInformation is a SecStaticCode API in current
    // SDK overlays and would both fail to compile and weaken the live-process
    // binding if replaced with a path-based static lookup.
    var productRequirement: SecRequirement?
    let productRequirementText =
        "identifier \"com.butler.desktop\" and !entitlement[\"com.apple.security.get-task-allow\"] exists"
    guard SecRequirementCreateWithString(
        productRequirementText as CFString,
        SecCSFlags(),
        &productRequirement
    ) == errSecSuccess,
    let productRequirement,
    SecCodeCheckValidity(
        parentCode,
        SecCSFlags(rawValue: kSecCSStrictValidate),
        productRequirement
    ) == errSecSuccess else {
        throw Box5AuthorityError.blocked
    }
}

private func requireUserPresence() throws -> LAContext {
    let context = LAContext()
    context.localizedReason = "Box5 회계 변경을 승인합니다."
    context.interactionNotAllowed = false
    var error: NSError?
    guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
        throw Box5AuthorityError.blocked
    }
    let semaphore = DispatchSemaphore(value: 0)
    var approved = false
    context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: context.localizedReason) {
        result, _ in
        approved = result
        semaphore.signal()
    }
    guard semaphore.wait(timeout: .now() + 25) == .success, approved else {
        context.invalidate()
        throw Box5AuthorityError.blocked
    }
    return context
}

private func keychainData(account: String, context: LAContext) throws -> Data {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: box5KeychainService,
        kSecAttrAccount as String: account,
        kSecAttrAccessGroup as String: box5KeychainAccessGroup,
        kSecUseDataProtectionKeychain as String: true,
        kSecUseAuthenticationContext as String: context,
        kSecMatchLimit as String: kSecMatchLimitOne,
        kSecReturnData as String: true,
    ]
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let data = result as? Data, !data.isEmpty, data.count <= 4_096 else {
        throw Box5AuthorityError.blocked
    }
    return data
}

private func loadEnrollment(context: LAContext) throws -> Box5Enrollment {
    let raw = try keychainData(account: box5EnrollmentAccount, context: context)
    let object = try strictObject(raw, maximum: 4_096)
    guard exactKeys(object, ["schema_version", "sub", "tenant_id", "company_id"]),
          try canonicalJSON(object) == raw,
          object["schema_version"] as? String == box5AuthoritySchema,
          let subject = object["sub"] as? String,
          matches(subject, "^[A-Za-z0-9._:@-]{1,128}$"),
          let tenantID = object["tenant_id"] as? String,
          matches(tenantID, "^[A-Za-z0-9._-]{1,80}$"),
          let companyID = object["company_id"] as? String,
          matches(companyID, "^[A-Za-z0-9._-]{1,80}$") else {
        throw Box5AuthorityError.blocked
    }
    return Box5Enrollment(subject: subject, tenantID: tenantID, companyID: companyID)
}

func decodeBox5AuthorityRequest(_ raw: Data) throws -> Box5AuthorityRequest {
    let object = try strictObject(raw, maximum: box5MaximumNativeRequestBytes)
    guard exactKeys(object, [
        "schema_version", "request_nonce", "action", "resource", "body_sha256",
        "session_binding_sha256",
    ]), try canonicalJSON(object) == raw,
    object["schema_version"] as? String == box5AuthoritySchema,
    let nonce = object["request_nonce"] as? String,
    matches(nonce, "^[A-Za-z0-9_-]{22,86}$"),
    let action = object["action"] as? String, authorityActions.contains(action),
    let resource = object["resource"] as? String,
    matches(resource, "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"),
    !resource.contains("%"), !resource.contains("//"),
    let bodyDigest = object["body_sha256"] as? String,
    matches(bodyDigest, "^[a-f0-9]{64}$"),
    let sessionDigest = object["session_binding_sha256"] as? String,
    matches(sessionDigest, "^[a-f0-9]{64}$") else {
        throw Box5AuthorityError.blocked
    }
    return try JSONDecoder().decode(Box5AuthorityRequest.self, from: raw)
}

func issueBox5Assertion(_ request: Box5AuthorityRequest) throws -> (assertion: String, expiresAt: Int64) {
    try verifyParentDesignatedRequirement()
    let now = Int64(Date().timeIntervalSince1970)
    let trust = try loadTrustPolicy(now: now)
    let context = try requireUserPresence()
    defer { context.invalidate() }
    let enrollment = try loadEnrollment(context: context)
    var seed = try keychainData(account: box5SigningKeyAccount, context: context)
    defer { seed.resetBytes(in: 0..<seed.count) }
    guard seed.count == 32 else { throw Box5AuthorityError.blocked }
    let privateKey = try Curve25519.Signing.PrivateKey(rawRepresentation: seed)
    guard privateKey.publicKey.rawRepresentation == trust.activeKey.publicKey else {
        throw Box5AuthorityError.blocked
    }
    let deviceText = "device_" + request.session_binding_sha256.dropFirst(32).prefix(16)
    let deviceID = sha256Hex(Data(deviceText.utf8))
    let expiresAt = min(now + 60, trust.expiresAt)
    guard trust.notBefore <= now, expiresAt > now else { throw Box5AuthorityError.blocked }
    var jti = try randomData(count: 16)
    defer { jti.resetBytes(in: 0..<jti.count) }
    let payload: [String: Any] = [
        "ver": box5AuthoritySchema,
        "iss": trust.issuer,
        "aud": trust.audience,
        "sub": enrollment.subject,
        "tenant_id": enrollment.tenantID,
        "company_id": enrollment.companyID,
        "device_id": deviceID,
        "session_id": request.session_binding_sha256,
        "action": request.action,
        "resource": request.resource,
        "iat": now,
        "nbf": now,
        "exp": expiresAt,
        "jti": jti.map { String(format: "%02x", $0) }.joined(),
        "nonce": request.request_nonce,
        "policy_id": trust.policyID,
        "kid": trust.activeKey.keyID,
        "alg": "EdDSA",
    ]
    let protected: [String: Any] = [
        "alg": "EdDSA", "kid": trust.activeKey.keyID, "typ": "BUTLER-UA2",
    ]
    let protectedSegment = base64URLNoPadding(try canonicalJSON(protected))
    let payloadSegment = base64URLNoPadding(try canonicalJSON(payload))
    var signingInput = Data((protectedSegment + "." + payloadSegment).utf8)
    defer { signingInput.resetBytes(in: 0..<signingInput.count) }
    let signature = try privateKey.signature(for: signingInput)
    return (
        protectedSegment + "." + payloadSegment + "." + base64URLNoPadding(signature),
        expiresAt
    )
}

func box5AuthorityResponse(nonce: String, assertion: String, expiresAt: Int64) throws -> Data {
    try canonicalJSON([
        "schema_version": box5AuthoritySchema,
        "request_nonce": nonce,
        "assertion": assertion,
        "expires_at": expiresAt,
    ])
}
