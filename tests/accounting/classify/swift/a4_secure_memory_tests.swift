import Foundation

private enum InjectedSigningFailure: Error {
    case keyConstruction
    case signature
}

@main
private struct A4SecureMemoryTests {
    static func main() throws {
        try assertZeroizedAfterFailure(.keyConstruction)
        try assertZeroizedAfterFailure(.signature)
        try assertZeroizedAfterSuccess()
        print("A4_SIGNING_SEED_DEFER_ZEROIZATION_OK=1")
    }

    private static func assertZeroizedAfterFailure(_ failure: InjectedSigningFailure) throws {
        var zeroizerCalled = false
        do {
            _ = try a4WithZeroizedSigningSeed(
                loadSeed: { Data(repeating: 0xA5, count: 32) },
                zeroize: { seed in
                    a4ZeroizeData(&seed)
                    precondition(seed.allSatisfy { $0 == 0 })
                    zeroizerCalled = true
                },
                operation: { seed -> Data in
                    precondition(seed == Data(repeating: 0xA5, count: 32))
                    throw failure
                }
            )
            preconditionFailure("injected signing failure was not raised")
        } catch let error as InjectedSigningFailure {
            precondition(error == failure)
        }
        precondition(zeroizerCalled)
    }

    private static func assertZeroizedAfterSuccess() throws {
        var zeroizerCalled = false
        let signature = try a4WithZeroizedSigningSeed(
            loadSeed: { Data(repeating: 0x5A, count: 32) },
            zeroize: { seed in
                a4ZeroizeData(&seed)
                precondition(seed.allSatisfy { $0 == 0 })
                zeroizerCalled = true
            },
            operation: { seed in Data(seed.prefix(8)) }
        )
        precondition(signature == Data(repeating: 0x5A, count: 8))
        precondition(zeroizerCalled)
    }
}
