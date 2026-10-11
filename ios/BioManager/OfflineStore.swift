import Foundation
import Network
import Security
import UIKit
import WebKit

/// This phone's copy of the facility, for working where there is no signal
/// (the server's side is app/sync.py).
///
/// While the lab's server answers, the app keeps what its person needs (the
/// server's snapshot) and catches up from the change feed: at launch, when the
/// app comes forward, when the network comes back, every 15 minutes while it is
/// open, and in the background when iOS allows. When the server can't be
/// reached, the web view shows the offline screens the app carries
/// (app/static/offline/), which read this copy and add what is done to a queue;
/// the queue goes to the lab, in order, as soon as it answers again.
///
/// The phone signs in to sync as one of its person's devices: once they are
/// signed in through the app's page, it asks the server for a device token of
/// its own (POST /api/devices/this-app), kept in the Keychain. The copy is kept
/// in the app's own files with iOS Data Protection.
final class OfflineStore {
    static let shared = OfflineStore()
    static let refreshTask = "org.biomanager.app.refresh"

    private let lock = NSLock()
    private var syncing = false
    private var registering = false
    private var nextRegistration = Date.distantPast
    private let monitor = NWPathMonitor()

    enum StoreError: LocalizedError {
        case notJoined, signedOut, server(Int)
        var errorDescription: String? {
            switch self {
            case .notJoined: return "This phone hasn't signed in to sync yet."
            case .signedOut: return "This phone was signed out of the lab."
            case .server(let code): return "The server answered \(code)."
            }
        }
    }

    // ------------------------------------------------------------ where it lives
    private var server: URL? { Server.saved }

    private var key: String {
        guard let server else { return "lab" }
        return (server.host ?? "lab") + "-" + String(server.port ?? 0)
    }

