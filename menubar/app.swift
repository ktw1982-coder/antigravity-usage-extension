import AppKit
import Foundation
import UserNotifications

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
    let error_type: String?
    let cli_found: Bool?
    let cli_path: String?
}

class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
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
    var preferencesMenuItem: NSMenuItem!
    var dashboardMenuItem: NSMenuItem!
    
    // Preferences Window
    var preferencesWindow: NSWindow?
    var enableNotificationsButton: NSButton?
    
    // Reference to the backend python process
    var pythonProcess: Process?
    
    // Flag to control quick retries during initialization or error states
    var isQuickRetrying = false
    
    // Notification tracking flags to prevent duplicate alerts
    var notified80 = false
    var notified90 = false
    var enableNotifications = true
    
    // Status Bar Preferences
    var selectedMetricIndex: Int = 0 // 0: Gemini Weekly, 1: Gemini 5-Hour, 2: Claude Weekly, 3: Claude 5-Hour, 4: Most Critical
    var selectedDisplayModeIndex: Int = 0 // 0: Remaining %, 1: Used %
    var metricPopUp: NSPopUpButton?
    var displayModePopUp: NSPopUpButton?
    var lastFetchedQuota: QuotaData?
    
    // Timer
    var pollingTimer: Timer?
    var currentInterval: TimeInterval = 60.0
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        setupNotifications()
        startBackendServer()
        
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "AG: --%"
        }
        
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
        
        // -- Last Update & Dashboard --
        updatedMenuItem = NSMenuItem(title: "Last Update: --", action: nil, keyEquivalent: "")
        updatedMenuItem.isEnabled = false
        menu.addItem(updatedMenuItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Open Web Analytics Dashboard
        dashboardMenuItem = NSMenuItem(title: "Open Dashboard 📊", action: #selector(openDashboard), keyEquivalent: "d")
        dashboardMenuItem.target = self
        menu.addItem(dashboardMenuItem)
        
        // Preferences Window Item
        preferencesMenuItem = NSMenuItem(title: "Preferences...", action: #selector(openPreferences), keyEquivalent: ",")
        preferencesMenuItem.target = self
        menu.addItem(preferencesMenuItem)
        
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
        
        loadPreferences()
        restartTimer()
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.fetchQuota()
        }
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        stopBackendServer()
    }
    
    @objc func openDashboard() {
        if let url = URL(string: "http://localhost:8484/dashboard") {
            NSWorkspace.shared.open(url)
        }
    }
    
    // -- Notifications Setup --
    func setupNotifications() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error = error {
                print("Notification permission error: \(error)")
            }
        }
    }
    
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
    
    func sendQuotaNotification(title: String, body: String) {
        guard enableNotifications else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Failed to deliver notification: \(error)")
            }
        }
    }
    
    func checkNotifications(quota: QuotaData) {
        let geminiPct = quota.gemini_weekly_percentage ?? 0.0
        let claudePct = quota.claude_weekly_percentage ?? 0.0
        let maxPct = max(geminiPct, claudePct)
        
        if maxPct >= 90.0 {
            if !notified90 {
                sendQuotaNotification(
                    title: "⚠️ High Quota Usage Alert (90%+)",
                    body: "Your Antigravity model quota usage has reached \(Int(maxPct))%! Consider pacing your requests."
                )
                notified90 = true
                notified80 = true
            }
        } else if maxPct >= 80.0 {
            if !notified80 {
                sendQuotaNotification(
                    title: "🔔 Quota Warning (80%+)",
                    body: "Your Antigravity quota usage is now at \(Int(maxPct))%."
                )
                notified80 = true
            }
        } else {
            notified80 = false
            notified90 = false
        }
    }
    
    // -- Preferences Window --
    @objc func openPreferences() {
        if let window = preferencesWindow {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 260),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = "Antigravity Monitor Preferences"
        window.isReleasedWhenClosed = false
        
        let contentView = NSView(frame: window.contentRect(forFrameRect: window.frame))
        
        let titleLabel = NSTextField(labelWithString: "Antigravity Monitor Settings")
        titleLabel.font = NSFont.boldSystemFont(ofSize: 14)
        titleLabel.frame = NSRect(x: 20, y: 220, width: 340, height: 20)
        contentView.addSubview(titleLabel)
        
        // Push Notifications Checkbox
        let notifyBtn = NSButton(checkboxWithTitle: "Enable Push Notifications (at 80% & 90% quota)", target: self, action: #selector(toggleNotificationsCheckbox(_:)))
        notifyBtn.frame = NSRect(x: 20, y: 185, width: 340, height: 25)
        notifyBtn.state = enableNotifications ? .on : .off
        self.enableNotificationsButton = notifyBtn
        contentView.addSubview(notifyBtn)
        
        // Status Bar Display Metric Selection
        let metricLabel = NSTextField(labelWithString: "Status Bar Display Metric:")
        metricLabel.font = NSFont.systemFont(ofSize: 12)
        metricLabel.frame = NSRect(x: 20, y: 145, width: 160, height: 20)
        contentView.addSubview(metricLabel)
        
        let mPopUp = NSPopUpButton(frame: NSRect(x: 180, y: 142, width: 180, height: 25), pullsDown: false)
        mPopUp.addItems(withTitles: [
            "Gemini Weekly",
            "Gemini 5-Hour",
            "Claude Weekly",
            "Claude 5-Hour",
            "Most Critical (Max Used)"
        ])
        mPopUp.selectItem(at: selectedMetricIndex)
        mPopUp.target = self
        mPopUp.action = #selector(metricPopUpChanged(_:))
        self.metricPopUp = mPopUp
        contentView.addSubview(mPopUp)
        
        // Display Value Type Selection (Remaining vs Used)
        let modeLabel = NSTextField(labelWithString: "Display Value Type:")
        modeLabel.font = NSFont.systemFont(ofSize: 12)
        modeLabel.frame = NSRect(x: 20, y: 105, width: 160, height: 20)
        contentView.addSubview(modeLabel)
        
        let dPopUp = NSPopUpButton(frame: NSRect(x: 180, y: 102, width: 180, height: 25), pullsDown: false)
        dPopUp.addItems(withTitles: [
            "Remaining Quota % (남은 양)",
            "Used Quota % (사용한 양)"
        ])
        dPopUp.selectItem(at: selectedDisplayModeIndex)
        dPopUp.target = self
        dPopUp.action = #selector(displayModePopUpChanged(_:))
        self.displayModePopUp = dPopUp
        contentView.addSubview(dPopUp)
        
        let infoLabel = NSTextField(labelWithString: "Customize status bar item metric and calculation mode.")
        infoLabel.font = NSFont.systemFont(ofSize: 11)
        infoLabel.textColor = .secondaryLabelColor
        infoLabel.frame = NSRect(x: 20, y: 65, width: 340, height: 25)
        contentView.addSubview(infoLabel)
        
        let closeBtn = NSButton(title: "Save & Close", target: self, action: #selector(closePreferences))
        closeBtn.frame = NSRect(x: 250, y: 18, width: 110, height: 32)
        closeBtn.bezelStyle = .rounded
        contentView.addSubview(closeBtn)
        
        window.contentView = contentView
        self.preferencesWindow = window
        
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    
    @objc func toggleNotificationsCheckbox(_ sender: NSButton) {
        enableNotifications = (sender.state == .on)
        UserDefaults.standard.set(enableNotifications, forKey: "enableNotifications")
    }
    
    @objc func metricPopUpChanged(_ sender: NSPopUpButton) {
        selectedMetricIndex = sender.indexOfSelectedItem
        UserDefaults.standard.set(selectedMetricIndex, forKey: "selectedMetricIndex")
        if let quota = lastFetchedQuota {
            updateUI(with: quota)
        }
    }
    
    @objc func displayModePopUpChanged(_ sender: NSPopUpButton) {
        selectedDisplayModeIndex = sender.indexOfSelectedItem
        UserDefaults.standard.set(selectedDisplayModeIndex, forKey: "selectedDisplayModeIndex")
        if let quota = lastFetchedQuota {
            updateUI(with: quota)
        }
    }
    
    @objc func closePreferences() {
        preferencesWindow?.close()
    }
    
    func loadPreferences() {
        if UserDefaults.standard.object(forKey: "enableNotifications") != nil {
            enableNotifications = UserDefaults.standard.bool(forKey: "enableNotifications")
        }
        if UserDefaults.standard.object(forKey: "selectedMetricIndex") != nil {
            selectedMetricIndex = UserDefaults.standard.integer(forKey: "selectedMetricIndex")
        }
        if UserDefaults.standard.object(forKey: "selectedDisplayModeIndex") != nil {
            selectedDisplayModeIndex = UserDefaults.standard.integer(forKey: "selectedDisplayModeIndex")
        }
    }
    
    func formatStatusBarTitle(quota: QuotaData) -> String {
        if quota.status == "Initializing" {
            return "AG: --%"
        }
        
        let gW = quota.gemini_weekly_percentage ?? 100.0
        let g5 = quota.gemini_five_hour_percentage ?? 100.0
        let cW = quota.claude_weekly_percentage ?? 100.0
        let c5 = quota.claude_five_hour_percentage ?? 100.0
        
        var targetRemPct: Double = gW
        var metricTag: String = ""
        
        switch selectedMetricIndex {
        case 0:
            targetRemPct = gW
            metricTag = ""
        case 1:
            targetRemPct = g5
            metricTag = "G5H"
        case 2:
            targetRemPct = cW
            metricTag = "CW"
        case 3:
            targetRemPct = c5
            metricTag = "C5H"
        case 4:
            let metrics = [("GW", gW), ("G5H", g5), ("CW", cW), ("C5H", c5)]
            if let minPair = metrics.min(by: { $0.1 < $1.1 }) {
                targetRemPct = minPair.1
                metricTag = minPair.0
            }
        default:
            targetRemPct = gW
            metricTag = ""
        }
        
        let isUsedMode = (selectedDisplayModeIndex == 1)
        let displayPct: Double
        if isUsedMode {
            displayPct = max(0.0, min(100.0, 100.0 - targetRemPct))
        } else {
            displayPct = targetRemPct
        }
        
        let modeSuffix = isUsedMode ? "Used" : "Rem"
        let prefix = metricTag.isEmpty ? "AG" : "AG(\(metricTag))"
        
        return String(format: "%@: %.0f%% %@", prefix, displayPct, modeSuffix)
    }
    
    func restartTimer() {
        pollingTimer?.invalidate()
        pollingTimer = Timer.scheduledTimer(withTimeInterval: currentInterval, repeats: true) { [weak self] _ in
            self?.fetchQuota()
        }
    }
    
    func startBackendServer() {
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
                    } else if quota.status == "Error" {
                        let errType = quota.error_type ?? "UNKNOWN"
                        let msg = quota.error_message ?? "Scraper Error"
                        self.updateUIWithError("[\(errType)] \(msg)")
                        self.scheduleQuickRetry()
                    } else {
                        self.isQuickRetrying = false
                        self.updateUI(with: quota)
                        self.checkNotifications(quota: quota)
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
        lastFetchedQuota = quota
        if let button = statusItem.button {
            button.title = formatStatusBarTitle(quota: quota)
        }
        
        let geminiWeeklyRem = quota.gemini_weekly_remaining ?? "--% remaining"
        let geminiWeeklyRef = quota.gemini_weekly_refresh ?? "--"
        geminiWeeklyMenuItem.title = "Weekly: \(geminiWeeklyRem) (Refreshes in \(geminiWeeklyRef))"
        geminiWeeklyBarMenuItem.title = makeProgressBar(remainingPercent: quota.gemini_weekly_percentage)
        
        let geminiFiveHourRem = quota.gemini_five_hour_remaining ?? "--% remaining"
        let geminiFiveHourRef = quota.gemini_five_hour_refresh ?? "--"
        geminiFiveHourMenuItem.title = "5-Hour: \(geminiFiveHourRem) (Refreshes in \(geminiFiveHourRef))"
        geminiFiveHourBarMenuItem.title = makeProgressBar(remainingPercent: quota.gemini_five_hour_percentage)
        
        let claudeWeeklyRem = quota.claude_weekly_remaining ?? "--% remaining"
        let claudeWeeklyRef = quota.claude_weekly_refresh ?? "--"
        claudeWeeklyMenuItem.title = "Weekly: \(claudeWeeklyRem) (Refreshes in \(claudeWeeklyRef))"
        claudeWeeklyBarMenuItem.title = makeProgressBar(remainingPercent: quota.claude_weekly_percentage)
        
        let claudeFiveHourRem = quota.claude_five_hour_remaining ?? "--% remaining"
        let claudeFiveHourRef = quota.claude_five_hour_refresh ?? "--"
        claudeFiveHourMenuItem.title = "5-Hour: \(claudeFiveHourRem) (Refreshes in \(claudeFiveHourRef))"
        claudeFiveHourBarMenuItem.title = makeProgressBar(remainingPercent: quota.claude_five_hour_percentage)
        
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
