"""
Source Configuration Page

Configures the CAP file source (local, HTTP, or GitHub release).
"""

from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QPushButton,
    QFileDialog,
    QStackedWidget,
    QWidget,
    QMessageBox,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
)
from PyQt5.QtCore import Qt

from .utils import (
    parse_github_url,
    fetch_github_repo_info,
    fetch_github_release_assets,
    fetch_github_plugin_definition,
    fetch_github_release_plugin_definition,
    download_file,
    parse_cap_file,
    show_open_file_dialog,
    GitHubError,
)


class SourceConfigPage(QWizardPage):
    """Configure the CAP file source."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("CAP File Source")
        self.setSubTitle("Specify where the applet CAP file can be obtained.")

        self._cap_metadata = None  # Single CAP metadata (for local/HTTP)
        self._github_repo_info = None
        # For multiple CAPs: {filename: {"url": str, "metadata": CapMetadata}}
        self._available_caps = {}
        self._source_validated = False  # Track if source has been validated
        self._discovered_plugin = None  # (filename, plugin_data) if found
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Source type selection
        type_group = QGroupBox("Source Type")
        type_layout = QVBoxLayout(type_group)

        self._type_button_group = QButtonGroup(self)

        self._local_radio = QRadioButton("Local File")
        self._http_radio = QRadioButton("HTTP/HTTPS URL")
        self._github_radio = QRadioButton("GitHub Release")

        self._type_button_group.addButton(self._local_radio, 0)
        self._type_button_group.addButton(self._http_radio, 1)
        self._type_button_group.addButton(self._github_radio, 2)

        type_layout.addWidget(self._local_radio)
        type_layout.addWidget(self._http_radio)
        type_layout.addWidget(self._github_radio)

        layout.addWidget(type_group)

        # Stacked widget for source-specific options
        self._options_stack = QStackedWidget()

        # Local file options
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)
        local_layout.addWidget(QLabel("File Path:"))
        path_layout = QHBoxLayout()
        self._local_path_edit = QLineEdit()
        self._local_path_edit.setPlaceholderText("/path/to/applet.cap")
        path_layout.addWidget(self._local_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_local_file)
        path_layout.addWidget(browse_btn)
        local_layout.addLayout(path_layout)

        # Parse button for local files
        parse_local_btn = QPushButton("Extract Metadata from CAP")
        parse_local_btn.clicked.connect(self._parse_local_cap)
        local_layout.addWidget(parse_local_btn)

        local_layout.addStretch()
        self._options_stack.addWidget(local_widget)

        # HTTP URL options
        http_widget = QWidget()
        http_layout = QVBoxLayout(http_widget)
        http_layout.addWidget(QLabel("URL:"))
        self._http_url_edit = QLineEdit()
        self._http_url_edit.setPlaceholderText("https://example.com/applet.cap")
        http_layout.addWidget(self._http_url_edit)

        # Fetch and parse button
        fetch_http_btn = QPushButton("Fetch && Extract Metadata")
        fetch_http_btn.clicked.connect(self._fetch_http_cap)
        http_layout.addWidget(fetch_http_btn)

        http_layout.addStretch()
        self._options_stack.addWidget(http_widget)

        # GitHub release options - simplified to just URL
        github_widget = QWidget()
        github_layout = QVBoxLayout(github_widget)

        github_layout.addWidget(QLabel("GitHub Repository URL:"))
        self._github_url_edit = QLineEdit()
        self._github_url_edit.setPlaceholderText("https://github.com/owner/repo or github.com/owner/repo")
        self._github_url_edit.textChanged.connect(self._on_github_url_changed)
        github_layout.addWidget(self._github_url_edit)

        # Parsed info display
        self._github_info_label = QLabel("")
        self._github_info_label.setStyleSheet("color: gray;")
        github_layout.addWidget(self._github_info_label)

        github_layout.addWidget(QLabel("Asset Pattern (optional):"))
        self._github_pattern_edit = QLineEdit()
        self._github_pattern_edit.setPlaceholderText("*.cap (matches any .cap file)")
        self._github_pattern_edit.setText("*.cap")
        github_layout.addWidget(self._github_pattern_edit)

        # Validate and fetch button
        validate_github_btn = QPushButton("Find CAP Files")
        validate_github_btn.clicked.connect(self._validate_github_source)
        github_layout.addWidget(validate_github_btn)

        # List of available CAP files (shown when multiple found)
        self._cap_list_label = QLabel("Available CAP files (select to include):")
        self._cap_list_label.hide()
        github_layout.addWidget(self._cap_list_label)

        self._cap_list = QListWidget()
        self._cap_list.setMaximumHeight(120)
        self._cap_list.hide()
        self._cap_list.itemChanged.connect(self._on_cap_selection_changed)
        github_layout.addWidget(self._cap_list)

        # Select all / Deselect all buttons
        select_btn_layout = QHBoxLayout()
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.clicked.connect(self._select_all_caps)
        self._select_all_btn.hide()
        select_btn_layout.addWidget(self._select_all_btn)

        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.clicked.connect(self._deselect_all_caps)
        self._deselect_all_btn.hide()
        select_btn_layout.addWidget(self._deselect_all_btn)

        select_btn_layout.addStretch()
        github_layout.addLayout(select_btn_layout)

        # Fetch selected button
        self._fetch_selected_btn = QPushButton("Fetch Selected && Extract Metadata")
        self._fetch_selected_btn.clicked.connect(self._fetch_selected_caps)
        self._fetch_selected_btn.hide()
        github_layout.addWidget(self._fetch_selected_btn)

        github_layout.addStretch()
        self._options_stack.addWidget(github_widget)

        layout.addWidget(self._options_stack)

        # Plugin definition discovery notification (hidden by default)
        self._plugin_found_group = QGroupBox("Plugin Definition Found")
        self._plugin_found_group.setStyleSheet(
            "QGroupBox { background-color: #e8f5e9; border: 1px solid #4caf50; border-radius: 4px; }"
        )
        self._plugin_found_group.hide()
        plugin_found_layout = QVBoxLayout(self._plugin_found_group)

        self._plugin_found_label = QLabel()
        self._plugin_found_label.setWordWrap(True)
        plugin_found_layout.addWidget(self._plugin_found_label)

        plugin_btn_layout = QHBoxLayout()
        self._import_plugin_btn = QPushButton("Import Plugin Definition")
        self._import_plugin_btn.clicked.connect(self._import_discovered_plugin)
        plugin_btn_layout.addWidget(self._import_plugin_btn)

        self._skip_plugin_btn = QPushButton("Continue Manually")
        self._skip_plugin_btn.clicked.connect(self._skip_discovered_plugin)
        plugin_btn_layout.addWidget(self._skip_plugin_btn)

        plugin_btn_layout.addStretch()
        plugin_found_layout.addLayout(plugin_btn_layout)

        layout.addWidget(self._plugin_found_group)

        # Progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Connect radio buttons to stack
        self._type_button_group.buttonClicked.connect(self._on_type_changed)

        # Connect text changes to update completion state
        self._local_path_edit.textChanged.connect(self._on_input_changed)
        self._http_url_edit.textChanged.connect(self._on_input_changed)
        self._github_url_edit.textChanged.connect(self._on_input_changed)

        # Default to GitHub (most common use case)
        self._github_radio.setChecked(True)
        self._options_stack.setCurrentIndex(2)

        layout.addStretch()

    def _on_input_changed(self):
        """Handle input changes to update completion state."""
        # Reset validation when main input changes (URL/path)
        # This is connected to the path/URL fields, not pattern
        self._source_validated = False
        self._available_caps.clear()
        self._discovered_plugin = None
        # Hide CAP list if visible (for GitHub)
        self._cap_list.hide()
        self._cap_list_label.hide()
        self._select_all_btn.hide()
        self._deselect_all_btn.hide()
        self._fetch_selected_btn.hide()
        # Hide plugin discovery notification
        self._plugin_found_group.hide()
        self.completeChanged.emit()

    def _on_cap_selection_changed(self, item):
        """Handle CAP file selection changes."""
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """Check if the page has valid data to proceed."""
        if self._local_radio.isChecked():
            # Local: just need a path
            return bool(self._local_path_edit.text().strip())

        elif self._http_radio.isChecked():
            # HTTP: just need a URL
            return bool(self._http_url_edit.text().strip())

        elif self._github_radio.isChecked():
            # GitHub: need valid URL AND CAP files found/validated
            url = self._github_url_edit.text().strip()
            owner, repo, _ = parse_github_url(url)
            if not owner or not repo:
                return False
            # Must have found CAP files (either single auto-fetched or list shown)
            # and have at least one selected/available
            if not self._available_caps:
                return False
            # If list is visible, check if at least one is selected
            if self._cap_list.isVisible():
                for i in range(self._cap_list.count()):
                    item = self._cap_list.item(i)
                    if item.checkState() == Qt.Checked:
                        return True
                return False
            # Single CAP auto-fetched
            return self._source_validated

        return False

    def initializePage(self):
        """Load existing source config if editing."""
        wizard = self.wizard()
        if not wizard:
            return

        source_type = wizard.get_plugin_value("applet.source.type", "")

        if source_type == "local":
            self._local_radio.setChecked(True)
            self._options_stack.setCurrentIndex(0)
            path = wizard.get_plugin_value("applet.source.path", "")
            if path:
                self._local_path_edit.setText(path)
                # Mark as validated if path exists
                self._source_validated = True
                self.completeChanged.emit()

        elif source_type == "http":
            self._http_radio.setChecked(True)
            self._options_stack.setCurrentIndex(1)
            url = wizard.get_plugin_value("applet.source.url", "")
            if url:
                self._http_url_edit.setText(url)
                # Mark as validated if URL exists
                self._source_validated = True
                self.completeChanged.emit()

        elif source_type == "github_release":
            self._github_radio.setChecked(True)
            self._options_stack.setCurrentIndex(2)
            owner = wizard.get_plugin_value("applet.source.owner", "")
            repo = wizard.get_plugin_value("applet.source.repo", "")
            if owner and repo:
                self._github_url_edit.setText(f"https://github.com/{owner}/{repo}")
            pattern = wizard.get_plugin_value("applet.source.asset_pattern", "")
            if pattern:
                self._github_pattern_edit.setText(pattern)

            # Auto-fetch CAP info for existing GitHub plugins
            if owner and repo:
                # Schedule auto-validation after UI settles
                QTimer.singleShot(500, self._validate_github_source)

    def _on_type_changed(self, button):
        """Handle source type change."""
        button_id = self._type_button_group.id(button)
        self._options_stack.setCurrentIndex(button_id)
        self._status_label.clear()
        # Reset validation when type changes
        self._source_validated = False
        self._available_caps.clear()
        self.completeChanged.emit()

    def _on_github_url_changed(self, text: str):
        """Parse GitHub URL as user types."""
        owner, repo, tag = parse_github_url(text)
        if owner and repo:
            info = f"Owner: {owner}, Repo: {repo}"
            if tag:
                info += f", Tag: {tag}"
            self._github_info_label.setText(info)
            self._github_info_label.setStyleSheet("color: green;")
        elif text.strip():
            self._github_info_label.setText("Could not parse URL")
            self._github_info_label.setStyleSheet("color: red;")
        else:
            self._github_info_label.setText("")

    def _browse_local_file(self):
        """Browse for a local CAP file."""
        def on_file_selected(path: str):
            if path:
                self._local_path_edit.setText(path)
                self._parse_local_cap()

        show_open_file_dialog(
            self,
            "Select CAP File",
            [("CAP Files", "*.cap"), ("All Files", "*.*")],
            on_file_selected,
        )

    def _parse_local_cap(self):
        """Parse local CAP file for metadata."""
        path = self._local_path_edit.text().strip()
        if not path:
            self._status_label.setText("Please enter a file path first.")
            return

        import os
        if not os.path.exists(path):
            self._status_label.setText(f"File not found: {path}")
            return

        self._status_label.setText("Parsing CAP file...")
        metadata = parse_cap_file(path)

        if metadata:
            self._cap_metadata = metadata
            self._show_metadata(metadata)
        else:
            self._status_label.setText("Could not parse CAP file.")

    def _fetch_http_cap(self):
        """Fetch CAP file from HTTP URL and parse it."""
        url = self._http_url_edit.text().strip()
        if not url:
            self._status_label.setText("Please enter a URL first.")
            return

        self._progress_bar.show()
        self._status_label.setText("Downloading CAP file...")

        # Run in background
        QTimer.singleShot(100, lambda: self._do_fetch_http(url))

    def _do_fetch_http(self, url: str):
        """Actually fetch the HTTP file."""
        try:
            path = download_file(url)
            if path:
                metadata = parse_cap_file(path)
                if metadata:
                    self._cap_metadata = metadata
                    self._show_metadata(metadata)
                else:
                    self._status_label.setText("Downloaded but could not parse CAP file.")
            else:
                self._status_label.setText("Failed to download file.")
        except Exception as e:
            self._status_label.setText(f"Error: {e}")
        finally:
            self._progress_bar.hide()

    def _validate_github_source(self):
        """Validate GitHub URL and find available CAP files."""
        url = self._github_url_edit.text().strip()
        owner, repo, tag = parse_github_url(url)

        if not owner or not repo:
            self._status_label.setText("Please enter a valid GitHub URL.")
            self._status_label.setStyleSheet("color: red;")
            return

        pattern = self._github_pattern_edit.text().strip() or "*.cap"

        # Reset state
        self._available_caps.clear()
        self._cap_list.clear()
        self._cap_list.hide()
        self._cap_list_label.hide()
        self._select_all_btn.hide()
        self._deselect_all_btn.hide()
        self._fetch_selected_btn.hide()

        self._progress_bar.show()
        release_info = f"{owner}/{repo}"
        if tag:
            release_info += f" (tag: {tag})"
        self._status_label.setText(f"Checking {release_info} for releases...")
        self._status_label.setStyleSheet("")

        # Run in background
        QTimer.singleShot(100, lambda: self._do_validate_github(owner, repo, pattern, tag))

    def _do_validate_github(self, owner: str, repo: str, pattern: str, tag: str = ""):
        """Find available CAP files in GitHub release."""
        try:
            # Fetch repo info for auto-populating plugin details
            try:
                repo_info = fetch_github_repo_info(owner, repo)
                self._github_repo_info = repo_info
            except GitHubError as e:
                self._progress_bar.hide()
                reply = QMessageBox.warning(
                    self,
                    "Network Error",
                    f"Failed to fetch repository info:\n{e}\n\n"
                    "Would you like to retry or continue without fetching?",
                    QMessageBox.Retry | QMessageBox.Ignore | QMessageBox.Cancel,
                    QMessageBox.Retry,
                )
                if reply == QMessageBox.Retry:
                    QTimer.singleShot(100, lambda: self._do_validate_github(owner, repo, pattern, tag))
                elif reply == QMessageBox.Ignore:
                    # Allow continuing without repo info - user must manually configure
                    self._status_label.setText(
                        "Continuing without repository info. "
                        "You'll need to manually enter all plugin details."
                    )
                    self._status_label.setStyleSheet("color: orange;")
                    self._source_validated = True
                    self.completeChanged.emit()
                return

            # Check for plugin definition in repo or release
            self._discovered_plugin = None
            self._plugin_found_group.hide()

            # Try repo root first, then release assets
            plugin_def = fetch_github_plugin_definition(owner, repo)
            if not plugin_def:
                plugin_def = fetch_github_release_plugin_definition(owner, repo, tag)

            if plugin_def:
                filename, plugin_data = plugin_def
                self._discovered_plugin = plugin_def
                plugin_name = plugin_data.get("name", plugin_data.get("applet", {}).get("name", "Unknown"))
                self._plugin_found_label.setText(
                    f"This repository provides a plugin definition ({filename}).\n"
                    f"Plugin: {plugin_name}\n\n"
                    "You can import it directly or continue configuring manually."
                )
                self._plugin_found_group.show()

            # Fetch ALL release assets matching pattern
            try:
                assets = fetch_github_release_assets(owner, repo, pattern, tag)
            except GitHubError as e:
                self._progress_bar.hide()
                reply = QMessageBox.warning(
                    self,
                    "Network Error",
                    f"Failed to fetch release assets:\n{e}\n\n"
                    "Would you like to retry or continue without CAP file info?",
                    QMessageBox.Retry | QMessageBox.Ignore | QMessageBox.Cancel,
                    QMessageBox.Retry,
                )
                if reply == QMessageBox.Retry:
                    QTimer.singleShot(100, lambda: self._do_validate_github(owner, repo, pattern, tag))
                elif reply == QMessageBox.Ignore:
                    # Allow continuing - the plugin won't have CAP metadata but can be completed
                    self._status_label.setText(
                        "Continuing without CAP file info. "
                        "You'll need to manually enter the AID and other metadata."
                    )
                    self._status_label.setStyleSheet("color: orange;")
                    self._source_validated = True
                    self.completeChanged.emit()
                return

            # Store available CAPs
            for download_url, filename in assets:
                self._available_caps[filename] = {"url": download_url, "metadata": None}

            if len(assets) == 1:
                # Single CAP: auto-download and parse
                download_url, filename = assets[0]
                self._status_label.setText(f"Found: {filename}\nDownloading...")
                self._fetch_and_parse_cap(filename, download_url)
            else:
                # Multiple CAPs: show selection list
                self._cap_list.clear()

                # Get existing variants to determine which to check
                wizard = self.wizard()
                existing_variants = []
                if wizard:
                    variants_data = wizard.get_plugin_value("applet.variants", [])
                    existing_variants = [v.get("filename", "") for v in variants_data]

                for download_url, filename in assets:
                    item = QListWidgetItem(filename)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    # Check if this file was in the saved variants, or check all if no variants saved
                    if existing_variants:
                        item.setCheckState(Qt.Checked if filename in existing_variants else Qt.Unchecked)
                    else:
                        item.setCheckState(Qt.Checked)  # Default all selected for new plugins
                    self._cap_list.addItem(item)

                self._cap_list_label.show()
                self._cap_list.show()
                self._select_all_btn.show()
                self._deselect_all_btn.show()
                self._fetch_selected_btn.show()
                self._status_label.setText(f"Found {len(assets)} CAP files. Select which to include.")
                self._status_label.setStyleSheet("color: green;")
                # Update completion state - CAP files found
                self.completeChanged.emit()

        except Exception as e:
            self._status_label.setText(f"Unexpected error: {e}")
            self._status_label.setStyleSheet("color: red;")
        finally:
            self._progress_bar.hide()

    def _select_all_caps(self):
        """Select all CAP files in the list."""
        self._cap_list.blockSignals(True)  # Avoid multiple signals
        for i in range(self._cap_list.count()):
            item = self._cap_list.item(i)
            item.setCheckState(Qt.Checked)
        self._cap_list.blockSignals(False)
        self.completeChanged.emit()

    def _deselect_all_caps(self):
        """Deselect all CAP files in the list."""
        self._cap_list.blockSignals(True)  # Avoid multiple signals
        for i in range(self._cap_list.count()):
            item = self._cap_list.item(i)
            item.setCheckState(Qt.Unchecked)
        self._cap_list.blockSignals(False)
        self.completeChanged.emit()

    def _fetch_selected_caps(self):
        """Download and parse metadata for selected CAP files."""
        selected = []
        for i in range(self._cap_list.count()):
            item = self._cap_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.text())

        if not selected:
            self._status_label.setText("Please select at least one CAP file.")
            self._status_label.setStyleSheet("color: red;")
            return

        self._progress_bar.show()
        self._status_label.setText(f"Downloading {len(selected)} CAP files...")
        self._status_label.setStyleSheet("")

        QTimer.singleShot(100, lambda: self._do_fetch_selected(selected))

    def _do_fetch_selected(self, filenames: list):
        """Actually fetch and parse selected CAPs."""
        try:
            parsed_count = 0
            for filename in filenames:
                cap_info = self._available_caps.get(filename)
                if not cap_info:
                    continue

                self._status_label.setText(f"Downloading {filename}...")
                path = download_file(cap_info["url"])
                if path:
                    metadata = parse_cap_file(path)
                    cap_info["metadata"] = metadata
                    if metadata:
                        parsed_count += 1

            # Show summary
            if parsed_count == len(filenames):
                self._show_multi_metadata(filenames)
            elif parsed_count > 0:
                self._status_label.setText(
                    f"Parsed {parsed_count}/{len(filenames)} CAP files. "
                    "Some files could not be parsed."
                )
                self._status_label.setStyleSheet("color: orange;")
            else:
                self._status_label.setText("Could not parse any CAP files.")
                self._status_label.setStyleSheet("color: red;")

        except Exception as e:
            self._status_label.setText(f"Error: {e}")
            self._status_label.setStyleSheet("color: red;")
        finally:
            self._progress_bar.hide()

    def _fetch_and_parse_cap(self, filename: str, url: str):
        """Fetch and parse a single CAP file."""
        path = download_file(url)
        if path:
            metadata = parse_cap_file(path)
            if metadata:
                self._available_caps[filename]["metadata"] = metadata
                self._cap_metadata = metadata  # For backward compat
                self._show_metadata(metadata, filename)
            else:
                self._status_label.setText(f"Found {filename} but could not parse CAP metadata.")
                self._status_label.setStyleSheet("color: orange;")
        else:
            self._status_label.setText(f"Found {filename} but download failed.")
            self._status_label.setStyleSheet("color: red;")
        self._progress_bar.hide()

    def _show_multi_metadata(self, filenames: list):
        """Display metadata summary for multiple CAP files."""
        lines = [f"Successfully parsed {len(filenames)} CAP files:"]
        for filename in filenames:
            cap_info = self._available_caps.get(filename, {})
            metadata = cap_info.get("metadata")
            if metadata and metadata.aid:
                aid_display = metadata.applet_aids[0] if metadata.applet_aids else metadata.aid
                lines.append(f"  {filename}: {aid_display}")
            else:
                lines.append(f"  {filename}: (no AID found)")

        self._status_label.setText("\n".join(lines))
        self._status_label.setStyleSheet("color: green;")

        # Mark as validated and update completion state
        self._source_validated = True
        self.completeChanged.emit()

    def _show_metadata(self, metadata, filename: str = ""):
        """Display extracted metadata."""
        lines = []
        if filename:
            lines.append(f"File: {filename}")
        if metadata.aid:
            lines.append(f"Package AID: {metadata.aid}")
        if metadata.applet_aids:
            lines.append(f"Applet AIDs: {', '.join(metadata.applet_aids)}")
        if metadata.version:
            lines.append(f"Version: {metadata.version}")
        if metadata.package_name:
            lines.append(f"Package: {metadata.package_name}")

        if lines:
            self._status_label.setText("Metadata extracted:\n" + "\n".join(lines))
            self._status_label.setStyleSheet("color: green;")
            # Mark as validated and update completion state
            self._source_validated = True
            self.completeChanged.emit()
        else:
            self._status_label.setText("CAP file parsed but no metadata found.")
            self._status_label.setStyleSheet("")

    def get_cap_metadata(self):
        """Get the extracted CAP metadata for use by other pages."""
        return self._cap_metadata

    def _import_discovered_plugin(self):
        """Import the discovered plugin definition directly."""
        if not self._discovered_plugin:
            return

        filename, plugin_data = self._discovered_plugin
        wizard = self.wizard()
        if not wizard:
            return

        # Store the plugin data for the wizard to use
        wizard.set_plugin_data("_imported_plugin", plugin_data)
        wizard.set_plugin_data("_imported_plugin_filename", filename)

        # Show confirmation and close wizard with accept
        from PyQt5.QtWidgets import QMessageBox
        plugin_name = plugin_data.get("name", plugin_data.get("applet", {}).get("name", "Unknown"))

        reply = QMessageBox.question(
            self,
            "Import Plugin",
            f"Import plugin '{plugin_name}' from {filename}?\n\n"
            "This will save the plugin and close the wizard.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # Signal wizard to import and close
            wizard.import_plugin_definition(plugin_data, filename)

    def _skip_discovered_plugin(self):
        """Skip the discovered plugin and continue manually."""
        self._plugin_found_group.hide()
        self._discovered_plugin = None

    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if not wizard:
            return True

        if self._local_radio.isChecked():
            path = self._local_path_edit.text().strip()
            if not path:
                return False
            wizard.set_plugin_data("applet.source.type", "local")
            wizard.set_plugin_data("applet.source.path", path)

        elif self._http_radio.isChecked():
            url = self._http_url_edit.text().strip()
            if not url:
                return False
            wizard.set_plugin_data("applet.source.type", "http")
            wizard.set_plugin_data("applet.source.url", url)

        elif self._github_radio.isChecked():
            url = self._github_url_edit.text().strip()
            owner, repo, tag = parse_github_url(url)
            if not owner or not repo:
                QMessageBox.warning(self, "Invalid URL", "Please enter a valid GitHub repository URL.")
                return False
            wizard.set_plugin_data("applet.source.type", "github_release")
            wizard.set_plugin_data("applet.source.owner", owner)
            wizard.set_plugin_data("applet.source.repo", repo)
            pattern = self._github_pattern_edit.text().strip()
            if pattern and pattern != "*.cap":
                wizard.set_plugin_data("applet.source.asset_pattern", pattern)
            # Store tag for version auto-population
            if tag:
                wizard.set_plugin_data("_github_release_tag", tag)

            # Get selected CAP files
            selected_caps = self._get_selected_caps()
            if not selected_caps:
                QMessageBox.warning(self, "No CAP Files", "Please find and select at least one CAP file.")
                return False

            # Store selected CAPs info for later pages
            wizard.set_plugin_data("_selected_caps", selected_caps)

        # Store metadata for metadata page to use (first one, for backward compat)
        if self._cap_metadata:
            wizard.set_plugin_data("_extracted_metadata", self._cap_metadata)
        elif self._available_caps:
            # Use first available cap with metadata
            for filename, info in self._available_caps.items():
                if info.get("metadata"):
                    wizard.set_plugin_data("_extracted_metadata", info["metadata"])
                    break

        # Store GitHub repo info for intro page to use
        if self._github_repo_info:
            wizard.set_plugin_data("_github_repo_info", self._github_repo_info)

        return True

    def _get_selected_caps(self) -> list:
        """Get list of selected CAP files with their metadata."""
        selected = []

        # If list is visible, use checked items
        if self._cap_list.isVisible():
            for i in range(self._cap_list.count()):
                item = self._cap_list.item(i)
                if item.checkState() == Qt.Checked:
                    filename = item.text()
                    cap_info = self._available_caps.get(filename, {})
                    selected.append({
                        "filename": filename,
                        "url": cap_info.get("url", ""),
                        "metadata": cap_info.get("metadata"),
                    })
        elif self._available_caps:
            # Single CAP was auto-selected
            for filename, info in self._available_caps.items():
                selected.append({
                    "filename": filename,
                    "url": info.get("url", ""),
                    "metadata": info.get("metadata"),
                })

        return selected
