# Validation — 11 September 2026

## Completed

- Built and executed the portable Windows x64 app on Windows 11 (build 26200), using Python 3.12.14, PySide6 Essentials 6.11.2, and PyInstaller 6.22.2.
- **22 automated tests passed**. Coverage includes real loopback HTTP responses, exact queued-file access, host validation, unknown/traversal paths, HEAD, supported/invalid byte ranges, empty and Unicode files, changed/deleted files, ZIP contents and duplicate names, temporary-file closure, one-ZIP concurrency limit, simultaneous downloads, queue updates, physical-adapter preference, occupied-port fallback, restart/token invalidation, shutdown of incomplete HTTP requests, and cancellation of a stalled 64 MB download.
- Offscreen GUI test exercises a local-file drop event, automatic startup, QR PNG display, stop/restart, clear, close, and non-overlapping QR/address layout at the minimum window size.
- Headless Microsoft Edge tested the phone page at widths **360, 390, 768, and 1280 pixels**. No horizontal overflow; sticky Download All remained visible. Single/multiple-file presentations and long filenames were checked. Browser clicks successfully downloaded an individual file and `LocalDrop-files.zip`.
- Desktop previews at default/minimum size and the 390-pixel phone page were visually inspected. A native Qt render from the packaged executable was also inspected.
- The **final packaged executable** passed its opt-in self-test with exit code 0: native Qt initialization, adapter discovery, queue/QR creation, HTML response, individual byte verification, ZIP content verification, and clear/shutdown. One available adapter was discovered on the host.

## Packaging fix

An initial portable build failed to import QtCore because the packaging environment's PATH supplied an incompatible `icuuc.dll` from another tool. Removing that DLL confirmed the cause. `build.py` now builds with an isolated DLL search path; the clean rebuild passed the packaged test without manual file edits. The final deliverable is that clean rebuild.

## Not yet verified

- A physical phone camera scan and real PC-to-phone Wi-Fi transfer. Browser tests used a local loopback address and desktop Edge at mobile widths; they do not establish phone reachability, mobile Chrome/Edge behavior on every OS, firewall permission, or router isolation.
- Manual dragging from Windows Explorer and native file-picker interaction. The GUI's drop handler and queued-file flow were exercised programmatically.
- Clean-machine installation, Windows versions other than the Windows 11 host, ARM systems, high-DPI display combinations, files/ZIPs larger than 4 GB, sustained throughput, disk-full behavior under a real exhausted disk, or forced process termination during ZIP creation.
- The portable executable is unsigned. No firewall settings were changed. All test servers were stopped.

## Quick check on your network

Extract the Windows ZIP, open LocalDrop.exe, add a small file, and scan the QR with a phone on the same trusted network. If prompted by Windows, allow Private-network access. Download the file and compare it, then try two files with Download All. Stop Server and confirm the old link no longer opens. Use the in-app Connection help if the phone cannot connect.
