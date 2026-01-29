"""
FileHandlerThread - Background file download thread.

Downloads files from URLs with progress reporting via EventBus.
Maintains backward compatibility with Qt signals during migration.
"""

import os
import tempfile
from typing import Optional

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from ..events.event_bus import (
    EventBus,
    ProgressEvent,
    OperationResultEvent,
    ErrorEvent,
)


class FileHandlerThread(QThread):
    """
    Downloads a file from a given URL and emits signals/events for progress.

    Events Emitted:
    - ProgressEvent: Download progress (0-100)
    - OperationResultEvent: Download complete with file path
    - ErrorEvent: Download error
    """

    # Legacy Qt signals (kept for backward compatibility)
    download_progress = pyqtSignal(int)
    download_complete = pyqtSignal(str)
    download_error = pyqtSignal(str)

    def __init__(
        self,
        app_name: str,
        download_url: str,
        output_dir: Optional[str] = None,
        parent=None,
        use_event_bus: bool = False,
    ):
        """
        Initialize the download thread.

        Args:
            app_name: Filename to save as (e.g. "myApplet.cap")
            download_url: URL to fetch
            output_dir: Folder for downloaded file (defaults to system temp)
            parent: Optional QThread parent
            use_event_bus: If True, emit EventBus events in addition to signals
        """
        super().__init__(parent)
        self.app_name = app_name
        self.download_url = download_url
        self.use_event_bus = use_event_bus

        if output_dir is None:
            self.output_dir = tempfile.gettempdir()
        else:
            self.output_dir = output_dir

        self.chunk_size = 8192
        self.timeout = 15

        self._event_bus = EventBus.instance() if use_event_bus else None

    def run(self):
        """Execute the download in background thread."""
        file_path = os.path.join(self.output_dir, self.app_name)

        try:
            response = requests.get(
                self.download_url,
                stream=True,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                raise Exception(f"HTTP Error: {response.status_code}")

            total_length = response.headers.get('Content-Length')
            if total_length is not None:
                total_length = int(total_length)

            downloaded = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_length:
                        percent = int(downloaded * 100 / total_length)
                        self._emit_progress(percent)

            # Emit 100% completion
            self._emit_progress(100)

            # Emit success
            self._emit_complete(file_path)

        except Exception as e:
            # Remove partial file on error
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

            error_msg = f"Download Error: {e}"
            self._emit_error(error_msg)

    def _emit_progress(self, percent: int) -> None:
        """Emit progress via signal and optionally EventBus."""
        self.download_progress.emit(percent)

        if self._event_bus:
            self._event_bus.emit(ProgressEvent(
                operation="download",
                progress=percent,
                message=f"Downloading {self.app_name}...",
            ))

    def _emit_complete(self, file_path: str) -> None:
        """Emit completion via signal and optionally EventBus."""
        self.download_complete.emit(file_path)

        if self._event_bus:
            self._event_bus.emit(OperationResultEvent(
                success=True,
                message=f"Downloaded {self.app_name}",
                operation_type="download",
                details={"file_path": file_path},
            ))

    def _emit_error(self, error_msg: str) -> None:
        """Emit error via signal and optionally EventBus."""
        print(error_msg)
        self.download_error.emit(error_msg)

        if self._event_bus:
            self._event_bus.emit(ErrorEvent(
                message=error_msg,
                recoverable=True,
            ))
