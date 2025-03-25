import requests
import os
import tempfile
from PyQt5.QtCore import QThread, pyqtSignal

class FileHandlerThread(QThread):
    """
    Downloads a file from a given URL and emits signals for progress and completion.
    """
    # Emitted repeatedly during download with an integer [0..100]
    download_progress = pyqtSignal(int)

    # Emitted upon successful download, providing the local file path
    download_complete = pyqtSignal(str)

    # Emitted upon error, providing an error message
    download_error = pyqtSignal(str)

    def __init__(self, app_name, download_url, output_dir=None, parent=None):
        """
        :param app_name: the filename to save as (e.g. "myApplet.cap")
        :param download_url: the URL to fetch
        :param output_directory: optional folder to place the downloaded file;
                                 defaults to system temp if None
        :param parent: optional QThread parent
        """
        super().__init__(parent)
        self.app_name = app_name
        self.download_url = download_url

        # If no custom output directory is provided, default to temp folder
        if output_dir is None:
            self.output_dir = tempfile.gettempdir()
        else:
            self.output_dir = output_dir

        # Optional: chunk size, timeout
        self.chunk_size = 8192
        self.timeout = 15

    def run(self):
        file_path = os.path.join(self.output_dir, self.app_name)

        try:
            # Begin download
            response = requests.get(self.download_url, stream=True, timeout=self.timeout)

            # Check HTTP status code
            if response.status_code != 200:
                raise Exception(f"HTTP Error: {response.status_code}")

            # If server provides Content-Length, we can track total size
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

                    # If we know total size, emit progress
                    if total_length:
                        percent = int(downloaded * 100 / total_length)
                        self.download_progress.emit(percent)

            # Emit 100% at the end to ensure the UI shows completion
            self.download_progress.emit(100)

            # Emit success
            self.download_complete.emit(file_path)

        except Exception as e:
            # Optionally remove partial file on error
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

            error_msg = f"Download Error: {e}"
            print(error_msg)
            self.download_error.emit(error_msg)
