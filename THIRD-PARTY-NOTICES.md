# Third-party components

LocalDrop uses the following independently licensed components. Their copyrights and licenses remain with their respective authors. Available license files and package metadata from the installed distributions are included in `licenses/` in the portable package.

| Component | Version | Project / source |
| --- | --- | --- |
| Python | 3.12.14 | https://www.python.org/ |
| PySide6 Essentials / Qt | 6.11.2 | https://www.qt.io/qt-for-python / https://code.qt.io/ |
| Shiboken6 | 6.11.2 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| qrcode | 8.2 | https://github.com/lincolnloop/python-qrcode |
| PyPNG | 0.20220715.0 | https://gitlab.com/drj11/pypng |
| psutil | 7.2.2 | https://github.com/giampaolo/psutil |
| colorama | 0.4.6 | https://github.com/tartley/colorama |
| PyInstaller bootloader | 6.22.2 | https://pyinstaller.org/ |

Qt and PySide are supplied as replaceable shared libraries in the one-folder package. LocalDrop does not modify these libraries. The supplied Python source and build helper are available in the accompanying source bundle. Refer to each upstream project's license and source for redistribution terms.
