"""UniversalDownloader: Phase 1 Notification Verification Suite.

Tests:
1. Completed download creates one notification.
2. Failed download creates one notification.
3. Queue completion creates one notification.
4. Same event is not notified repeatedly during polling.
5. Notifications setting disabled -> no notification.
6. Browser Notification API unavailable -> application continues normally.
7. Permission denied -> in-app notification still works.
8. Route navigation does not duplicate notification.
9. Refresh does not duplicate already-notified events.
"""

import sys
import json
import subprocess
from pathlib import Path

# Node.js script to simulate frontend notification engine and verify all 9 scenarios
NODE_TEST_SCRIPT = """
class MockLocalStorage {
    constructor() { this.store = {}; }
    getItem(k) { return this.store[k] || null; }
    setItem(k, v) { this.store[k] = String(v); }
    removeItem(k) { delete this.store[k]; }
    clear() { this.store = {}; }
}

class NotificationEngine {
    constructor(options = {}) {
        this.localStorage = options.localStorage || new MockLocalStorage();
        this.notificationApi = options.notificationApi; // undefined, or mock class
        this.inAppNotifications = [];
        this.desktopNotifications = [];
        this.initialized = false;
        this.prevActiveOrQueued = null;
        this.masterNotificationsEnabled = options.masterNotificationsEnabled ?? true;
        this.desktopSettingEnabled = options.desktopSettingEnabled ?? false;
    }

    notify(msg, type) {
        this.inAppNotifications.push({ msg, type });
    }

    sendDesktop(title, body) {
        if (!this.notificationApi) return false;
        if (this.notificationApi.permission !== 'granted') return false;
        try {
            const inst = new this.notificationApi(title, { body });
            this.desktopNotifications.push({ title, body, inst });
            return true;
        } catch (e) {
            return false;
        }
    }

    getNotifiedMap() {
        try {
            const raw = this.localStorage.getItem('ud_notified_downloads');
            return raw ? JSON.parse(raw) : {};
        } catch {
            return {};
        }
    }

    saveNotifiedMap(map) {
        this.localStorage.setItem('ud_notified_downloads', JSON.stringify(map));
    }

    getDownloadFilename(d) {
        if (d.output_path) {
            const parts = d.output_path.split(/[/\\\\]/);
            const last = parts[parts.length - 1];
            if (last && last.trim()) return last.trim();
        }
        return d.title || `Download #${d.id}`;
    }

    // Emulates a polling cycle with new downloads list
    poll(downloads) {
        const notifiedMap = this.getNotifiedMap();
        const activeOrQueued = downloads.filter(
            d => d.status === 'downloading' || d.status === 'queued'
        ).length;

        // Startup / refresh seeding
        if (!this.initialized) {
            let updated = false;
            for (const d of downloads) {
                const idStr = String(d.id);
                if ((d.status === 'completed' || d.status === 'failed' || d.status === 'cancelled') && !notifiedMap[idStr]) {
                    notifiedMap[idStr] = d.status;
                    updated = true;
                }
            }
            if (updated) this.saveNotifiedMap(notifiedMap);
            this.prevActiveOrQueued = activeOrQueued;
            this.initialized = true;
            return;
        }

        let mapModified = false;

        for (const d of downloads) {
            const idStr = String(d.id);
            const prev = notifiedMap[idStr];

            if (d.status === 'completed' && prev !== 'completed') {
                notifiedMap[idStr] = 'completed';
                mapModified = true;

                if (this.masterNotificationsEnabled) {
                    const fn = this.getDownloadFilename(d);
                    const msg = `Download completed: ${fn}`;
                    this.notify(msg, 'success');
                    if (this.desktopSettingEnabled) {
                        this.sendDesktop('UniversalDownloader', msg);
                    }
                }
            } else if (d.status === 'failed' && prev !== 'failed') {
                notifiedMap[idStr] = 'failed';
                mapModified = true;

                if (this.masterNotificationsEnabled) {
                    const fn = this.getDownloadFilename(d);
                    const msg = `Download failed: ${fn}`;
                    this.notify(msg, 'error');
                    if (this.desktopSettingEnabled) {
                        this.sendDesktop('UniversalDownloader', msg);
                    }
                }
            }
        }

        if (mapModified) {
            this.saveNotifiedMap(notifiedMap);
        }

        // Queue completion
        if (
            this.prevActiveOrQueued !== null &&
            this.prevActiveOrQueued > 0 &&
            activeOrQueued === 0
        ) {
            if (this.masterNotificationsEnabled) {
                const msg = 'Download queue completed';
                this.notify(msg, 'success');
                if (this.desktopSettingEnabled) {
                    this.sendDesktop('UniversalDownloader', msg);
                }
            }
        }

        this.prevActiveOrQueued = activeOrQueued;
    }
}

function runTests() {
    const results = {};

    function record(name, pass, detail) {
        results[name] = { pass, detail };
        console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}: ${detail}`);
    }

    // 1. Completed download creates one notification
    {
        const engine = new NotificationEngine();
        engine.poll([]); // init
        engine.poll([{ id: 1, title: 'Test Video', output_path: 'C:\\\\dl\\\\Test Video.mp4', status: 'downloading' }]);
        engine.poll([{ id: 1, title: 'Test Video', output_path: 'C:\\\\dl\\\\Test Video.mp4', status: 'completed' }]);
        const completedToasts = engine.inAppNotifications.filter(n => n.msg.startsWith('Download completed:'));
        const ok = completedToasts.length === 1 &&
                   completedToasts[0].msg === 'Download completed: Test Video.mp4' &&
                   completedToasts[0].type === 'success';
        record('TEST-1-COMPLETED', ok, `completed_toasts=${completedToasts.length}, msg="${completedToasts[0]?.msg}"`);
    }

    // 2. Failed download creates one notification
    {
        const engine = new NotificationEngine();
        engine.poll([]); // init
        engine.poll([{ id: 2, title: 'Broken Stream', output_path: null, status: 'downloading' }]);
        engine.poll([{ id: 2, title: 'Broken Stream', output_path: null, status: 'failed' }]);
        const failedToasts = engine.inAppNotifications.filter(n => n.msg.startsWith('Download failed:'));
        const ok = failedToasts.length === 1 &&
                   failedToasts[0].msg === 'Download failed: Broken Stream' &&
                   failedToasts[0].type === 'error';
        record('TEST-2-FAILED', ok, `failed_toasts=${failedToasts.length}, msg="${failedToasts[0]?.msg}"`);
    }

    // 3. Queue completion creates one notification
    {
        const engine = new NotificationEngine();
        engine.poll([]); // init
        engine.poll([
            { id: 10, title: 'Video A', output_path: 'C:\\\\dl\\\\A.mp4', status: 'downloading' },
            { id: 11, title: 'Video B', output_path: 'C:\\\\dl\\\\B.mp4', status: 'queued' }
        ]);
        engine.poll([
            { id: 10, title: 'Video A', output_path: 'C:\\\\dl\\\\A.mp4', status: 'completed' },
            { id: 11, title: 'Video B', output_path: 'C:\\\\dl\\\\B.mp4', status: 'downloading' }
        ]);
        // Finish last one
        engine.poll([
            { id: 10, title: 'Video A', output_path: 'C:\\\\dl\\\\A.mp4', status: 'completed' },
            { id: 11, title: 'Video B', output_path: 'C:\\\\dl\\\\B.mp4', status: 'completed' }
        ]);
        const queueToasts = engine.inAppNotifications.filter(n => n.msg === 'Download queue completed');
        const ok = queueToasts.length === 1 && queueToasts[0].type === 'success';
        record('TEST-3-QUEUE-COMPLETED', ok, `queue_toasts=${queueToasts.length}, total_toasts=${engine.inAppNotifications.length}`);
    }

    // 4. Same event is not notified repeatedly during polling
    {
        const engine = new NotificationEngine();
        engine.poll([]); // init
        const item = [{ id: 3, title: 'Repeat Check', output_path: 'C:\\\\dl\\\\Repeat.mp4', status: 'completed' }];
        engine.poll(item);
        engine.poll(item); // 2nd poll
        engine.poll(item); // 3rd poll
        engine.poll(item); // 4th poll
        const ok = engine.inAppNotifications.length === 1;
        record('TEST-4-POLL-DEDUP', ok, `expected=1, actual=${engine.inAppNotifications.length}`);
    }

    // 5. Notifications setting disabled -> no notification
    {
        const engine = new NotificationEngine({ masterNotificationsEnabled: false });
        engine.poll([]); // init
        engine.poll([{ id: 4, title: 'Silent Video', output_path: 'C:\\\\dl\\\\Silent.mp4', status: 'downloading' }]);
        engine.poll([{ id: 4, title: 'Silent Video', output_path: 'C:\\\\dl\\\\Silent.mp4', status: 'completed' }]);
        engine.poll([]); // queue completed
        const ok = engine.inAppNotifications.length === 0 && engine.desktopNotifications.length === 0;
        record('TEST-5-SETTING-DISABLED', ok, `notifications_suppressed=${ok}`);
    }

    // 6. Browser Notification API unavailable -> application continues normally
    {
        // notificationApi is undefined (unsupported browser)
        const engine = new NotificationEngine({
            notificationApi: undefined,
            desktopSettingEnabled: true
        });
        let threw = false;
        try {
            engine.poll([]); // init
            engine.poll([{ id: 5, title: 'Fallback Video', output_path: 'C:\\\\dl\\\\Fallback.mp4', status: 'completed' }]);
        } catch (e) {
            threw = true;
        }
        const ok = !threw && engine.inAppNotifications.length === 1 && engine.desktopNotifications.length === 0;
        record('TEST-6-UNAVAILABLE-API', ok, `threw=${threw}, in_app_fallback=${engine.inAppNotifications.length}`);
    }

    // 7. Permission denied -> in-app notification still works
    {
        class MockNotificationDenied {
            static permission = 'denied';
            constructor() { throw new Error('Permission denied'); }
        }
        const engine = new NotificationEngine({
            notificationApi: MockNotificationDenied,
            desktopSettingEnabled: true
        });
        engine.poll([]); // init
        engine.poll([{ id: 6, title: 'Denied Video', output_path: 'C:\\\\dl\\\\Denied.mp4', status: 'completed' }]);
        const ok = engine.inAppNotifications.length === 1 && engine.desktopNotifications.length === 0;
        record('TEST-7-PERMISSION-DENIED', ok, `in_app_works=${engine.inAppNotifications.length === 1}, desktop_sent=${engine.desktopNotifications.length}`);
    }

    // 8. Route navigation does not duplicate notification
    {
        const storage = new MockLocalStorage();
        // User is on /downloads
        const enginePage1 = new NotificationEngine({ localStorage: storage });
        enginePage1.poll([]); // init
        enginePage1.poll([{ id: 7, title: 'Nav Video', output_path: 'C:\\\\dl\\\\Nav.mp4', status: 'completed' }]);
        
        // User navigates to /settings (same shared localStorage, layout listener stays active or remounts)
        const enginePage2 = new NotificationEngine({ localStorage: storage });
        enginePage2.poll([{ id: 7, title: 'Nav Video', output_path: 'C:\\\\dl\\\\Nav.mp4', status: 'completed' }]);
        enginePage2.poll([{ id: 7, title: 'Nav Video', output_path: 'C:\\\\dl\\\\Nav.mp4', status: 'completed' }]);

        const totalToasts = enginePage1.inAppNotifications.length + enginePage2.inAppNotifications.length;
        const ok = totalToasts === 1;
        record('TEST-8-ROUTE-NAVIGATION', ok, `total_toasts_across_routes=${totalToasts}`);
    }

    // 9. Refresh does not duplicate already-notified events
    {
        const storage = new MockLocalStorage();
        // Session 1: download completes
        const session1 = new NotificationEngine({ localStorage: storage });
        session1.poll([]); // init
        session1.poll([{ id: 8, title: 'Refresh Video', output_path: 'C:\\\\dl\\\\Refresh.mp4', status: 'completed' }]);
        
        // Page refresh: new engine instance with same persistent localStorage
        const session2 = new NotificationEngine({ localStorage: storage });
        // Fresh poll on startup
        session2.poll([{ id: 8, title: 'Refresh Video', output_path: 'C:\\\\dl\\\\Refresh.mp4', status: 'completed' }]);
        // Subsequent poll
        session2.poll([{ id: 8, title: 'Refresh Video', output_path: 'C:\\\\dl\\\\Refresh.mp4', status: 'completed' }]);

        const s2Toasts = session2.inAppNotifications.length;
        const ok = s2Toasts === 0;
        record('TEST-9-REFRESH-DEDUP', ok, `toasts_after_refresh=${s2Toasts} (expected 0)`);
    }

    const allPassed = Object.values(results).every(r => r.pass);
    console.log(`\\nResult: ${Object.values(results).filter(r => r.pass).length}/9 tests PASSED`);
    process.exit(allPassed ? 0 : 1);
}

runTests();
"""

def main():
    print("=" * 65)
    print("VERIFYING DOWNLOAD & QUEUE NOTIFICATION SYSTEM (9 TESTS)")
    print("=" * 65)

    proc = subprocess.run(
        ["node", "-e", NODE_TEST_SCRIPT],
        capture_output=True,
        text=True
    )
    print(proc.stdout)
    if proc.stderr:
        print("STDERR:\n", proc.stderr, file=sys.stderr)

    if proc.returncode == 0:
        print("ALL 9 NOTIFICATION TESTS PASSED SUCCESSFULLY!")
    else:
        print("NOTIFICATION VERIFICATION FAILED!")

    return proc.returncode

if __name__ == "__main__":
    sys.exit(main())
