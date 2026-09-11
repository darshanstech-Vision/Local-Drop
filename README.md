# LocalDrop

A Windows desktop app for sending queued files to a phone over your local network. Deep-grey desktop and phone interfaces, multi-file drag/drop, QR sharing, individual downloads, and a single ZIP for Download All. No account, cloud service, or phone installation.

## Run the portable Windows build

Extract **LocalDrop-Windows-x64.zip**, open the extracted LocalDrop folder, and double-click **LocalDrop.exe**. Keep `_internal` beside the executable. No Python installation is needed. This is an unsigned, 64-bit Windows build; Windows may show a publisher/reputation prompt. No administrator privileges are needed to run the app.

1. Connect the phone and PC to the same trusted network.
2. Check the Network selector. Physical Wi-Fi/Ethernet adapters are preferred; other adapters remain available for manual selection. Refresh after changing networks.
3. Drop individual files into the large zone or choose several in the file picker. Sharing starts automatically and the QR appears after a successful bind.
4. Scan with your phone camera and open the URL in Chrome or Edge. Tap an individual green Download button or Download All for one ZIP.
5. Keep the app open until downloads finish. Stop Server cancels transfers and invalidates the session URL. Clear Queue also empties the queue; neither deletes original files. Starting again creates a new QR.

Adding more files to a running session preserves its link. Refresh the phone page to see the updated list. An already-started ZIP uses its original queue snapshot. Duplicate paths are ignored; duplicate filenames get distinct names inside the ZIP.

## Connection and firewall help

The Online indicator means the selected local IP/port is listening. It does **not** establish that the phone can reach the PC. The actual port is shown beside the QR: LocalDrop tries 8000 through 8099, advancing past occupied or Windows-reserved ports. It binds only the selected IPv4 address, not every interface. Network loss stops the server when the address disappears; reconnect, Refresh, and start again.

If Windows asks about network access, allow LocalDrop on your trusted **Private** network only. Source runs may appear as Python. If you previously denied access, use Windows Security → Firewall & network protection → Allow an app through firewall. An administrator can create a narrower inbound TCP rule scoped to the executable, displayed port, selected local IP, and Local Subnet. Remove unneeded rules later. The app never changes firewall rules, requests elevation, or turns off the firewall.

Guest Wi-Fi and router AP/client isolation can block communication between devices even if the Wi-Fi name matches. School/hotel networks may have similar restrictions. Try a trusted non-guest network or a phone hotspot with the PC connected. A timeout alone cannot diagnose isolation: an incorrect adapter, firewall, VPN, or routing problem can look the same. First verify the displayed IP/port and that the PC remains awake. Manual network selection is available while the server is stopped.

## Privacy, performance, and limits

- Files stay local; the app has no external runtime services, telemetry, scripts, fonts, or QR service. Installing dependencies is the only step that needs internet access.
- A cryptographically random 192-bit session token is part of the URL. Only explicit opaque file IDs in the queue are served. No directory browsing or URL-to-filesystem path mapping. HTTP Host validation prevents arbitrary hostnames from reaching a session. Responses disable caching and referrer disclosure.
- Anyone who obtains a live link on a reachable network can download the queue. HTTP is unencrypted, so use a trusted LAN; do not expose this server through port forwarding. This is a personal local transfer tool, not a public production web server.
- Downloads run outside the GUI thread. The server bounds concurrent client handlers to 12. One ZIP is allowed at a time; another ZIP request gets a retry message.
- ZIPs are uncompressed for low CPU use and streamed from temporary disk, using roughly the total queued size in free temporary space. They are deleted on completion, disconnect, or normal shutdown. Large ZIPs need preparation time; lack of disk space is reported to the phone. ZIP64 is enabled for large archives.
- Individual downloads support a single HTTP byte range. ZIP downloads do not resume. Browsers choose the save location and may show their usual download prompts.
- Queued files are referenced, not copied. Moved/deleted/changed files are rejected at download time. Do not modify a file during a transfer: the app does not lock an immutable snapshot. Original names, sizes, and modification times are checked against the opened file.
- The adapter query uses Windows' read-only physical-adapter inventory with an eight-second timeout; if unavailable, name-based heuristics are used. Adapter selection is not a conclusive reachability test. IPv6-only networks are not supported.
- Folders must be zipped before adding. Closing normally cancels transfers and waits for resources to close in a background worker. Files already saved on the phone are unaffected.

## Run and develop from source

Install Python 3.12 or newer (64-bit) from [python.org](https://www.python.org/downloads/windows/), including its `py` launcher. Double-click **Setup.cmd**, then **Run.cmd**. Alternatively, in this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

For tests and packaging, run **Build.cmd**, or:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe build.py
```

The app is split into `localdrop/app.py` (Qt GUI and serialized background actions), `server.py` (HTTP, queue metadata, ZIPs, lifecycle), and `network.py` (adapter discovery). Tests exercise real loopback HTTP connections and an offscreen Qt GUI. Runtime dependencies are pinned in requirements.txt; the build/test versions are in requirements-dev.txt. The build helper isolates the DLL search path so unrelated installed tools cannot supply incompatible libraries.

To check a packaged build without showing a window, run `LocalDrop.exe --self-test C:\path\to\test-output`. This opt-in mode writes a sample file, screenshot, and `result.json` to that directory, tests transfers on loopback, then exits. It never exposes the test file to the LAN.

## Official implementation references

- [Qt drag/drop](https://doc.qt.io/qtforpython-6/overviews/qtgui-dnd.html) and [Qt threading](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html): GUI events remain on the GUI thread; worker results arrive through Qt signals.
- [Python HTTP server](https://docs.python.org/3/library/http.server.html): custom BaseHTTPRequestHandler routes rather than SimpleHTTPRequestHandler filesystem serving; threaded handling with bounded connections.
- [qrcode](https://pypi.org/project/qrcode/): local PNG generation using the pure PNG renderer.
- [psutil network API](https://psutil.io/api/) and [Get-NetAdapter](https://learn.microsoft.com/en-us/powershell/module/netadapter/get-netadapter): interface addresses, state, and Windows physical-adapter inventory.
- [PyInstaller packaging](https://www.pyinstaller.org/en/stable/usage.html): portable one-folder Windows packaging.

See VALIDATION.md for the actual checks performed and remaining device-validation limits.
