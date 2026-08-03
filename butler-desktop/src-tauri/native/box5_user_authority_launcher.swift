import Foundation

private func readOneCanonicalLine() throws -> Data {
    let input = FileHandle.standardInput
    var collected = Data()
    while collected.count <= box5MaximumNativeRequestBytes {
        let chunk = input.readData(ofLength: min(4_096, box5MaximumNativeRequestBytes + 1 - collected.count))
        if chunk.isEmpty { break }
        collected.append(chunk)
    }
    guard !collected.isEmpty,
          collected.count <= box5MaximumNativeRequestBytes,
          collected.last == 0x0A else {
        throw Box5AuthorityError.blocked
    }
    collected.removeLast()
    guard !collected.contains(0x0A), !collected.contains(0x0D) else {
        throw Box5AuthorityError.blocked
    }
    return collected
}

do {
    let request = try decodeBox5AuthorityRequest(readOneCanonicalLine())
    let issued = try issueBox5Assertion(request)
    var response = try box5AuthorityResponse(
        nonce: request.request_nonce,
        assertion: issued.assertion,
        expiresAt: issued.expiresAt
    )
    response.append(0x0A)
    try FileHandle.standardOutput.write(contentsOf: response)
    response.resetBytes(in: 0..<response.count)
} catch {
    exit(70)
}
