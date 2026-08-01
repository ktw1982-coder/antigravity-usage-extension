import AppKit
import Foundation

struct QuotaData: Codable {
    // Gemini models
    let gemini_weekly_percentage: Double?
    let gemini_weekly_remaining: String?
    let gemini_weekly_refresh: String?
    let gemini_five_hour_percentage: Double?
    let gemini_five_hour_remaining: String?
    let gemini_five_hour_refresh: String?
    
    // Claude/GPT models
    let claude_weekly_percentage: Double?
    let claude_weekly_remaining: String?
    let claude_weekly_refresh: String?
    let claude_five_hour_percentage: Double?
    let claude_five_hour_remaining: String?
    let claude_five_hour_refresh: String?
    
    let last_updated: Int?
    let status: String?
    let error_message: String?
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var menu: NSMenu!
    
    // UI Outlets
    var geminiHeaderItem: NSMenuItem!
    var geminiWeeklyMenuItem: NSMenuItem!
    var geminiWeeklyBarMenuItem: NSMenuItem!
    var geminiFiveHourMenuItem: NSMenuItem!
    var geminiFiveHourBarMenuItem: NSMenuItem!
    
    var claudeHeaderItem: NSMenuItem!
    var claudeWeeklyMenuItem: NSMenuItem!
    var claudeWeeklyBarMenuItem: NSMenuItem!
    var claudeFiveHourMenuItem: NSMenuItem!
    var claudeFiveHourBarMenuItem: NSMenuItem!
    
    var updatedMenuItem: NSMenuItem!
    var launchAtLoginMenuItem: NSMenuItem!
    
    // Reference to the backend python process
    var pythonProcess: Process?
    
    // Flag to control quick retries during initialization or error states
    var isQuickRetrying = false
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // 1. Start the backend python server (packaged in Resources)
        startBackendServer()
        
