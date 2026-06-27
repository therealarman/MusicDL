#!/usr/bin/env python3
"""MusicDL — desktop entry point.

Starts the FastAPI backend in a daemon thread, then launches the PyQt6 UI.
"""
import os
import sys
import threading

# Ensure the repo root is on sys.path so backend imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _run_server(host: str, port: int) -> None:
    import asyncio
    import uvicorn

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(
        "backend.main:app",
        host=host,
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())


def main() -> None:
    from backend.config import settings

    host = "127.0.0.1"
    port = settings.PORT
    base_url = f"http://{host}:{port}"

    # Start FastAPI backend in a daemon thread
    server_thread = threading.Thread(
        target=_run_server, args=(host, port), daemon=True, name="uvicorn"
    )
    server_thread.start()

    # Launch Qt application
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QIcon
    from PyQt6.QtWidgets import QApplication

    from gui.style import QSS
    from gui.window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("MusicDL")
    app.setOrganizationName("MusicDL")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(QSS)

    icon_path = os.path.join(os.path.dirname(__file__), "frontend", "icons", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow(base_url=base_url)
    window.setAcceptDrops(True)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
