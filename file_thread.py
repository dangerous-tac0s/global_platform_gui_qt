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

    # Alternatively, you can emit an error signal with the exception or message.
    # Or simply re-use download_complete in an error path with e.g. empty string.
    download_error = pyqtSignal(str)

    def __init__(self, app_name, download_url, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.download_url = download_url

        # You might allow passing in a custom output directory if needed
        self.output_dir = tempfile.gettempdir()  # cross-platform temp folder

        # If you want a custom chunk size
        self.chunk_size = 8192

        # If you want a timeout in seconds
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

                    # If we know total size, emit progress %.
                    if total_length:
                        percent = int(downloaded * 100 / total_length)
                        self.download_progress.emit(percent)

            # Emit 100% at the end just to be sure
            self.download_progress.emit(100)

            # Done, emit success
            self.download_complete.emit(file_path)

        except Exception as e:
            # If there's an error, optionally remove partial file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass  # best effort

            error_msg = f"Download Error: {e}"
            print(error_msg)

            # Either emit a separate error signal:
            self.download_error.emit(error_msg)

            # or re-use download_complete with something like an empty path:
            # self.download_complete.emit("")