        // 2. Create the Status Bar Item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "AG: --%"
        }
        
        // Setup dropdown Menu list
        menu = NSMenu()
        
        // -- Gemini Group --
        geminiHeaderItem = NSMenuItem(title: "── GEMINI MODELS ──", action: nil, keyEquivalent: "")
        geminiWeeklyMenuItem = NSMenuItem(title: "Weekly: --%", action: nil, keyEquivalent: "")
        geminiWeeklyBarMenuItem = NSMenuItem(title: "  └─ [□□□□□□□□□□] (Used: 0%)", action: nil, keyEquivalent: "")
        geminiFiveHourMenuItem = NSMenuItem(title: "5-Hour: --%", action: nil, keyEquivalent: "")
        geminiFiveHourBarMenuItem = NSMenuItem(title: "  └─ [□□□□□□□□□□] (Used: 0%)", action: nil, keyEquivalent: "")
        
        geminiHeaderItem.isEnabled = false
        geminiWeeklyMenuItem.isEnabled = false
        geminiWeeklyBarMenuItem.isEnabled = false
        geminiFiveHourMenuItem.isEnabled = false
        geminiFiveHourBarMenuItem.isEnabled = false
        
        menu.addItem(geminiHeaderItem)
        menu.addItem(geminiWeeklyMenuItem)
        menu.addItem(geminiWeeklyBarMenuItem)
        menu.addItem(geminiFiveHourMenuItem)
        menu.addItem(geminiFiveHourBarMenuItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // -- Claude & GPT Group --
        claudeHeaderItem = NSMenuItem(title: "── CLAUDE & GPT MODELS ──", action: nil, keyEquivalent: "")
        claudeWeeklyMenuItem = NSMenuItem(title: "Weekly: --%", action: nil, keyEquivalent: "")
        claudeWeeklyBarMenuItem = NSMenuItem(title: "  └─ [□□□□□□□□□□] (Used: 0%)", action: nil, keyEquivalent: "")
        claudeFiveHourMenuItem = NSMenuItem(title: "5-Hour: --%", action: nil, keyEquivalent: "")
        claudeFiveHourBarMenuItem = NSMenuItem(title: "  └─ [□□□□□□□□□□] (Used: 0%)", action: nil, keyEquivalent: "")
        
        claudeHeaderItem.isEnabled = false
        claudeWeeklyMenuItem.isEnabled = false
        claudeWeeklyBarMenuItem.isEnabled = false
        claudeFiveHourMenuItem.isEnabled = false
        claudeFiveHourBarMenuItem.isEnabled = false
        
        menu.addItem(claudeHeaderItem)
        menu.addItem(claudeWeeklyMenuItem)
        menu.addItem(claudeWeeklyBarMenuItem)
        menu.addItem(claudeFiveHourMenuItem)
        menu.addItem(claudeFiveHourBarMenuItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // -- Last Update & Control --
        updatedMenuItem = NSMenuItem(title: "Last Update: --", action: nil, keyEquivalent: "")
        updatedMenuItem.isEnabled = false
        menu.addItem(updatedMenuItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Launch at Login Toggle
        launchAtLoginMenuItem = NSMenuItem(title: "Launch at Login", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        launchAtLoginMenuItem.target = self
        launchAtLoginMenuItem.state = isLaunchAtLoginEnabled() ? .on : .off
        menu.addItem(launchAtLoginMenuItem)
        
        menu.addItem(NSMenuItem.separator())
        
        let refreshItem = NSMenuItem(title: "Force Refresh", action: #selector(refreshQuota), keyEquivalent: "r")
        refreshItem.target = self
        menu.addItem(refreshItem)
        
        let quitItem = NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)
        
        statusItem.menu = menu
        
        // Timer for polling every 60 seconds
        Timer.scheduledTimer(withTimeInterval: 60.0, repeats: true) { _ in
            self.fetchQuota()
        }
        
        // Start immediate fetch after launch (0.5s instead of 2.5s) to trigger quick polling loop
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.fetchQuota()
        }
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        stopBackendServer()
    }
    
    func startBackendServer() {
        // Retrieve the server.py path dynamically from the App Bundle Resources folder
        guard let scriptPath = Bundle.main.path(forResource: "server", ofType: "py") else {
            print("❌ Error: server.py not found in App Bundle Resources!")
            DispatchQueue.main.async {
                self.updateUIWithError("Resources missing")
            }
            return
        }
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        
        let myPid = ProcessInfo.processInfo.processIdentifier
        
        // Wrap path in quotes to support folders with spaces
        let command = "python3 \"\(scriptPath)\" 8484 \(myPid)"
        process.arguments = ["-c", command]
        
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        
        do {
            try process.run()
            self.pythonProcess = process
            print("Backend Python server started automatically (PID: \(process.processIdentifier), Parent PID: \(myPid)).")
        } catch {
            print("Failed to auto-start backend server: \(error)")
        }
    }
    
    func stopBackendServer() {
        guard let process = pythonProcess, process.isRunning else { return }
        print("Stopping backend Python server (PID: \(process.processIdentifier))...")
        process.terminate()
        process.waitUntilExit()
        print("Backend server stopped.")
    }
    
    @objc func refreshQuota() {
        fetchQuota()
    }
    
    @objc func quitApp() {
        stopBackendServer()
        NSApplication.shared.terminate(nil)
    }
    
    func fetchQuota() {
        guard let url = URL(string: "http://localhost:8484/usage") else { return }
        
        let task = URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                
                if let error = error {
                    self.updateUIWithError(error.localizedDescription)
                    self.scheduleQuickRetry()
                    return
                }
                
                guard let data = data else {
                    self.updateUIWithError("No data received")
                    self.scheduleQuickRetry()
                    return
                }
                
                do {
                    let decoder = JSONDecoder()
                    let quota = try decoder.decode(QuotaData.self, from: data)
                    
                    if quota.status == "Initializing" {
                        self.updateUI(with: quota)
                        self.scheduleQuickRetry()
                    } else {
                        // Success: Stop quick retry loop and update UI
                        self.isQuickRetrying = false
                        self.updateUI(with: quota)
                    }
                } catch {
                    self.updateUIWithError("JSON Parsing failed")
                    self.scheduleQuickRetry()
                }
            }
        }
        task.resume()
    }
    
    func scheduleQuickRetry() {
        guard !isQuickRetrying else { return }
        isQuickRetrying = true
        
        // Retry fetch after 3 seconds for fast startup responsiveness
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { [weak self] in
            guard let self = self else { return }
            if self.isQuickRetrying {
                self.isQuickRetrying = false
                self.fetchQuota()
            }
        }
    }
    
    func makeProgressBar(remainingPercent: Double?) -> String {
        let rem = remainingPercent ?? 100.0
        let usedPercent = max(0.0, min(100.0, 100.0 - rem))
        let filledCount = Int(round(usedPercent / 10.0))
        let emptyCount = 10 - filledCount
        let bar = String(repeating: "■", count: filledCount) + String(repeating: "□", count: emptyCount)
        return "  └─ [\(bar)] (Used: \(Int(round(usedPercent)))%)"
    }
    
    func updateUI(with quota: QuotaData) {
        if quota.status == "Error" {
            updateUIWithError(quota.error_message ?? "Internal scraper error")
            return
        }
        
        // 1. Status Bar Title
        let geminiWeeklyPct = quota.gemini_weekly_percentage ?? 0.0
        if let button = statusItem.button {
            if quota.status == "Initializing" {
                button.title = "AG: --%"
            } else {
                button.title = String(format: "AG: %.0f%%", geminiWeeklyPct)
            }
        }
        
        // 2. Gemini Quota Items
        let geminiWeeklyRem = quota.gemini_weekly_remaining ?? "--% remaining"
        let geminiWeeklyRef = quota.gemini_weekly_refresh ?? "--"
        geminiWeeklyMenuItem.title = "Weekly: \(geminiWeeklyRem) (Refreshes in \(geminiWeeklyRef))"
        geminiWeeklyBarMenuItem.title = makeProgressBar(remainingPercent: quota.gemini_weekly_percentage)
        
        let geminiFiveHourRem = quota.gemini_five_hour_remaining ?? "--% remaining"
        let geminiFiveHourRef = quota.gemini_five_hour_refresh ?? "--"
        geminiFiveHourMenuItem.title = "5-Hour: \(geminiFiveHourRem) (Refreshes in \(geminiFiveHourRef))"
        geminiFiveHourBarMenuItem.title = makeProgressBar(remainingPercent: quota.gemini_five_hour_percentage)
        
        // 3. Claude/GPT Quota Items
        let claudeWeeklyRem = quota.claude_weekly_remaining ?? "--% remaining"
        let claudeWeeklyRef = quota.claude_weekly_refresh ?? "--"
        claudeWeeklyMenuItem.title = "Weekly: \(claudeWeeklyRem) (Refreshes in \(claudeWeeklyRef))"
        claudeWeeklyBarMenuItem.title = makeProgressBar(remainingPercent: quota.claude_weekly_percentage)
        
        let claudeFiveHourRem = quota.claude_five_hour_remaining ?? "--% remaining"
        let claudeFiveHourRef = quota.claude_five_hour_refresh ?? "--"
        claudeFiveHourMenuItem.title = "5-Hour: \(claudeFiveHourRem) (Refreshes in \(claudeFiveHourRef))"
        claudeFiveHourBarMenuItem.title = makeProgressBar(remainingPercent: quota.claude_five_hour_percentage)
        
        // 4. Last Update Time
        if let lastUpdatedTime = quota.last_updated, lastUpdatedTime > 0 {
            let date = Date(timeIntervalSince1970: TimeInterval(lastUpdatedTime))
            let formatter = DateFormatter()
            formatter.dateFormat = "hh:mm:ss a"
            updatedMenuItem.title = "Last Update: \(formatter.string(from: date))"
        } else {
            updatedMenuItem.title = "Last Update: Initializing..."
        }
    }
    
    func updateUIWithError(_ message: String) {
        if let button = statusItem.button {
            button.title = "AG: ⚠️"
        }
        
        geminiWeeklyMenuItem.title = "Weekly: Offline"
        geminiWeeklyBarMenuItem.title = "  └─ [----------] (Offline)"
        geminiFiveHourMenuItem.title = "5-Hour: Offline"
        geminiFiveHourBarMenuItem.title = "  └─ [----------] (Offline)"
        
        claudeWeeklyMenuItem.title = "Weekly: Offline"
        claudeWeeklyBarMenuItem.title = "  └─ [----------] (Offline)"
        claudeFiveHourMenuItem.title = "5-Hour: Offline"
        claudeFiveHourBarMenuItem.title = "  └─ [----------] (Offline)"
        
        updatedMenuItem.title = "Error: \(message)"
    }
    
    // -- Launch at Login Helper --
    var launchAgentURL: URL {
        let libraryURL = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask).first!
        return libraryURL.appendingPathComponent("LaunchAgents/com.taewoong.AntigravityMonitor.plist")
    }
    
    func isLaunchAtLoginEnabled() -> Bool {
        return FileManager.default.fileExists(atPath: launchAgentURL.path)
    }
    
    func setLaunchAtLogin(enabled: Bool) {
        let fileManager = FileManager.default
        let agentURL = launchAgentURL
        
        if enabled {
            let appPath = Bundle.main.bundlePath
            let plistContent: [String: Any] = [
                "Label": "com.taewoong.AntigravityMonitor",
                "ProgramArguments": ["/usr/bin/open", appPath],
                "RunAtLoad": true,
                "KeepAlive": false
            ]
            
            let plistData = try? PropertyListSerialization.data(fromPropertyList: plistContent, format: .xml, options: 0)
            
            let agentFolder = agentURL.deletingLastPathComponent()
            if !fileManager.fileExists(atPath: agentFolder.path) {
                try? fileManager.createDirectory(at: agentFolder, withIntermediateDirectories: true, attributes: nil)
            }
            
            do {
                try plistData?.write(to: agentURL)
                print("Successfully enabled Launch at Login by creating plist.")
            } catch {
                print("Failed to write Launch at Login plist: \(error)")
            }
        } else {
            if fileManager.fileExists(atPath: agentURL.path) {
                do {
                    try fileManager.removeItem(at: agentURL)
                    print("Successfully disabled Launch at Login by removing plist.")
                } catch {
                    print("Failed to remove Launch at Login plist: \(error)")
                }
            }
        }
    }
    
    @objc func toggleLaunchAtLogin() {
        let currentStatus = isLaunchAtLoginEnabled()
        let newStatus = !currentStatus
        setLaunchAtLogin(enabled: newStatus)
        launchAtLoginMenuItem.state = newStatus ? .on : .off
    }
}

// macOS Application Lifecycle Entrypoint
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
