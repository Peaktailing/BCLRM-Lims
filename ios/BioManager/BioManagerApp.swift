import BackgroundTasks
import SwiftUI

/// BioManager for iPhone and iPad: a companion for the lab's BioManager server.
/// The first launch asks for the server's address; after that it opens straight
/// into BioManager. Change server, on the screen shown when the server
/// cannot be reached, points it somewhere else.
@main
struct BioManagerApp: App {
    @State private var server: URL? = Server.saved
    @Environment(\.scenePhase) private var phase

    init() {
        // This phone's copy of the facility stays fresh (OfflineStore): when the
        // network comes back, and in the background when iOS allows.
        OfflineStore.shared.start()
        BGTaskScheduler.shared.register(forTaskWithIdentifier: OfflineStore.refreshTask, using: nil) { task in
            BioManagerApp.scheduleRefresh()
            let work = Task {
                await OfflineStore.shared.sync()
                task.setTaskCompleted(success: true)
            }
            task.expirationHandler = { work.cancel() }
        }
    }

    static func scheduleRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: OfflineStore.refreshTask)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if let server {
                    MainView(server: server) { self.server = nil }
                        .id(server)   // a new server starts a fresh page
                } else {
                    SetupView { self.server = $0 }
                }
            }
            .tint(Color.accentColor)
            .onChange(of: phase) { now in
                if now == .active { Task { await OfflineStore.shared.sync() } }
                if now == .background { BioManagerApp.scheduleRefresh() }
            }
        }
    }
}
