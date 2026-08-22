"""Main application window for MusicDL desktop app."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import requests
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import (
    QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .style import ACCENT, BG, BORDER, ERROR, INFO, MUTED, SURFACE, SURFACE2, TEXT, WARN, btn_style
from .workers import (
    CancelWorker, DownloadStartWorker, FetchWorker, ImageLoader,
    ServerWaitWorker, SSEWorker,
)

# ── Constants ──────────────────────────────────────────────────────────────────

BROWSERS = [
    ("— No browser —", ""),
    ("Firefox  ✓", "firefox"),
    ("Brave  ⚠ close first", "brave"),
    ("Chrome  ⚠ close first", "chrome"),
    ("Chromium  ⚠ close first", "chromium"),
    ("Edge  ⚠ close first", "edge"),
    ("Opera  ⚠ close first", "opera"),
    ("Safari", "safari"),
    ("Vivaldi  ⚠ close first", "vivaldi"),
]

FORMATS = ["mp3", "flac", "wav", "ogg", "m4a"]

QUALITIES = [
    ("128 kbps", "128"),
    ("192 kbps", "192"),
    ("256 kbps", "256"),
    ("320 kbps (best)", "320"),
    ("Best available", "best"),
]

TEMPLATE_PRESETS = [
    ("— Presets —", ""),
    ("Simple", "{artist} - {title}"),
    ("Track listing", "{track_number}. {title}"),
    ("Full detail", "{artist} - {album} - {track_number} {title}"),
    ("Playlist order", "{playlist_index}. {artist} - {title}"),
    ("Year prefix", "{year} - {artist} - {title}"),
]

TOKENS = [
    "title", "artist", "artists", "album", "album_artist",
    "track_number", "disc_number", "year", "date", "duration",
    "playlist", "playlist_index", "source",
]

STATUS_COLORS: Dict[str, tuple] = {
    "queued":      ("rgba(139,148,158,0.15)", MUTED),
    "searching":   ("rgba(88,166,255,0.15)",  INFO),
    "downloading": ("rgba(29,185,84,0.15)",   ACCENT),
    "converting":  ("rgba(210,153,34,0.15)",  WARN),
    "embedding":   ("rgba(210,153,34,0.15)",  WARN),
    "done":        ("rgba(29,185,84,0.2)",    ACCENT),
    "error":       ("rgba(248,81,73,0.15)",   ERROR),
    "cancelled":   ("rgba(139,148,158,0.15)", MUTED),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _btn(text: str, variant: str = "secondary", size: str = "", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setStyleSheet(btn_style(variant, small=(size == "sm")))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _label(text: str = "", obj_name: str = "", color: str = "", font_size: int = 0) -> QLabel:
    lb = QLabel(text)
    if obj_name:
        lb.setObjectName(obj_name)
    style_parts = []
    if color:
        style_parts.append(f"color: {color};")
    if font_size:
        style_parts.append(f"font-size: {font_size}px;")
    if style_parts:
        lb.setStyleSheet(" ".join(style_parts))
    return lb


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    f.setFrameShape(QFrame.Shape.StyledPanel)
    return f


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setStyleSheet(f"color: {BORDER}; max-height: 1px;")
    return line


def _fmt_duration(ms: int) -> str:
    if not ms:
        return "--:--"
    s = round(ms / 1000)
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


def _preview_template(template: str, track: dict) -> str:
    if not track:
        return template
    dur = _fmt_duration(track.get("duration_ms", 0))
    vals = {
        "title": track.get("title") or "Title",
        "artist": track.get("artist") or "Artist",
        "artists": ", ".join(track.get("artists") or [track.get("artist", "Artist")]),
        "album": track.get("album") or "Album",
        "album_artist": track.get("album_artist") or track.get("artist") or "Artist",
        "track_number": str(track.get("track_number") or 1).zfill(2),
        "disc_number": str(track.get("disc_number") or 1),
        "year": track.get("year") or "2024",
        "date": track.get("date") or "2024-01-01",
        "duration": dur,
        "playlist": track.get("playlist_name") or "Playlist",
        "playlist_index": str(track.get("playlist_index") or 1).zfill(3),
        "source": track.get("source") or "spotify",
    }
    result = template
    for k, v in vals.items():
        result = result.replace(f"{{{k}}}", v)
    result = re.sub(r'[/\\:*?"<>|]', "_", result).strip()[:80]
    return result


# ── Per-track progress widget ──────────────────────────────────────────────────

class TrackProgressItem(QFrame):
    def __init__(self, track: dict, job_id: str, base_url: str, parent=None):
        super().__init__(parent)
        self.track = track
        self.job_id = job_id
        self.base_url = base_url
        self.file_path: Optional[str] = None
        self._build()

    def _build(self):
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {SURFACE2};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)

        title_text = f"{self.track.get('title', '?')}  —  {self.track.get('artist', '?')}"
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {TEXT};")
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setTextFormat(Qt.TextFormat.PlainText)

        self.badge = QLabel("queued")
        self._set_badge("queued")

        self.open_btn = QPushButton("Open Folder")
        self.open_btn.setFixedHeight(24)
        self.open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SURFACE};
                color: {MUTED};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 11px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}
        """)
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(self._open_folder)

        header.addWidget(self.title_lbl)
        header.addWidget(self.badge)
        header.addWidget(self.open_btn)
        layout.addLayout(header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximumHeight(5)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.msg_lbl = QLabel("")
        self.msg_lbl.setStyleSheet(f"font-size: 11px; color: {MUTED};")
        layout.addWidget(self.msg_lbl)

    def _set_badge(self, status: str):
        bg, color = STATUS_COLORS.get(status, STATUS_COLORS["queued"])
        self.badge.setText(status)
        self.badge.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: {color};
                border-radius: 50px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)

    def update_progress(self, data: dict):
        status = data.get("status", "queued")
        progress = int(data.get("progress", 0))
        message = data.get("message", "")
        file_path = data.get("file_path")

        self._set_badge(status)
        self.progress_bar.setValue(progress)
        self.msg_lbl.setText(message)

        if file_path:
            self.file_path = file_path

        if status == "done":
            self.setStyleSheet(f"""
                QFrame#card {{
                    background: {SURFACE2};
                    border: 1px solid {ACCENT};
                    border-radius: 6px;
                }}
            """)
            self.open_btn.setVisible(True)
        elif status == "error":
            self.setStyleSheet(f"""
                QFrame#card {{
                    background: {SURFACE2};
                    border: 1px solid {ERROR};
                    border-radius: 6px;
                }}
            """)

    def _open_folder(self):
        path = self.file_path
        if path and os.path.exists(path):
            folder = os.path.dirname(path)
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{path}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", folder])
        else:
            from backend.config import settings
            folder = settings.TEMP_DIR
            if sys.platform == "win32":
                os.startfile(folder)


