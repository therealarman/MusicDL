"""Background QThread workers for all network operations."""
import json
import time

import requests
from PyQt6.QtCore import QRunnable, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap


# ── Server readiness ───────────────────────────────────────────────────────────

class ServerWaitWorker(QThread):
    ready = pyqtSignal(bool)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url

    def run(self):
        deadline = time.time() + 15.0
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.base_url}/api/health", timeout=1)
                if r.ok:
                    self.ready.emit(True)
                    return
            except Exception:
                pass
            time.sleep(0.25)
        self.ready.emit(False)


# ── Fetch ──────────────────────────────────────────────────────────────────────

class FetchWorker(QThread):
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str, base_url: str):
        super().__init__()
        self.url = url
        self.base_url = base_url

    def run(self):
        try:
            r = requests.post(
                f"{self.base_url}/api/fetch",
                json={"url": self.url},
                timeout=45,
            )
            if r.ok:
                self.result.emit(r.json())
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                self.error.emit(str(detail))
        except Exception as exc:
            self.error.emit(str(exc))


# ── Download start ─────────────────────────────────────────────────────────────

class DownloadStartWorker(QThread):
    started = pyqtSignal(str)  # job_id
    error = pyqtSignal(str)

    def __init__(self, base_url: str, payload: dict):
        super().__init__()
        self.base_url = base_url
        self.payload = payload

    def run(self):
        try:
            r = requests.post(
                f"{self.base_url}/api/download",
                json=self.payload,
                timeout=15,
            )
            if r.ok:
                self.started.emit(r.json()["job_id"])
            else:
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    detail = r.text
                self.error.emit(str(detail))
        except Exception as exc:
            self.error.emit(str(exc))


# ── SSE progress stream ────────────────────────────────────────────────────────

class SSEWorker(QThread):
    track_update = pyqtSignal(dict)
    job_update = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    finished_sse = pyqtSignal()

    def __init__(self, base_url: str, job_id: str):
        super().__init__()
        self.base_url = base_url
        self.job_id = job_id
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        url = f"{self.base_url}/api/status/{self.job_id}"
        try:
            with requests.get(url, stream=True, timeout=(10, None)) as r:
                event_type = None
                for raw in r.iter_lines(decode_unicode=True):
                    if self._stop:
                        break
                    if raw.startswith("event:"):
                        event_type = raw[6:].strip()
                    elif raw.startswith("data:"):
                        data_str = raw[5:].strip()
                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue
                        if event_type == "track_update":
                            self.track_update.emit(data)
                        elif event_type == "job_update":
                            self.job_update.emit(data)
                        elif event_type == "log":
                            self.log_message.emit(data.get("message", ""))
                        elif event_type == "done":
                            self.finished_sse.emit()
                            return
                    elif raw == "":
                        event_type = None
        except Exception:
            pass
        self.finished_sse.emit()


# ── Cancel ─────────────────────────────────────────────────────────────────────

class CancelWorker(QThread):
    def __init__(self, base_url: str, job_id: str):
        super().__init__()
        self.base_url = base_url
        self.job_id = job_id

    def run(self):
        try:
            requests.post(f"{self.base_url}/api/cancel/{self.job_id}", timeout=5)
        except Exception:
            pass


# ── Image loading ──────────────────────────────────────────────────────────────

class ImageSignals(QObject):
    loaded = pyqtSignal(str, QPixmap)  # track_id, pixmap


class ImageLoader(QRunnable):
    def __init__(self, track_id: str, url: str):
        super().__init__()
        self.track_id = track_id
        self.url = url
        self.signals = ImageSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            r = requests.get(self.url, timeout=10)
            if r.ok and r.content:
                pix = QPixmap()
                pix.loadFromData(r.content)
                if not pix.isNull():
                    from PyQt6.QtCore import Qt
                    pix = pix.scaled(
                        36, 36,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.signals.loaded.emit(self.track_id, pix)
        except Exception:
            pass
