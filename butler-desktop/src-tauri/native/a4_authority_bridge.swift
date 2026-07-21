import Darwin
import Foundation
import XPC

private typealias SetPeerRequirementBridge = @convention(c) (
    xpc_connection_t,
    UnsafePointer<CChar>
) -> Void

private func bridgePeerRequirement(_ connection: xpc_connection_t) throws {
    guard let symbol = dlsym(
        UnsafeMutableRawPointer(bitPattern: -2),
        "xpc_connection_set_peer_requirement"
    ) else {
        throw A4NativeError.authorityIdentity
    }
    let function = unsafeBitCast(symbol, to: SetPeerRequirementBridge.self)
    a4ExpectedAuthorityRequirement.withCString { function(connection, $0) }
}

private func bridgeMessage(operation: String) -> xpc_object_t {
    let message = xpc_dictionary_create(nil, nil, 0)
    xpc_dictionary_set_string(message, "operation", operation)
    return message
}

private func bridgeReply(
    _ connection: xpc_connection_t,
    message: xpc_object_t,
    maximum: Int
) throws -> Data {
    let response = xpc_connection_send_message_with_reply_sync(connection, message)
    guard xpc_get_type(response) == XPC_TYPE_DICTIONARY,
          let errorPointer = xpc_dictionary_get_string(response, "error_code") else {
        throw A4NativeError.authorityIdentity
    }
    let error = String(cString: errorPointer)
    guard error == "NONE" else {
        throw A4NativeError(rawValue: error) ?? .internalFailure
    }
    var length = 0
    guard let pointer = xpc_dictionary_get_data(response, "payload", &length),
          length > 0, length <= maximum else {
        throw A4NativeError.requestSize
    }
    return Data(bytes: pointer, count: length)
}

private func roundtrip(request: Data, source: Data) throws -> Data {
    guard !request.isEmpty, request.count <= a4MaximumRequestBytes,
          !source.isEmpty, source.count <= a4MaximumSourceBytes else {
        throw A4NativeError.requestSize
    }
    let connection = xpc_connection_create_mach_service(
        a4XPCServiceName,
        nil,
        0
    )
    try bridgePeerRequirement(connection)
    xpc_connection_set_event_handler(connection) { _ in }
    xpc_connection_resume(connection)
    defer { xpc_connection_cancel(connection) }

    let challenge = bridgeMessage(operation: "challenge")
    xpc_dictionary_set_string(challenge, "protocol_version", a4ProtocolVersion)
    _ = try bridgeReply(connection, message: challenge, maximum: 4_096)

    let verify = bridgeMessage(operation: "verify_and_attest")
    request.withUnsafeBytes { buffer in
        if let baseAddress = buffer.baseAddress {
            xpc_dictionary_set_data(verify, "request", baseAddress, buffer.count)
        }
    }
    source.withUnsafeBytes { buffer in
        if let baseAddress = buffer.baseAddress {
            xpc_dictionary_set_data(verify, "source", baseAddress, buffer.count)
        }
    }
    return try bridgeReply(
        connection,
        message: verify,
        maximum: a4MaximumResponseBytes
    )
}

@_cdecl("butler_a4_authority_verify")
public func butlerA4AuthorityVerify(
    _ requestPointer: UnsafePointer<UInt8>?,
    _ requestLength: Int,
    _ sourcePointer: UnsafePointer<UInt8>?,
    _ sourceLength: Int,
    _ outputPointer: UnsafeMutablePointer<UnsafeMutablePointer<UInt8>?>?,
    _ outputLength: UnsafeMutablePointer<Int>?
) -> Int32 {
    guard let requestPointer,
          let sourcePointer,
          let outputPointer,
          let outputLength,
          requestLength > 0,
          sourceLength > 0 else {
        return 1
    }
    do {
        let response = try roundtrip(
            request: Data(bytes: requestPointer, count: requestLength),
            source: Data(bytes: sourcePointer, count: sourceLength)
        )
        guard let allocated = malloc(response.count) else { return 2 }
        response.copyBytes(to: allocated.assumingMemoryBound(to: UInt8.self), count: response.count)
        outputPointer.pointee = allocated.assumingMemoryBound(to: UInt8.self)
        outputLength.pointee = response.count
        return 0
    } catch let error as A4NativeError {
        switch error {
        case .authoritySaturated: return 3
        case .authorityTimeout: return 4
        case .callerIdentity, .authorityIdentity: return 5
        default: return 6
        }
    } catch {
        return 7
    }
}

@_cdecl("butler_a4_authority_free")
public func butlerA4AuthorityFree(
    _ pointer: UnsafeMutablePointer<UInt8>?,
    _ length: Int
) {
    guard let pointer, length >= 0 else { return }
    free(pointer)
}