# ── Token picker dialog ────────────────────────────────────────────────────────

class TokenPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.selected_token: Optional[str] = None
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
            QLabel#header {{
                font-size: 11px;
                font-weight: 600;
                color: {MUTED};
                padding: 0 2px 4px 2px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        hdr = QLabel("Click a token to insert")
        hdr.setObjectName("header")
        layout.addWidget(hdr)

        wrap = QWidget()
        flow = _FlowLayout(wrap, spacing=4)
        for token in TOKENS:
            btn = QPushButton(f"{{{token}}}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {SURFACE2};
                    color: {TEXT};
                    border: 1px solid {BORDER};
                    border-radius: 50px;
                    padding: 3px 10px;
                    font-size: 12px;
                    font-family: "Cascadia Code", "Consolas", monospace;
                }}
                QPushButton:hover {{
                    border-color: {ACCENT};
                    color: {ACCENT};
                }}
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=token: self._pick(t))
            flow.addWidget(btn)
        layout.addWidget(wrap)

    def _pick(self, token: str):
        self.selected_token = token
        self.accept()


# ── Minimal flow layout for token pills ───────────────────────────────────────

class _FlowLayout(QVBoxLayout):
    """Simple wrapping layout for token pills (horizontal rows)."""
    def __init__(self, parent, spacing=4):
        super().__init__(parent)
        self.setSpacing(spacing)
        self._rows: List[QHBoxLayout] = []
        self._current_row: Optional[QHBoxLayout] = None
        self._add_row()

    def _add_row(self):
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)
        self._rows.append(row)
        self._current_row = row
        self.addLayout(row)

    def addWidget(self, widget, stretch=0, alignment=Qt.AlignmentFlag(0)):
        if len(self._rows[-1].children()) >= 4:
            self._add_row()
        self._current_row.addWidget(widget)


# ── Per-batch progress dialog (non-modal, one per download batch) ─────────────

class ProgressBatchDialog(QDialog):
    """Opens alongside the main window for a single download batch."""

    job_complete = pyqtSignal(str, list)  # job_id, list of history-entry dicts

    def __init__(
        self,
        job_id: str,
        tracks: List[dict],
        base_url: str,
        fmt: str,
        parent=None,
    ):
        super().__init__(parent, Qt.WindowType.Window)
        self.job_id = job_id
        self.tracks = tracks
        self.base_url = base_url
        self._fmt = fmt
        self._save_folder: Optional[str] = None  # populated from first completed file_path
        self.track_progress_widgets: Dict[str, TrackProgressItem] = {}
        self._sse_worker: Optional[SSEWorker] = None
        self._cancel_workers: List[CancelWorker] = []
        self._build()
        self._start_sse()

    def _build(self):
        n = len(self.tracks)
        self.setWindowTitle(f"Downloading — {n} track{'s' if n != 1 else ''}")
        self.resize(620, 520)
        self.setMinimumWidth(500)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        self._title_lbl = _label(f"Downloading {n} track{'s' if n != 1 else ''}…", color=TEXT, font_size=14)
        self._title_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT};")
        self._count_lbl = _label("", color=MUTED, font_size=11)
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()
        hdr.addWidget(self._count_lbl)
        layout.addLayout(hdr)

        # Overall progress bar
        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setMaximumHeight(6)
        self._overall_bar.setTextVisible(False)
        layout.addWidget(self._overall_bar)

        # Per-track scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._track_layout = QVBoxLayout(content)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.setSpacing(6)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        for track in self.tracks:
            item = TrackProgressItem(track, self.job_id, self.base_url)
            self.track_progress_widgets[track["id"]] = item
            self._track_layout.addWidget(item)
        self._track_layout.addStretch()

        # Bottom row: cancel | open-folder | close
        btn_row = QHBoxLayout()
        self._cancel_btn = _btn("✕  Cancel", "danger")
        self._cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        self._open_folder_btn = _btn("📂  Open Folder", "secondary")
        self._open_folder_btn.setEnabled(False)
        self._open_folder_btn.setToolTip("Open the folder containing the downloaded files")
        self._open_folder_btn.clicked.connect(self._open_save_folder)
        btn_row.addWidget(self._open_folder_btn)
        self._close_btn = _btn("Close", "secondary")
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _start_sse(self):
        self._sse_worker = SSEWorker(self.base_url, self.job_id)
        self._sse_worker.track_update.connect(self._on_track_update)
        self._sse_worker.job_update.connect(self._on_job_update)
        self._sse_worker.log_message.connect(self._on_log)
        self._sse_worker.start()

    @pyqtSlot(dict)
    def _on_track_update(self, data: dict):
        tid = data.get("track_id", "")
        pw = self.track_progress_widgets.get(tid)
        if pw:
            pw.update_progress(data)
        # Latch the save folder as soon as any completed file_path arrives
        if self._save_folder is None:
            fp = data.get("file_path")
            if fp:
                self._save_folder = os.path.dirname(fp)
                self._open_folder_btn.setEnabled(True)
        self._refresh_overall()

    def _open_save_folder(self):
        if self._save_folder and os.path.isdir(self._save_folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._save_folder))

    @pyqtSlot(dict)
    def _on_job_update(self, data: dict):
        status = data.get("status")
        completed = data.get("completed_tracks", 0)
        failed = data.get("failed_tracks", 0)
        total = data.get("total_tracks", len(self.track_progress_widgets))

        if total > 0:
            self._overall_bar.setValue(int((completed / total) * 100))
        self._count_lbl.setText(
            f"{completed}/{total} done" + (f"  —  {failed} failed" if failed else "")
        )

        if status == "done":
            self._overall_bar.setValue(100)
            self.setWindowTitle(f"Complete — {completed} track{'s' if completed != 1 else ''} downloaded")
            self._title_lbl.setText(f"Done! {completed} track{'s' if completed != 1 else ''} downloaded.")
            self._cancel_btn.setEnabled(False)
            self._emit_complete()
        elif status == "cancelled":
            self.setWindowTitle("Cancelled")
            self._title_lbl.setText("Download cancelled.")
            self._cancel_btn.setEnabled(False)

    @pyqtSlot(str)
    def _on_log(self, msg: str):
        pass  # Could forward to status bar; currently swallowed

    def _refresh_overall(self):
        widgets = list(self.track_progress_widgets.values())
        if not widgets:
            return
        completed = sum(1 for w in widgets if w.badge.text() == "done")
        failed = sum(1 for w in widgets if w.badge.text() == "error")
        total = len(widgets)
        self._overall_bar.setValue(int((completed / total) * 100) if total else 0)
        self._count_lbl.setText(
            f"{completed}/{total} done" + (f"  —  {failed} failed" if failed else "")
        )

    def _emit_complete(self):
        done_entries = []
        ts = time.time()
        for track in self.tracks:
            pw = self.track_progress_widgets.get(track["id"])
            if pw and pw.badge.text() == "done":
                done_entries.append({
                    "title": track.get("title", "?"),
                    "artist": track.get("artist", "?"),
                    "format": self._fmt,
                    "timestamp": ts,
                    "file_path": pw.file_path,
                })
        self.job_complete.emit(self.job_id, done_entries)

    def _cancel(self):
        w = CancelWorker(self.base_url, self.job_id)
        self._cancel_workers.append(w)
        w.start()
        self._cancel_btn.setEnabled(False)

    def closeEvent(self, event):
        if self._sse_worker:
            self._sse_worker.stop()
        super().closeEvent(event)