    private var folder: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("offline", isDirectory: true).appendingPathComponent(key, isDirectory: true)
    }

    var token: String? {
        get { Keychain.read("device-token-" + key) }
        set { Keychain.write("device-token-" + key, newValue) }
    }

    private var deviceId: String? {
        get { UserDefaults.standard.string(forKey: "device-id-" + key) }
        set { UserDefaults.standard.set(newValue, forKey: "device-id-" + key) }
    }

    private func read(_ name: String) -> Any? {
        lock.lock(); defer { lock.unlock() }
        guard let data = try? Data(contentsOf: folder.appendingPathComponent(name + ".json")) else { return nil }
        return try? JSONSerialization.jsonObject(with: data)
    }

    private func write(_ name: String, _ value: Any) {
        lock.lock(); defer { lock.unlock() }
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        guard let data = try? JSONSerialization.data(withJSONObject: value) else { return }
        // Readable in the background once the phone has been unlocked since it started.
        try? data.write(to: folder.appendingPathComponent(name + ".json"),
                        options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    func snapshot() -> [String: Any]? { read("snapshot") as? [String: Any] }
    func queue() -> [[String: Any]] { read("queue") as? [[String: Any]] ?? [] }
    private func state() -> [String: Any] { read("state") as? [String: Any] ?? [:] }

    private func setState(_ changes: [String: Any]) {
        var current = state()
        for (k, v) in changes { current[k] = v }
        write("state", current)
    }

    var hasCopy: Bool { snapshot() != nil }

    /// Signed out, or pointed at another server: nothing of the lab stays here.
    func forget() {
        lock.lock(); defer { lock.unlock() }
        try? FileManager.default.removeItem(at: folder)
        Keychain.write("device-token-" + key, nil)
    }

    // ------------------------------------------------------------ what the screens do
    func add(_ op: [String: Any]) throws -> Int {
        guard let id = op["op"] as? String, !id.isEmpty, op["action"] is String else {
            throw NSError(domain: "BioManager", code: 1, userInfo: [NSLocalizedDescriptionKey: "a change is {op, action, …}"])
        }
        var list = queue()
        if !list.contains(where: { ($0["op"] as? String) == id }) {
            list.append(op)
            write("queue", list)
        }
        return list.count
    }

    func status() -> [String: Any] {
        let snap = snapshot()
        let st = state()
        return ["waiting": queue().count, "taken": snap?["taken"] ?? "", "cursor": snap?["cursor"] ?? NSNull(),
                "has_copy": snap != nil, "last_sync": st["last_sync"] ?? "", "error": st["error"] ?? "",
                "held": st["held"] ?? 0, "refused": st["refused"] ?? [], "online": st["online"] ?? false]
    }

    /// The bundle's words in the phone's language (app/translations/zh/js-offline.json).
    func strings() -> [String: Any] {
        let zh = Locale.preferredLanguages.first?.hasPrefix("zh") == true
        guard zh, let url = Bundle.main.url(forResource: "js-offline", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let words = try? JSONSerialization.jsonObject(with: data) else { return ["lang": "en", "words": [:]] }
        return ["lang": "zh", "words": words]
    }

    // ------------------------------------------------------------ talking to the server
    private func endpoint(_ path: String) -> URL? {
        guard let server else { return nil }
        var base = server.absoluteString
        while base.hasSuffix("/") { base.removeLast() }
        return URL(string: base + path)
    }

    private func call(_ method: String, _ path: String, body: Any? = nil, timeout: TimeInterval = 60) async throws -> [String: Any] {
        guard let url = endpoint(path), let token else { throw StoreError.notJoined }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.httpShouldHandleCookies = false
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(Self.version, forHTTPHeaderField: "X-BioManager-Version")
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 {
            self.token = nil
            throw StoreError.signedOut
        }
        guard (200..<300).contains(code) else { throw StoreError.server(code) }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    static var version: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0" }

    /// Whether the lab's server answers just now.
    func reachable() async -> Bool {
        guard let url = endpoint("/healthz") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 6
        request.cachePolicy = .reloadIgnoringLocalCacheData
        guard let answer = try? await URLSession.shared.data(for: request) else { return false }
        let (data, response) = answer
        return (response as? HTTPURLResponse)?.statusCode == 200
            && String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines) == "ok"
    }

    private func begin() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if syncing { return false }
        syncing = true
        return true
    }

    private func end() {
        lock.lock(); syncing = false; lock.unlock()
    }

    /// Send what waits, in order; then catch up with the lab.
    @discardableResult
    func sync() async -> [String: Any] {
        guard token != nil, begin() else { return status() }
        defer { end() }
        do {
            try await push()
            try await catchUp()
            setState(["online": true, "error": "", "last_sync": ISO8601DateFormatter().string(from: Date())])
        } catch {
            setState(["online": false, "error": error.localizedDescription])
        }
        return status()
    }

    private static let finished: Set<String> = ["applied", "merged", "held", "refused"]

    private func push() async throws {
        let waiting = queue()
        guard !waiting.isEmpty else { return }
        let answer = try await call("POST", "/api/sync/push", body: ["ops": Array(waiting.prefix(200))], timeout: 300)
        let results = answer["results"] as? [[String: Any]] ?? []
        var done = Set<String>()
        var ids: [String: Any] = [:]
        var refused = state()["refused"] as? [[String: Any]] ?? []
        for r in results {
            guard let op = r["op"] as? String, let result = r["result"] as? String else { continue }
            if Self.finished.contains(result) { done.insert(op) }
            if result == "refused" { refused.append(["op": op, "message": r["message"] ?? ""]) }
            if let made = r["ids"] as? [String: Any] { ids.merge(made) { $1 } }
        }
        // Later changes naming what an applied one made now name the real record.
        let remaining = queue().filter { !done.contains(($0["op"] as? String) ?? "") }.map { Self.rename($0, ids) }
        write("queue", remaining)
        setState(["held": answer["held"] ?? 0, "refused": Array(refused.suffix(50))])
    }

    private static func rename(_ value: Any, _ ids: [String: Any]) -> Any {
        if let text = value as? String, let real = ids[text] { return real }
        if let list = value as? [Any] { return list.map { rename($0, ids) } }
        if let dict = value as? [String: Any] { return dict.mapValues { rename($0, ids) } }
        return value
    }

    private static func rename(_ op: [String: Any], _ ids: [String: Any]) -> [String: Any] {
        rename(op as Any, ids) as? [String: Any] ?? op
    }

    private static let tables = ["mice": "mice", "mouse_cages": "cages", "litters": "litters", "mouse_weights": "weights",
                                 "tasks": "tasks", "mouse_racks": "racks", "stock_units": "stock_units", "tanks": "tanks"]

    private func catchUp() async throws {
        if var snap = snapshot(), let cursor = snap["cursor"] as? Int {
            let answer = try await call("GET", "/api/sync/changes?since=\(cursor)")
            if (answer["reset"] as? Bool) != true {
                let changes = answer["changes"] as? [String: [[String: Any]]] ?? [:]
                for (name, rows) in changes {
                    var current: [Int: [String: Any]] = [:]
                    var order: [Int] = []
                    for row in snap[name] as? [[String: Any]] ?? [] {
                        if let id = row["id"] as? Int { current[id] = row; order.append(id) }
                    }
                    for row in rows {
                        guard let id = row["id"] as? Int else { continue }
                        if current[id] == nil { order.append(id) }
                        current[id] = row
                    }
                    snap[name] = order.compactMap { current[$0] }
                }
                for gone in answer["gone"] as? [[String: Any]] ?? [] {
                    guard let table = gone["table"] as? String, let name = Self.tables[table],
                          let id = gone["id"] as? Int else { continue }
                    snap[name] = (snap[name] as? [[String: Any]] ?? []).filter { ($0["id"] as? Int) != id }
                }
                snap["cursor"] = answer["cursor"] ?? cursor
                snap["taken"] = ISO8601DateFormatter().string(from: Date())
                write("snapshot", snap)
                return
            }
        }
        let fresh = try await call("GET", "/api/sync/snapshot", timeout: 300)
        if (fresh["ok"] as? Bool) == true { write("snapshot", fresh) }
    }

    // ------------------------------------------------------------ signing in to sync
    /// Once its person is signed in through the app's page, the phone asks for a
    /// device token of its own, with the page's sign-in (its cookies).
    @MainActor
    func registerIfNeeded(_ webView: WKWebView) {
        guard token == nil, let server, !registering, Date() > nextRegistration else { return }
        registering = true
        nextRegistration = Date().addingTimeInterval(60)
        let agent = webView.customUserAgent ?? ""
        let name = UIDevice.current.name
        webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
            let mine = cookies.filter { cookie in
                let domain = cookie.domain.hasPrefix(".") ? String(cookie.domain.dropFirst()) : cookie.domain
                return server.host?.lowercased().hasSuffix(domain.lowercased()) == true
            }
            Task {
                await self.register(cookies: mine, agent: agent, name: name)
                self.registering = false
            }
        }
    }

    private func register(cookies: [HTTPCookie], agent: String, name: String) async {
        guard let url = endpoint("/api/devices/this-app"), let server, !cookies.isEmpty else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpShouldHandleCookies = false
        for (name, value) in HTTPCookie.requestHeaderFields(with: cookies) { request.setValue(value, forHTTPHeaderField: name) }
        request.setValue(agent, forHTTPHeaderField: "User-Agent")
        var origin = server.absoluteString
        while origin.hasSuffix("/") { origin.removeLast() }
        request.setValue(origin, forHTTPHeaderField: "Origin")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = ["name": name, "platform": "ios", "app_version": Self.version]
        if let deviceId { body["replaces"] = deviceId }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        guard let reply = try? await URLSession.shared.data(for: request),
              (reply.1 as? HTTPURLResponse)?.statusCode == 200,
              let answer = (try? JSONSerialization.jsonObject(with: reply.0)) as? [String: Any],
              let token = answer["token"] as? String else { return }
        self.token = token
        deviceId = answer["device"] as? String
        await sync()
    }

    // ------------------------------------------------------------ keeping it fresh
    /// Catch up whenever the network comes back.
    func start() {
        monitor.pathUpdateHandler = { path in
            if path.status == .satisfied { Task { await OfflineStore.shared.sync() } }
        }
        monitor.start(queue: DispatchQueue(label: "org.biomanager.network"))
    }
}

/// The device token, in the Keychain: this phone only, after its first unlock.
enum Keychain {
    static func read(_ account: String) -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "BioManager",
                                    kSecAttrAccount as String: account, kSecReturnData as String: true,
                                    kSecMatchLimit as String: kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func write(_ account: String, _ value: String?) {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "BioManager",
                                   kSecAttrAccount as String: account]
        SecItemDelete(base as CFDictionary)
        guard let value, let data = value.data(using: .utf8) else { return }
        var item = base
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(item as CFDictionary, nil)
    }
}
