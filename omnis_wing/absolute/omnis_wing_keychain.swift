import Foundation
import Security
import CryptoKit

// Narrow macOS bridge for OMNIS WING R4.  It manages only an explicitly named
// non-exportable P-256 Secure Enclave private key.  It never prints private
// material and has no network behaviour.

enum BridgeError: Error, CustomStringConvertible {
    case message(String)

    var description: String {
        switch self {
        case .message(let text): return text
        }
    }
}

let keyType = kSecAttrKeyTypeECSECPrimeRandom
let keySize = 256

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

func json(_ value: [String: Any]) {
    guard JSONSerialization.isValidJSONObject(value),
          let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    else { fail("json_encode_failed") }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

func tagData(_ tag: String) throws -> Data {
    guard tag.hasPrefix("ai.jourdanlabs.omnis-wing."), tag.count <= 160 else {
        throw BridgeError.message("invalid_application_tag")
    }
    return Data(tag.utf8)
}

func privateKeyQuery(_ tag: String, returnRef: Bool = true) throws -> [CFString: Any] {
    return [
        kSecClass: kSecClassKey,
        kSecAttrApplicationTag: try tagData(tag),
        kSecAttrKeyType: keyType,
        kSecAttrKeyClass: kSecAttrKeyClassPrivate,
        kSecMatchLimit: kSecMatchLimitOne,
        kSecReturnRef: returnRef,
        // Explicitly use the traditional macOS login keychain.  A standalone
        // command-line helper has no app access-group entitlement for the
        // data-protection keychain.
        kSecUseDataProtectionKeychain: false,
        // Health/status must never hang on an invisible authorization sheet.
        // A locked/unavailable key is reported fail-closed by the caller.
        kSecUseAuthenticationUI: kSecUseAuthenticationUIFail,
    ]
}

func loadPrivateKey(_ tag: String) throws -> SecKey? {
    var item: CFTypeRef?
    let status = SecItemCopyMatching(try privateKeyQuery(tag) as CFDictionary, &item)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let key = item as! SecKey? else {
        throw BridgeError.message("keychain_lookup_failed:\(status)")
    }
    return key
}

func publicKeyBytes(_ privateKey: SecKey) throws -> Data {
    guard let publicKey = SecKeyCopyPublicKey(privateKey) else {
        throw BridgeError.message("public_key_unavailable")
    }
    var error: Unmanaged<CFError>?
    guard let bytes = SecKeyCopyExternalRepresentation(publicKey, &error) as Data? else {
        throw BridgeError.message("public_key_export_failed")
    }
    return bytes
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func status(_ tag: String) throws {
    guard let key = try loadPrivateKey(tag) else {
        json(["ready": false, "state": "NOT_ENROLLED", "tag": tag])
        return
    }
    let pub = try publicKeyBytes(key)
    let attributes = (SecKeyCopyAttributes(key) as NSDictionary?) ?? [:]
    let token = attributes[kSecAttrTokenID] as? String
    json([
        "ready": true,
        "state": "ENROLLED",
        "tag": tag,
        "key_type": "P-256",
        // The traditional macOS keychain does not reliably return the token
        // attribute on a later lookup. Do not turn an omitted attribute into
        // a false hardware claim (or a false negative).
        "storage_state": token == (kSecAttrTokenIDSecureEnclave as String)
            ? "SECURE_ENCLAVE"
            : "UNVERIFIED_AT_READ",
        "public_key_sha256": sha256(pub),
    ])
}

func enroll(_ tag: String) throws {
    if try loadPrivateKey(tag) != nil {
        try status(tag)
        return
    }
    var accessError: Unmanaged<CFError>?
    guard let access = SecAccessControlCreateWithFlags(
        kCFAllocatorDefault,
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        .privateKeyUsage,
        &accessError
    ) else {
        throw BridgeError.message("access_control_create_failed")
    }
    let privateAttrs: [CFString: Any] = [
        kSecAttrIsPermanent: true,
        kSecAttrApplicationTag: try tagData(tag),
        kSecAttrAccessControl: access,
    ]
    let parameters: [CFString: Any] = [
        kSecAttrKeyType: keyType,
        kSecAttrKeySizeInBits: keySize,
        kSecAttrTokenID: kSecAttrTokenIDSecureEnclave,
        kSecUseDataProtectionKeychain: false,
        kSecPrivateKeyAttrs: privateAttrs,
    ]
    var error: Unmanaged<CFError>?
    guard let key = SecKeyCreateRandomKey(parameters as CFDictionary, &error) else {
        let detail = error?.takeRetainedValue().localizedDescription ?? "unknown"
        throw BridgeError.message("secure_enclave_enrollment_failed:\(detail)")
    }
    let pub = try publicKeyBytes(key)
    json([
        "ready": true,
        "state": "ENROLLED",
        "tag": tag,
        "key_type": "P-256",
        "storage_state": "SECURE_ENCLAVE_CREATED",
        "public_key_sha256": sha256(pub),
    ])
}

func sign(_ tag: String, messageB64: String) throws {
    guard let key = try loadPrivateKey(tag) else {
        throw BridgeError.message("not_enrolled")
    }
    guard let message = Data(base64Encoded: messageB64) else {
        throw BridgeError.message("invalid_message_encoding")
    }
    let algorithm = SecKeyAlgorithm.ecdsaSignatureMessageX962SHA256
    guard SecKeyIsAlgorithmSupported(key, .sign, algorithm) else {
        throw BridgeError.message("signature_algorithm_unavailable")
    }
    var error: Unmanaged<CFError>?
    guard let sig = SecKeyCreateSignature(key, algorithm, message as CFData, &error) as Data? else {
        let detail = error?.takeRetainedValue().localizedDescription ?? "unknown"
        throw BridgeError.message("sign_failed:\(detail)")
    }
    json(["signature_b64": sig.base64EncodedString()])
}

func publicKey(_ tag: String) throws {
    guard let key = try loadPrivateKey(tag) else { throw BridgeError.message("not_enrolled") }
    json(["public_key_b64": try publicKeyBytes(key).base64EncodedString()])
}

func verify(messageB64: String, signatureB64: String, publicKeyB64: String) throws {
    guard let message = Data(base64Encoded: messageB64),
          let signature = Data(base64Encoded: signatureB64),
          let publicKeyData = Data(base64Encoded: publicKeyB64)
    else { throw BridgeError.message("invalid_verify_encoding") }
    let attrs: [CFString: Any] = [
        kSecAttrKeyType: keyType,
        kSecAttrKeyClass: kSecAttrKeyClassPublic,
        kSecAttrKeySizeInBits: keySize,
    ]
    var error: Unmanaged<CFError>?
    guard let publicKey = SecKeyCreateWithData(publicKeyData as CFData, attrs as CFDictionary, &error) else {
        throw BridgeError.message("public_key_import_failed")
    }
    let algorithm = SecKeyAlgorithm.ecdsaSignatureMessageX962SHA256
    json(["valid": SecKeyVerifySignature(publicKey, algorithm, message as CFData, signature as CFData, nil)])
}

let args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 2 else { fail("usage: omnis_wing_keychain <status|enroll|public-key|sign> <tag> [args]") }
let command = args[0]
let tag = args[1]
do {
    switch command {
    case "status": try status(tag)
    case "enroll": try enroll(tag)
    case "public-key": try publicKey(tag)
    case "sign":
        guard args.count == 3 else { fail("sign_requires_message_b64") }
        try sign(tag, messageB64: args[2])
    case "verify":
        guard args.count == 5 else { fail("verify_requires_message_signature_public_key") }
        try verify(messageB64: args[2], signatureB64: args[3], publicKeyB64: args[4])
    default: fail("unknown_command")
    }
} catch {
    fail(String(describing: error))
}