# ── History dialog ─────────────────────────────────────────────────────────────

class HistoryDialog(QDialog):
    """Pop-out window showing download history."""

    history_cleared = pyqtSignal()

    def __init__(self, history: List[dict], parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.history = history
        self._build()

    def _build(self):
        self.setWindowTitle("Download History")
        self.resize(500, 440)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"QDialog {{ background: {BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(_label("DOWNLOAD HISTORY", color=MUTED, font_size=11))
        hdr.addStretch()
        clear_btn = _btn("Clear All", "danger", "sm")
        clear_btn.clicked.connect(self._clear)
        hdr.addWidget(clear_btn)
        layout.addLayout(hdr)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

        self._populate()

        # Close
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = _btn("Close", "secondary")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def _populate(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.history:
            empty = _label("No downloads yet.", color=MUTED)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(empty)
            self._list_layout.addStretch()
            return

        for entry in self.history[:50]:
            row_lay = QHBoxLayout()
            row_lay.setSpacing(10)

            info = QVBoxLayout()
            info.setSpacing(1)
            title_lbl = QLabel(entry.get("title", "?"))
            title_lbl.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {TEXT};")
            title_lbl.setWordWrap(False)
            title_lbl.setTextFormat(Qt.TextFormat.PlainText)

            ts = entry.get("timestamp", 0)
            time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""
            meta_lbl = QLabel(
                f"{entry.get('artist', '?')}  ·  {entry.get('format', '').upper()}  ·  {time_str}"
            )
            meta_lbl.setStyleSheet(f"font-size: 11px; color: {MUTED};")
            info.addWidget(title_lbl)
            info.addWidget(meta_lbl)

            open_btn = QPushButton("📂")
            open_btn.setFixedSize(28, 28)
            open_btn.setStyleSheet(
                f"QPushButton {{ background: {SURFACE2}; border: 1px solid {BORDER};"
                f"border-radius: 4px; font-size: 13px; }}"
                f"QPushButton:hover {{ border-color: {ACCENT}; }}"
            )
            fp = entry.get("file_path")
            if fp and os.path.exists(fp):
                open_btn.setToolTip("Open in Explorer")
                open_btn.clicked.connect(lambda _, p=fp: self._open_file(p))
            else:
                open_btn.setEnabled(False)
                open_btn.setToolTip("File no longer available")

            row_lay.addLayout(info, 1)
            row_lay.addWidget(open_btn)

            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(row_lay)
            self._list_layout.addWidget(wrap)

        self._list_layout.addStretch()

    def _clear(self):
        self.history.clear()
        self.history_cleared.emit()
        self._populate()

    def _open_file(self, path: str):
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url

        # Track state
        self.tracks: List[dict] = []
        self.selected_ids: Set[str] = set()
        self.history: List[dict] = []

        # Last completed job (for ZIP)
        self._active_job_id: Optional[str] = None

        # Running batch dialogs keyed by job_id
        self._batch_dialogs: Dict[str, ProgressBatchDialog] = {}

        # Keep DownloadStartWorker refs alive until threads finish
        self._active_workers: Set = set()

        # Settings
        self._settings = QSettings("MusicDL", "MusicDL")
        self._load_settings()

        # Workers kept alive to prevent GC
        self._server_worker: Optional[ServerWaitWorker] = None
        self._fetch_worker: Optional[FetchWorker] = None

        # Image loading pool
        self._image_pool = QThreadPool()
        self._image_pool.setMaxThreadCount(4)
        self._art_labels: Dict[str, QLabel] = {}

        self._build_ui()
        self._set_server_ready(False)
        self._start_server_wait()

    # ── Settings persistence ───────────────────────────────────────────────────

    def _load_settings(self):
        s = self._settings
        self.fmt = s.value("format", "mp3")
        self.quality = s.value("quality", "320")
        self.template = s.value("template", "{artist} - {title}")
        self.normalize = s.value("normalize", False, type=bool)
        self.embed_art = s.value("embed_art", True, type=bool)
        self.cookies_browser = s.value("cookies_browser", "")
        self.output_dir = s.value("output_dir", "")
        try:
            import json
            raw = s.value("history", "[]")
            self.history = json.loads(raw) if raw else []
        except Exception:
            self.history = []

    def _save_settings(self):
        s = self._settings
        s.setValue("format", self.fmt)
        s.setValue("quality", self.quality)
        s.setValue("template", self.template)
        s.setValue("normalize", self.normalize)
        s.setValue("embed_art", self.embed_art)
        s.setValue("cookies_browser", self.cookies_browser)
        s.setValue("output_dir", self.output_dir)

    def _save_history(self):
        import json
        self._settings.setValue("history", json.dumps(self.history[:50]))

    def _save_column_widths(self):
        self._settings.setValue(
            "track_table_header_state",
            self.track_table.horizontalHeader().saveState(),
        )

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("MusicDL")
        self.setMinimumSize(820, 640)
        self.resize(960, 840)

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "frontend", "icons", "icon.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {BG}; }}")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header bar
        root_layout.addWidget(self._build_header())

        # ── Splitter: top = settings, bottom = track staging ──────────────────
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setHandleWidth(2)
        self.splitter.setChildrenCollapsible(False)

        self.splitter.addWidget(self._build_settings_pane())
        self.splitter.addWidget(self._build_track_pane())

        self.splitter.setSizes([340, 500])

        root_layout.addWidget(self.splitter, 1)

        # Footer bar (outside splitter, pinned to bottom)
        root_layout.addWidget(self._build_footer_bar())

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet(
            f"QStatusBar {{ background: {SURFACE}; color: {MUTED}; font-size: 12px;"
            f"border-top: 1px solid {BORDER}; }}"
        )

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setFixedHeight(68)
        header.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}"
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "frontend", "icons", "icon.png"
        )
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(
                42, 42, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pix)
            icon_lbl.setFixedSize(42, 42)
            layout.addWidget(icon_lbl)

        title = QLabel("MusicDL")
        title.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {TEXT};")
        layout.addWidget(title)
        layout.addStretch()

        self.spotify_btn = QPushButton("Connect Spotify")
        self.spotify_btn.setStyleSheet(btn_style("spotify", small=True))
        self.spotify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.spotify_btn.setToolTip(
            "Opens your browser to authenticate with Spotify.\n"
            "Required to download from Spotify URLs."
        )
        self.spotify_btn.setVisible(False)
        self.spotify_btn.clicked.connect(self._open_spotify_login)
        layout.addWidget(self.spotify_btn)

        return header

    # ── Settings pane (top half of splitter) ───────────────────────────────────

    def _build_settings_pane(self) -> QScrollArea:
        """Scrollable top pane: URL + filename template + audio settings."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background: {BG}; border: none; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        self.url_card = self._build_url_card()
        self.template_card = self._build_template_card()
        self.settings_card = self._build_settings_card()

        layout.addWidget(self.url_card)
        layout.addWidget(self.template_card)
        layout.addWidget(self.settings_card)
        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    # ── Track staging pane (bottom half of splitter) ───────────────────────────

    def _build_track_pane(self) -> QWidget:
        """Bottom pane: action toolbar + track staging area."""
        pane = QWidget()
        pane.setStyleSheet(f"background: {BG};")
        outer = QVBoxLayout(pane)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Action toolbar (between the panes) ─────────────────────────────────
        self.action_toolbar = QFrame()
        self.action_toolbar.setObjectName("actionToolbar")
        self.action_toolbar.setFixedHeight(52)
        toolbar_layout = QHBoxLayout(self.action_toolbar)
        toolbar_layout.setContentsMargins(20, 8, 20, 8)
        toolbar_layout.setSpacing(10)

        self.dl_all_btn = _btn("↓  Download All (0)", "secondary")
        self.dl_all_btn.setEnabled(False)
        self.dl_all_btn.clicked.connect(self._download_all)

        self.dl_selected_btn = _btn("↓  Download Selected (0)", "primary")
        self.dl_selected_btn.setEnabled(False)
        self.dl_selected_btn.clicked.connect(self._download_selected)

        toolbar_layout.addWidget(self.dl_all_btn)
        toolbar_layout.addWidget(self.dl_selected_btn)
        toolbar_layout.addStretch()
        outer.addWidget(self.action_toolbar)

        # ── Track staging content ──────────────────────────────────────────────
        staging = QWidget()
        staging.setStyleSheet(f"background: {BG};")
        staging_layout = QVBoxLayout(staging)
        staging_layout.setContentsMargins(20, 12, 20, 12)
        staging_layout.setSpacing(8)

        # Header row: playlist title + selection count
        hdr = QHBoxLayout()
        self.track_card_title = _label("TRACKS", color=MUTED, font_size=11)
        self.track_count_lbl = _label("0 selected", color=MUTED, font_size=11)
        hdr.addWidget(self.track_card_title)
        hdr.addStretch()
        hdr.addWidget(self.track_count_lbl)
        staging_layout.addLayout(hdr)

        # Selection controls
        ctrl = QHBoxLayout()
        self.select_all_btn = _btn("Select All", "secondary", "sm")
        self.select_all_btn.setFixedWidth(90)
        self.select_all_btn.setEnabled(False)
        self.select_all_btn.clicked.connect(self._toggle_select_all)
        self.invert_btn = _btn("Invert", "secondary", "sm")
        self.invert_btn.setFixedWidth(70)
        self.invert_btn.setEnabled(False)
        self.invert_btn.clicked.connect(self._invert_selection)
        ctrl.addWidget(self.select_all_btn)
        ctrl.addWidget(self.invert_btn)
        ctrl.addStretch()
        staging_layout.addLayout(ctrl)

        # Track table
        self.track_table = QTableWidget()
        self.track_table.setColumnCount(7)
        self.track_table.setHorizontalHeaderLabels(["", "#", "", "Title", "Artist", "Album", "Duration"])
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.verticalHeader().setVisible(False)
        self.track_table.setShowGrid(False)
        self.track_table.setWordWrap(False)
        self.track_table.setAlternatingRowColors(False)
        self.track_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hh = self.track_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        hh.setStretchLastSection(False)
        self.track_table.setColumnWidth(0, 38)
        self.track_table.setColumnWidth(1, 36)
        self.track_table.setColumnWidth(2, 50)
        self.track_table.setColumnWidth(6, 70)
        self.track_table.verticalHeader().setDefaultSectionSize(44)

        staging_layout.addWidget(self.track_table, 1)
        outer.addWidget(staging, 1)

        return pane

    # ── Footer bar (pinned at window bottom) ───────────────────────────────────

    def _build_footer_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("footerBar")
        bar.setFixedHeight(52)
        bar.setStyleSheet(
            f"QFrame#footerBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(10)

        self.zip_btn = _btn("⊞  Download ZIP", "secondary")
        self.zip_btn.setVisible(False)
        self.zip_btn.clicked.connect(self._save_zip)

        self.history_btn = _btn("History", "secondary")
        self.history_btn.clicked.connect(self._open_history_dialog)

        layout.addWidget(self.zip_btn)
        layout.addStretch()
        layout.addWidget(self.history_btn)

        return bar

    # ── URL Card ───────────────────────────────────────────────────────────────

    def _build_url_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("URL", color=MUTED, font_size=11))
        hdr.addStretch()
        layout.addLayout(hdr)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Paste a Spotify or YouTube track, album, or playlist URL…"
        )
        self.url_input.returnPressed.connect(self._do_fetch)

        self.paste_btn = _btn("⎘  Paste", "secondary")
        self.paste_btn.setFixedWidth(90)
        self.paste_btn.clicked.connect(self._paste_url)

        self.fetch_btn = _btn("⌕  Fetch", "primary")
        self.fetch_btn.setFixedWidth(100)
        self.fetch_btn.clicked.connect(self._do_fetch)

        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.paste_btn)
        url_row.addWidget(self.fetch_btn)
        layout.addLayout(url_row)

        tip = _label(
            "Tip: paste a Spotify or YouTube URL for a track, album, or playlist.",
            color=MUTED, font_size=11
        )
        layout.addWidget(tip)

        return card

    # ── Template Card ──────────────────────────────────────────────────────────

    def _build_template_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("FILENAME TEMPLATE", color=MUTED, font_size=11))
        hdr.addStretch()
        self.tokens_btn = _btn("{}  Tokens", "ghost")
        self.tokens_btn.setFixedWidth(100)
        self.tokens_btn.clicked.connect(self._show_token_picker)
        hdr.addWidget(self.tokens_btn)
        layout.addLayout(hdr)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.preset_combo = QComboBox()
        for label, _ in TEMPLATE_PRESETS:
            self.preset_combo.addItem(label)
        self.preset_combo.setFixedWidth(150)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

        self.template_input = QLineEdit(self.template)
        self.template_input.setObjectName("template")
        self.template_input.setPlaceholderText("{artist} - {title}")
        self.template_input.textChanged.connect(self._on_template_changed)

        input_row.addWidget(self.preset_combo)
        input_row.addWidget(self.template_input, 1)
        layout.addLayout(input_row)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(4)
        preview_row.addWidget(_label("Preview:", color=MUTED, font_size=11))
        self.preview_lbl = QLabel(self._get_preview())
        self.preview_lbl.setStyleSheet(
            f"font-family: 'Cascadia Code', 'Consolas', monospace;"
            f"font-size: 11px; color: {ACCENT}; font-weight: 600;"
        )
        self.preview_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_row.addWidget(self.preview_lbl, 1)
        layout.addLayout(preview_row)

        return card

    # ── Settings Card ──────────────────────────────────────────────────────────

    def _build_settings_card(self) -> QFrame:
        card = _card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        layout.addWidget(_label("AUDIO SETTINGS", color=MUTED, font_size=11))

        selects_row = QHBoxLayout()
        selects_row.setSpacing(16)

        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(4)
        fmt_col.addWidget(_label("FORMAT", color=MUTED, font_size=10))
        self.format_combo = QComboBox()
        for f in FORMATS:
            self.format_combo.addItem(f.upper(), f)
        self.format_combo.setCurrentText(self.fmt.upper())
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_col.addWidget(self.format_combo)

        q_col = QVBoxLayout()
        q_col.setSpacing(4)
        q_col.addWidget(_label("BITRATE", color=MUTED, font_size=10))
        self.quality_combo = QComboBox()
        for label, val in QUALITIES:
            self.quality_combo.addItem(label, val)
        cur_q = next((i for i, (_, v) in enumerate(QUALITIES) if v == self.quality), 3)
        self.quality_combo.setCurrentIndex(cur_q)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        q_col.addWidget(self.quality_combo)

        br_col = QVBoxLayout()
        br_col.setSpacing(4)
        br_lbl_row = QHBoxLayout()
        br_lbl_row.setSpacing(4)
        br_lbl_row.addWidget(_label("BROWSER", color=MUTED, font_size=10))
        tip_lbl = QLabel("?")
        tip_lbl.setToolTip(
            "Select your browser to pass cookies for age-restricted YouTube content.\n"
            "Requirements:\n"
            "  • You must be logged into your Google account in that browser.\n"
            "  • The browser must be FULLY CLOSED (all windows) before downloading.\n"
            "    Chrome, Edge, and Brave lock their cookie file while running —\n"
            "    yt-dlp cannot read it until the browser is closed."
        )
        tip_lbl.setStyleSheet(
            f"color: {MUTED}; background: {SURFACE2}; border: 1px solid {BORDER};"
            f"border-radius: 50px; font-size: 10px; font-weight: 700;"
            f"padding: 0px 5px; min-width: 14px; max-width: 14px;"
            f"min-height: 14px; max-height: 14px;"
        )
        tip_lbl.setCursor(Qt.CursorShape.WhatsThisCursor)
        br_lbl_row.addWidget(tip_lbl)
        br_lbl_row.addStretch()
        br_col.addLayout(br_lbl_row)

        self.browser_combo = QComboBox()
        self.browser_combo.setToolTip(
            "Browser must be FULLY CLOSED before downloading.\n"
            "Chrome/Edge/Brave lock their cookie file while running."
        )
        for label, val in BROWSERS:
            self.browser_combo.addItem(label, val)
        cur_br = next((i for i, (_, v) in enumerate(BROWSERS) if v == self.cookies_browser), 0)
        self.browser_combo.setCurrentIndex(cur_br)
        self.browser_combo.currentIndexChanged.connect(self._on_browser_changed)
        br_col.addWidget(self.browser_combo)

        selects_row.addLayout(fmt_col)
        selects_row.addLayout(q_col)
        selects_row.addLayout(br_col)
        selects_row.addStretch()
        layout.addLayout(selects_row)

        checks = QHBoxLayout()
        checks.setSpacing(20)
        self.normalize_chk = QCheckBox("Normalize audio levels (ffmpeg loudnorm)")
        self.normalize_chk.setChecked(self.normalize)
        self.normalize_chk.stateChanged.connect(self._on_normalize_changed)
        self.embed_art_chk = QCheckBox("Embed album artwork")
        self.embed_art_chk.setChecked(self.embed_art)
        self.embed_art_chk.stateChanged.connect(self._on_embed_art_changed)
        checks.addWidget(self.normalize_chk)
        checks.addWidget(self.embed_art_chk)
        checks.addStretch()
        layout.addLayout(checks)

        layout.addWidget(_hline())

        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        loc_row.addWidget(_label("SAVE TO", color=MUTED, font_size=10))

        self.output_dir_input = QLineEdit(self.output_dir)
        self.output_dir_input.setPlaceholderText("Default temp location (files deleted after cleanup)")
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setStyleSheet(
            f"QLineEdit {{ background: {SURFACE2}; border: 1px solid {BORDER};"
            f"border-radius: 6px; color: {TEXT}; font-size: 12px; padding: 6px 10px; }}"
        )
        self.output_dir_input.textChanged.connect(self._on_output_dir_changed)

        browse_btn = _btn("Browse…", "secondary", "sm")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_output_dir)

        clear_loc_btn = _btn("✕", "secondary", "sm")
        clear_loc_btn.setFixedWidth(32)
        clear_loc_btn.setToolTip("Reset to default temp location")
        clear_loc_btn.clicked.connect(self._clear_output_dir)

        self.open_dir_btn = _btn("Open", "secondary", "sm")
        self.open_dir_btn.setFixedWidth(56)
        self.open_dir_btn.setToolTip("Open the save folder in Explorer")
        self.open_dir_btn.clicked.connect(self._open_output_dir)
        self.open_dir_btn.setVisible(bool(self.output_dir))

        loc_row.addWidget(self.output_dir_input, 1)
        loc_row.addWidget(browse_btn)
        loc_row.addWidget(clear_loc_btn)
        loc_row.addWidget(self.open_dir_btn)
        layout.addLayout(loc_row)

        return card

    # ── Server readiness ───────────────────────────────────────────────────────

    def _start_server_wait(self):
        self._server_worker = ServerWaitWorker(self.base_url)
        self._server_worker.ready.connect(self.on_server_ready)
        self._server_worker.start()

    @pyqtSlot(bool)
    def on_server_ready(self, ready: bool):
        self._set_server_ready(ready)
        if not ready:
            self._notify("Backend failed to start — check console for errors.", "error")
            return
        try:
            health = requests.get(f"{self.base_url}/api/health", timeout=5).json()
            checks = health.get("checks", {})
            warnings = health.get("warnings", [])
            spotify_ok = checks.get("spotify_configured", False)
            self.spotify_btn.setVisible(True)
            self.spotify_btn.setText("Reconnect Spotify" if spotify_ok else "Connect Spotify")
            for w in warnings:
                self._notify(w, "warn")
                break
            if not warnings:
                self._notify("Ready.", "info")
        except Exception:
            self._notify("Ready.", "info")

    def _open_spotify_login(self):
        import webbrowser
        webbrowser.open(f"{self.base_url}/api/spotify/login")
        self._notify("Opened Spotify login in your browser. Complete the auth flow, then come back.", "info")

    def _set_server_ready(self, ready: bool):
        self.fetch_btn.setEnabled(ready)
        self.paste_btn.setEnabled(ready)
        self.url_input.setEnabled(ready)
        if not ready:
            self.url_input.setPlaceholderText("Starting backend…")
        else:
            self.url_input.setPlaceholderText(
                "Paste a Spotify or YouTube track, album, or playlist URL…"
            )

    # ── Fetch ──────────────────────────────────────────────────────────────────

    def _do_fetch(self):
        url = self.url_input.text().strip()
        if not url:
            self._notify("Please enter a URL.", "warn")
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching…")
        self.tracks = []
        self.selected_ids.clear()
        self._art_labels.clear()

        self._fetch_worker = FetchWorker(url, self.base_url)
        self._fetch_worker.result.connect(self._on_fetch_result)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    @pyqtSlot(dict)
    def _on_fetch_result(self, data: dict):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("⌕  Fetch")
        self.tracks = data.get("tracks", [])
        self.selected_ids = {t["id"] for t in self.tracks}

        playlist = data.get("playlist_name", "")
        count = len(self.tracks)
        if playlist:
            self.track_card_title.setText(f"  {playlist}  —  {count} TRACKS")
        else:
            self.track_card_title.setText("TRACKS")

        if not self.tracks:
            self._notify("No tracks found for this URL.", "warn")
            return

        self._notify(f"Found {count} track{'s' if count != 1 else ''}.", "info")
        self._rebuild_track_table()
        self._update_actions()
        self._update_preview()
        self._load_images()

    @pyqtSlot(str)
    def _on_fetch_error(self, msg: str):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("⌕  Fetch")
        lower = msg.lower()
        if "spotify" in lower and any(k in lower for k in ("auth", "login", "token", "credentials", "unauthorized", "401")):
            self._notify("Spotify auth required — click 'Connect Spotify' in the toolbar.", "warn")
        else:
            self._notify(f"Error: {msg}", "error")

    # ── Track table ────────────────────────────────────────────────────────────

    def _rebuild_track_table(self):
        table = self.track_table
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(len(self.tracks))
        self._art_labels.clear()

        for row, track in enumerate(self.tracks):
            tid = track["id"]
            selected = tid in self.selected_ids
            table.setRowHeight(row, 44)

            cb = QCheckBox()
            cb.setChecked(selected)
            cb.setStyleSheet(
                f"QCheckBox::indicator {{ width: 15px; height: 15px; }}"
                f"QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}"
            )
            cb.stateChanged.connect(
                lambda state, t=tid: self._on_track_check_changed(t, state)
            )
            cb_wrap = QWidget()
            cb_wrap.setStyleSheet("background: transparent;")
            cb_lay = QHBoxLayout(cb_wrap)
            cb_lay.setContentsMargins(0, 0, 0, 0)
            cb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_lay.addWidget(cb)
            table.setCellWidget(row, 0, cb_wrap)

            num = track.get("playlist_index") or (row + 1)
            num_item = QTableWidgetItem(str(num))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setForeground(QColor(MUTED))
            num_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row, 1, num_item)

            art_lbl = QLabel()
            art_lbl.setFixedSize(36, 36)
            art_lbl.setStyleSheet(f"background: {BORDER}; border-radius: 4px; color: {MUTED}; font-size: 14px;")
            art_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art_lbl.setText("♪")
            art_wrap = QWidget()
            art_wrap.setStyleSheet("background: transparent;")
            aw = QHBoxLayout(art_wrap)
            aw.setContentsMargins(4, 4, 4, 4)
            aw.addWidget(art_lbl)
            table.setCellWidget(row, 2, art_wrap)
            self._art_labels[tid] = art_lbl

            for col, key in [(3, "title"), (4, "artist"), (5, "album")]:
                val = track.get(key, "") or "—"
                item = QTableWidgetItem(val)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if key == "album":
                    item.setForeground(QColor(MUTED))
                table.setItem(row, col, item)

            dur = _fmt_duration(track.get("duration_ms", 0))
            dur_item = QTableWidgetItem(dur)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dur_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            dur_item.setForeground(QColor(MUTED))
            table.setItem(row, 6, dur_item)

        table.blockSignals(False)

        # Enable selection controls now that tracks are loaded
        self.select_all_btn.setEnabled(True)
        self.invert_btn.setEnabled(True)
        self._update_selection_ui()

    def _on_track_check_changed(self, track_id: str, state: int):
        if state == Qt.CheckState.Checked.value:
            self.selected_ids.add(track_id)
        else:
            self.selected_ids.discard(track_id)
        self._update_selection_ui()

    def _update_selection_ui(self):
        count = len(self.selected_ids)
        total = len(self.tracks)
        self.track_count_lbl.setText(f"{count} of {total} selected")
        all_sel = count == total
        self.select_all_btn.setText("Deselect All" if all_sel else "Select All")
        self._update_actions()

    def _toggle_select_all(self):
        if len(self.selected_ids) == len(self.tracks):
            self.selected_ids.clear()
        else:
            self.selected_ids = {t["id"] for t in self.tracks}
        self._sync_checkboxes()
        self._update_selection_ui()

    def _invert_selection(self):
        self.selected_ids = {t["id"] for t in self.tracks if t["id"] not in self.selected_ids}
        self._sync_checkboxes()
        self._update_selection_ui()

    def _sync_checkboxes(self):
        table = self.track_table
        table.blockSignals(True)
        for row, track in enumerate(self.tracks):
            cb_widget = table.cellWidget(row, 0)
            if cb_widget:
                cb = cb_widget if isinstance(cb_widget, QCheckBox) else cb_widget.findChild(QCheckBox)
                if cb:
                    cb.blockSignals(True)
                    cb.setChecked(track["id"] in self.selected_ids)
                    cb.blockSignals(False)
        table.blockSignals(False)

    # ── Image loading ──────────────────────────────────────────────────────────

    def _load_images(self):
        for track in self.tracks:
            url = track.get("album_art_url")
            tid = track["id"]
            if url and tid in self._art_labels:
                loader = ImageLoader(tid, url)
                loader.signals.loaded.connect(self._on_image_loaded)
                self._image_pool.start(loader)

    @pyqtSlot(str, QPixmap)
    def _on_image_loaded(self, track_id: str, pixmap: QPixmap):
        lbl = self._art_labels.get(track_id)
        if lbl and not pixmap.isNull():
            lbl.setPixmap(pixmap)
            lbl.setStyleSheet("background: transparent; border-radius: 4px;")
            lbl.setText("")

    # ── Actions ────────────────────────────────────────────────────────────────

    def _update_actions(self):
        sel = len(self.selected_ids)
        total = len(self.tracks)
        self.dl_selected_btn.setText(f"↓  Download Selected ({sel})")
        self.dl_selected_btn.setEnabled(sel > 0)
        self.dl_all_btn.setText(f"↓  Download All ({total})")
        self.dl_all_btn.setEnabled(total > 0)

    def _download_selected(self):
        tracks = [t for t in self.tracks if t["id"] in self.selected_ids]
        if not tracks:
            self._notify("No tracks selected.", "warn")
            return
        self._start_download(tracks)

    def _download_all(self):
        if not self.tracks:
            return
        self._start_download(self.tracks)

    def _start_download(self, tracks: List[dict]):
        fmt_snapshot = self.fmt
        payload = {
            "tracks": tracks,
            "settings": {
                "format": self.fmt,
                "quality": self.quality,
                "filename_template": self.template,
                "normalize_audio": self.normalize,
                "embed_artwork": self.embed_art,
                "download_thumbnail": False,
                "cookies_browser": self.cookies_browser,
                "output_dir": self.output_dir,
            },
        }

        worker = DownloadStartWorker(self.base_url, payload)
        worker.started.connect(
            lambda job_id, t=tracks, f=fmt_snapshot: self._on_batch_started(job_id, t, f)
        )
        worker.error.connect(self._on_download_error)
        self._active_workers.add(worker)
        worker.finished.connect(lambda w=worker: self._active_workers.discard(w))
        worker.start()

    @pyqtSlot(str)
    def _on_batch_started(self, job_id: str, tracks: list, fmt: str):
        dlg = ProgressBatchDialog(job_id, tracks, self.base_url, fmt, self)
        dlg.job_complete.connect(self._on_batch_complete)
        dlg.setWindowFlag(Qt.WindowType.Window, True)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda: self._batch_dialogs.pop(job_id, None))
        dlg.show()
        self._batch_dialogs[job_id] = dlg
        self._notify(
            f"Download started — {len(tracks)} track{'s' if len(tracks) != 1 else ''}. "
            "Progress window is open.",
            "info",
        )

    @pyqtSlot(str)
    def _on_download_error(self, msg: str):
        self._notify(f"Download error: {msg}", "error")

    @pyqtSlot(str, list)
    def _on_batch_complete(self, job_id: str, done_entries: list):
        self._active_job_id = job_id
        self.zip_btn.setVisible(True)
        for entry in done_entries:
            self.history.insert(0, entry)
        self.history = self.history[:50]
        self._save_history()

    def _save_zip(self):
        if not self._active_job_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ZIP", "music_download.zip", "ZIP Archive (*.zip)"
        )
        if not path:
            return
        try:
            r = requests.get(f"{self.base_url}/api/batch/{self._active_job_id}", timeout=60)
            if r.ok:
                with open(path, "wb") as f:
                    f.write(r.content)
                self._notify("ZIP saved.", "info")
                if sys.platform == "win32":
                    os.startfile(os.path.dirname(path))
            else:
                self._notify("ZIP not ready yet.", "warn")
        except Exception as exc:
            self._notify(f"Save failed: {exc}", "error")

    # ── History ────────────────────────────────────────────────────────────────

    def _open_history_dialog(self):
        dlg = HistoryDialog(self.history, self)
        dlg.history_cleared.connect(self._save_history)
        dlg.setWindowFlag(Qt.WindowType.Window, True)
        dlg.show()

    # ── Template ───────────────────────────────────────────────────────────────

    def _on_template_changed(self, text: str):
        self.template = text
        self._save_settings()
        self._update_preview()

    def _on_preset_changed(self, index: int):
        _, tmpl = TEMPLATE_PRESETS[index]
        if tmpl:
            self.template = tmpl
            self.template_input.blockSignals(True)
            self.template_input.setText(tmpl)
            self.template_input.blockSignals(False)
            self._save_settings()
            self._update_preview()

    def _get_preview(self) -> str:
        sample = self.tracks[0] if self.tracks else None
        preview = _preview_template(self.template, sample)
        return f"{preview}.{self.fmt}"

    def _update_preview(self):
        self.preview_lbl.setText(self._get_preview())

    def _show_token_picker(self):
        dlg = TokenPickerDialog(self)
        btn_pos = self.tokens_btn.mapToGlobal(self.tokens_btn.rect().bottomLeft())
        dlg.move(btn_pos)
        dlg.resize(340, 220)
        if dlg.exec() and dlg.selected_token:
            token = f"{{{dlg.selected_token}}}"
            pos = self.template_input.cursorPosition()
            cur_text = self.template_input.text()
            new_text = cur_text[:pos] + token + cur_text[pos:]
            self.template_input.setText(new_text)
            self.template_input.setCursorPosition(pos + len(token))
            self.template_input.setFocus()

    # ── Settings changes ───────────────────────────────────────────────────────

    def _on_format_changed(self, _):
        self.fmt = self.format_combo.currentData()
        lossless = self.fmt in ("flac", "wav")
        self.quality_combo.setEnabled(not lossless)
        self._save_settings()
        self._update_preview()

    def _on_quality_changed(self, _):
        self.quality = self.quality_combo.currentData()
        self._save_settings()

    def _on_browser_changed(self, _):
        self.cookies_browser = self.browser_combo.currentData() or ""
        self._save_settings()

    def _on_normalize_changed(self, state: int):
        self.normalize = bool(state)
        self._save_settings()

    def _on_embed_art_changed(self, state: int):
        self.embed_art = bool(state)
        self._save_settings()

    # ── Download location ──────────────────────────────────────────────────────

    def _browse_output_dir(self):
        start = self.output_dir or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Download Folder", start,
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self.output_dir = folder
            self.output_dir_input.setText(folder)
            self.open_dir_btn.setVisible(True)
            self._save_settings()

    def _on_output_dir_changed(self, text: str):
        self.output_dir = text.strip()
        self._save_settings()

    def _clear_output_dir(self):
        self.output_dir = ""
        self.output_dir_input.setText("")
        self.open_dir_btn.setVisible(False)
        self._save_settings()

    def _open_output_dir(self):
        folder = self.output_dir
        if folder and os.path.isdir(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])

    # ── Paste ─────────────────────────────────────────────────────────────────

    def _paste_url(self):
        cb = QApplication.clipboard()
        text = cb.text().strip()
        if text:
            self.url_input.setText(text)
            self.url_input.setFocus()
        else:
            self._notify("Clipboard is empty.", "warn")

    # ── Notifications ──────────────────────────────────────────────────────────

    def _notify(self, msg: str, level: str = "info"):
        colors = {"info": ACCENT, "warn": WARN, "error": ERROR}
        color = colors.get(level, MUTED)
        self.status_bar.setStyleSheet(
            f"QStatusBar {{ background: {SURFACE}; color: {color}; font-size: 12px;"
            f"border-top: 1px solid {BORDER}; }}"
        )
        self.status_bar.showMessage(msg, 5000)

    # ── Drag and drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        text = ""
        if event.mimeData().hasUrls():
            text = event.mimeData().urls()[0].toString()
        elif event.mimeData().hasText():
            text = event.mimeData().text().strip()
        if text:
            self.url_input.setText(text)
            self._do_fetch()

    def setAcceptDrops(self, on: bool):
        super().setAcceptDrops(on)
