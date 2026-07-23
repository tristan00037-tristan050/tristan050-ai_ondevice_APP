import Foundation

@_silgen_name("butler_secure_zero")
func a4SecureZero(_ pointer: UnsafeMutableRawPointer?, _ length: Int)

typealias A4SeedZeroizer = (inout Data) -> Void

func a4ZeroizeData(_ data: inout Data) {
    data.withUnsafeMutableBytes { buffer in
        a4SecureZero(buffer.baseAddress, buffer.count)
    }
}

func a4WithZeroizedSigningSeed<Result>(
    loadSeed: () throws -> Data,
    zeroize: A4SeedZeroizer = a4ZeroizeData,
    operation: (Data) throws -> Result
) throws -> Result {
    var seed = try loadSeed()
    defer { zeroize(&seed) }
    return try operation(seed)
}
