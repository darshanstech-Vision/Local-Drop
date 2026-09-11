"""Opt-in packaged smoke test: LocalDrop.exe --self-test <output-directory>."""
import io
import json
from pathlib import Path
import time
import traceback
from urllib.request import urlopen
import zipfile

from PySide6.QtWidgets import QApplication
from .app import STYLE, Window


def run(directory):
    output = Path(directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    # No visible window. Native Qt plugins and fonts are still initialized.
    def settle():
        deadline = time.monotonic() + 20
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        app.processEvents()
        if window.busy:
            raise RuntimeError("GUI action timed out.")
    result = {}
    try:
        settle()
        result["adapters_found"] = window.adapters.count()
        window.adapters.clear()
        window.adapters.addItem("Self-test loopback", "127.0.0.1")
        sample = output / "sample.txt"
        sample.write_text("LocalDrop packaged test", encoding="utf-8")
        window.add_files([str(sample)])
        settle()
        assert window.service.server and window.url
        assert not window.qr.pixmap().isNull()
        with urlopen(window.url, timeout=5) as response:
            assert b"Your file is ready." in response.read()
        with urlopen(window.url + "file/" + window.files[0].id, timeout=5) as response:
            assert response.read() == sample.read_bytes()
        with urlopen(window.url + "all.zip", timeout=5) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as bundle:
                assert bundle.read("sample.txt") == sample.read_bytes()
        window.grab().save(str(output / "desktop.png"))
        window.clear()
        settle()
        assert not window.files and not window.service.server
        result.update(passed=True, checks=["native Qt initialization", "adapter discovery", "queue and QR",
                      "phone HTML", "individual file bytes", "ZIP contents", "clear and shutdown"])
    except Exception:
        result.update(passed=False, error=traceback.format_exc())
    finally:
        window.close()
        settle()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result.get("passed") else 1
