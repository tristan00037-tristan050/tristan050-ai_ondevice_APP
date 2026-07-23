import Foundation

let a4ProtocolVersion = "butler.box5.a4.authority_protocol.v5.3"
let a4ChallengeSchema = "butler.box5.a4.authority_challenge.v5.3"
let a4VerifyRequestSchema = "butler.box5.a4.verify_request.v5.3"
let a4ObservationSchema = "butler.box5.a4.verified_observation.v5.3"
let a4ResponseSchema = "butler.box5.a4.authority_response.v5.3"
let a4ReceiptSchema = "butler.box5.a4.verification_receipt.v5.3"
let a4ReceiptContract = "BUTLER-BOX5-A4-V5.3-NATIVE-AUTHORITY"
let a4SignatureDomain = Data("BUTLER-A4-ATTESTATION-V5.3\0".utf8)
let a4MaximumRequestBytes = 32 * 1024 * 1024
let a4MaximumSourceBytes = 32 * 1024 * 1024
let a4MaximumResponseBytes = 512 * 1024

@objc protocol A4AuthorityXPCProtocol {
    func issueChallenge(
        _ protocolVersion: String,
        withReply reply: @escaping (Data?, String?) -> Void
    )

    func verifyAndAttest(
        _ canonicalRequest: Data,
        source: Data,
        withReply reply: @escaping (Data?, String?) -> Void
    )

    func health(
        _ challenge: Data,
        withReply reply: @escaping (Data?, String?) -> Void
    )
}

enum A4NativeError: String, Error {
    case processHardening = "BLOCK_PROCESS_HARDENING"
    case protocolVersion = "BLOCK_PROTOCOL_VERSION"
    case callerIdentity = "BLOCK_CALLER_IDENTITY"
    case authorityIdentity = "BLOCK_AUTHORITY_IDENTITY"
    case verifierIdentity = "BLOCK_VERIFIER_IDENTITY"
    case bundleContainment = "BLOCK_BUNDLE_CONTAINMENT"
    case codeClosure = "BLOCK_CODE_CLOSURE"
    case unsafeVolume = "BLOCK_UNSAFE_VOLUME"
    case keyUnavailable = "BLOCK_KEY_UNAVAILABLE"
    case keyEpoch = "BLOCK_KEY_EPOCH"
    case trustPolicy = "BLOCK_TRUST_POLICY"
    case trustRollback = "BLOCK_TRUST_ROLLBACK"
    case trustExpired = "BLOCK_TRUST_EXPIRED"
    case signature = "BLOCK_SIGNATURE"
    case requestSchema = "BLOCK_REQUEST_SCHEMA"
    case requestSize = "BLOCK_REQUEST_SIZE"
    case requestDeadline = "BLOCK_REQUEST_DEADLINE"
    case nonceBinding = "BLOCK_NONCE_BINDING"
    case replay = "BLOCK_REPLAY_OR_EQUIVOCATION"
    case sourceDigest = "BLOCK_SOURCE_DIGEST"
    case authoritySaturated = "BLOCK_AUTHORITY_SATURATED"
    case authorityTimeout = "BLOCK_AUTHORITY_TIMEOUT"
    case storageAtomicity = "BLOCK_STORAGE_ATOMICITY"
    case internalFailure = "UNVERIFIED_INTERNAL"
}
