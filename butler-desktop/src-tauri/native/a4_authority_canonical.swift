import CryptoKit
import Foundation

private func a4JSONString(_ value: String) throws -> Data {
    guard !value.unicodeScalars.contains(where: { (0xD800...0xDFFF).contains($0.value) }) else {
        throw A4NativeError.requestSchema
    }
    let encoded = try JSONSerialization.data(
        withJSONObject: [value],
        options: [.withoutEscapingSlashes]
    )
    guard encoded.count >= 2 else { throw A4NativeError.requestSchema }
    return encoded.subdata(in: 1..<(encoded.count - 1))
}

private func a4UTF16Less(_ lhs: String, _ rhs: String) -> Bool {
    Array(lhs.utf16).lexicographicallyPrecedes(Array(rhs.utf16))
}

func a4CanonicalJSON(_ value: Any) throws -> Data {
    if value is NSNull { return Data("null".utf8) }
    if let text = value as? String { return try a4JSONString(text) }
    if let number = value as? NSNumber {
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            return Data(number.boolValue ? "true".utf8 : "false".utf8)
        }
        var integer: Int64 = 0
        guard !CFNumberIsFloatType(number),
              CFNumberGetValue(number, .sInt64Type, &integer),
              number.stringValue == String(integer) else {
            throw A4NativeError.requestSchema
        }
        return Data(String(integer).utf8)
    }
    if let array = value as? [Any] {
        var output = Data("[".utf8)
        for (index, item) in array.enumerated() {
            if index > 0 { output.append(Data(",".utf8)) }
            output.append(try a4CanonicalJSON(item))
        }
        output.append(Data("]".utf8))
        return output
    }
    if let dictionary = value as? [String: Any] {
        var output = Data("{".utf8)
        let keys = dictionary.keys.sorted(by: a4UTF16Less)
        for (index, key) in keys.enumerated() {
            if index > 0 { output.append(Data(",".utf8)) }
            output.append(try a4JSONString(key))
            output.append(Data(":".utf8))
            guard let item = dictionary[key] else { throw A4NativeError.requestSchema }
            output.append(try a4CanonicalJSON(item))
        }
        output.append(Data("}".utf8))
        return output
    }
    throw A4NativeError.requestSchema
}

func a4StrictCanonicalObject(_ data: Data) throws -> [String: Any] {
    guard !data.isEmpty, data.count <= a4MaximumRequestBytes else {
        throw A4NativeError.requestSize
    }
    let value = try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
    guard let object = value as? [String: Any], try a4CanonicalJSON(object) == data else {
        throw A4NativeError.requestSchema
    }
    return object
}

func a4SHA256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func a4AttestationEnvelope(_ canonicalReceipt: Data) throws -> Data {
    guard !canonicalReceipt.isEmpty else { throw A4NativeError.requestSchema }
    var length = UInt64(canonicalReceipt.count).bigEndian
    var output = a4SignatureDomain
    withUnsafeBytes(of: &length) { output.append(contentsOf: $0) }
    output.append(canonicalReceipt)
    return output
}

func a4Base64URL(_ data: Data) -> String {
    data.base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
}
