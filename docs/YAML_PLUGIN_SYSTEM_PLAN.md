# YAML-Based User-Extensible Plugin System

**Branch:** `feature/yaml-plugin-system` (created from `refactor/mvc-architecture`)

**Status:** Nearly Complete - Phases 1-8 Core Done (180 tests passing)

---

## Overview

Create a declarative, YAML-based plugin system allowing users to add custom JavaCard applets without writing Python code. Users can define:
- Applet sources (CAP file URIs)
- Installation parameter UIs
- **Post-installation configuration/management UIs**
- Multi-step workflows (like FIDO attestation)
- Exportable/importable plugin definitions

## Key Requirements

1. **Add applets** via URI (local CAP or HTTP URL)
2. **Generate installation UI** declaratively (dropdowns, text fields, hex editors)
3. **Generate management UI** for post-install configuration (PIN setup, key generation, etc.)
4. **Build workflows** for complex multi-step operations
5. **YAML import/export** for sharing plugins
6. **Visual plugin designer** - GUI wizard to create plugins (generates editable YAML)
7. **State monitoring** - Read and display current applet configuration
8. **Python scripting** - Sandboxed scripts for crypto operations (FIDO attestation, etc.)

## Reference Implementations Studied

| Example                 | Key Patterns                                                       |
| ----------------------- | ------------------------------------------------------------------ |
| NDEF Override           | Multi-tab dialog, hex parameter encoding, real-time updates        |
| FIDO-attestation-loader | Multi-step workflow (CA create → cert create → upload), INI config |
| SmartPGP                | Dynamic AID construction, post-install CLI configuration           |

---

## YAML Schema Design

### Root Structure

```yaml
schema_version: "1.0"

plugin:
  name: "my-applet"
  description: "Description"
  version: "1.0.0"
  author: "Author"

applet:
  source:
    type: "http" | "local" | "github_release"
    url: "https://..."
  metadata:
    name: "Applet Name"
    aid: "D276000124010304"
    aid_construction:  # Dynamic AID (SmartPGP style)
      base: "D276000124010304"
      segments:
        - name: "manufacturer_id"
          length: 2
          source: "field:manufacturer"
    storage:
      persistent: 4096
      transient: 512
    mutual_exclusion: ["FIDO2.cap"]

# Installation UI
install_ui:
  dialog:
    title: "Configure Installation"
    tabs:
      - name: "Basic"
        fields: [...]

# Post-install Management UI
management_ui:
  actions:
    - id: "set_pin"
      label: "Set PIN"
      dialog:
        fields:
          - id: "new_pin"
            type: "password"
            label: "New PIN"
      apdu_sequence:
        - "00200081{pin_length}{pin_hex}"
    - id: "generate_keys"
      label: "Generate Keys"
      workflow: "key_generation"

# Installation parameters
parameters:
  encoding: "template" | "tlv" | "custom"
  template: "8102{read_perm}{write_perm}"

# Workflows for complex operations
workflows:
  key_generation:
    steps:
      - id: "select_applet"
        type: "apdu"
        apdu: "00A4040007{aid}"
      - id: "generate"
        type: "apdu"
        apdu: "0047800002B600"

# Lifecycle hooks
hooks:
  pre_install:
    type: "script"
    script: |
      if card_version < (3, 0, 4):
          raise ValidationError("Requires JC 3.0.4+")
```

### Field Types

| Type         | Widget             | Use Case           |
| ------------ | ------------------ | ------------------ |
| `text`       | QLineEdit          | General text input |
| `password`   | QLineEdit (masked) | PINs, secrets      |
| `dropdown`   | QComboBox          | Fixed choices      |
| `checkbox`   | QCheckBox          | Boolean flags      |
| `hex_editor` | QTextEdit          | Raw hex data       |
| `number`     | QSpinBox           | Integers           |
| `file`       | File picker        | Local files        |

### Conditional Display

```yaml
fields:
  - id: "uri_value"
    type: "text"
    label: "URI"
    show_when:
      field: "record_type"
      equals: "uri"
```

---

## Architecture

### New Modules

```
src/plugins/yaml/
    __init__.py
    schema.py              # Pydantic models for YAML schema
    parser.py              # YAML loading and validation

    ui/
        field_factory.py   # Creates Qt widgets from field defs
        dialog_builder.py  # Builds dialogs from UI specs
        management_panel.py # Post-install management UI
        widgets/
            hex_editor.py  # Custom hex input widget

    encoding/
        encoder.py         # Parameter encoding
        templates.py       # Template processing
        tlv.py             # TLV structure building
        aid_builder.py     # Dynamic AID construction

    workflow/
        engine.py          # Workflow execution
        context.py         # Variable storage
        steps/
            script_step.py # Python snippets
            command_step.py # Shell commands
            apdu_step.py   # Card communication
            dialog_step.py # User input

    adapter.py             # BaseAppletPlugin implementation
    loader.py              # Discovery and loading
```

### Key Classes

| Class               | Responsibility                               |
| ------------------- | -------------------------------------------- |
| `YamlPluginSchema`  | Root dataclass for YAML                      |
| `FieldFactory`      | Maps field types → Qt widgets                |
| `DialogBuilder`     | Assembles install/management dialogs         |
| `ManagementPanel`   | Post-install config UI for installed applets |
| `ParameterEncoder`  | Encodes field values → install params        |
| `AIDBuilder`        | Constructs dynamic AIDs                      |
| `WorkflowEngine`    | Executes multi-step workflows                |
| `YamlPluginAdapter` | Implements `BaseAppletPlugin` interface      |

### Integration Points

1. **Plugin Loading** ([main.py:282-330](main.py#L282-L330))
   - Extend `load_plugins()` to scan for `.yaml` files
   - Create `YamlPluginAdapter` instances

2. **AppletController** ([src/controllers/applet_controller.py](src/controllers/applet_controller.py))
   - Register YAML plugins via `register_plugin()`
   - Add `get_management_actions()` for post-install UI

3. **AppletList Widget** ([src/views/widgets/applet_list.py](src/views/widgets/applet_list.py))
   - Add "Configure" button for installed applets with management_ui

---

## Critical Files to Modify

| File                                                                         | Changes                                |
| ---------------------------------------------------------------------------- | -------------------------------------- |
| [base_plugin.py](base_plugin.py)                                             | Add `get_management_actions()` method  |
| [main.py](main.py)                                                           | Extend plugin loader for YAML          |
| [src/controllers/applet_controller.py](src/controllers/applet_controller.py) | Management action support              |
| [src/views/widgets/applet_list.py](src/views/widgets/applet_list.py)         | Configure button for installed applets |

## New Files to Create

### Core Plugin Engine

| File                                       | Purpose                          | Est. Lines |
| ------------------------------------------ | -------------------------------- | ---------- |
| `src/plugins/yaml/schema.py`               | Pydantic/dataclass schema models | ~250       |
| `src/plugins/yaml/parser.py`               | YAML loading and validation      | ~150       |
| `src/plugins/yaml/ui/field_factory.py`     | Widget creation                  | ~300       |
| `src/plugins/yaml/ui/dialog_builder.py`    | Dialog construction              | ~250       |
| `src/plugins/yaml/ui/management_panel.py`  | Post-install config panel        | ~200       |
| `src/plugins/yaml/ui/state_monitor.py`     | Applet state reading             | ~200       |
| `src/plugins/yaml/encoding/encoder.py`     | Parameter encoding               | ~200       |
| `src/plugins/yaml/encoding/aid_builder.py` | Dynamic AID construction         | ~100       |
| `src/plugins/yaml/workflow/engine.py`      | Workflow execution               | ~300       |
| `src/plugins/yaml/workflow/sandbox.py`     | Script sandboxing                | ~150       |
| `src/plugins/yaml/workflow/steps/*.py`     | Step implementations             | ~400       |
| `src/plugins/yaml/adapter.py`              | BaseAppletPlugin adapter         | ~200       |
| `src/plugins/yaml/loader.py`               | Plugin discovery                 | ~100       |
| **Subtotal Engine**                        |                                  | **~2,800** |

### Visual Plugin Designer

| File                                                    | Purpose                  | Est. Lines |
| ------------------------------------------------------- | ------------------------ | ---------- |
| `src/views/dialogs/plugin_designer/wizard.py`           | Main wizard dialog       | ~300       |
| `src/views/dialogs/plugin_designer/source_page.py`      | CAP source config        | ~150       |
| `src/views/dialogs/plugin_designer/metadata_page.py`    | AID/storage config       | ~200       |
| `src/views/dialogs/plugin_designer/ui_builder.py`       | Drag-drop UI builder     | ~500       |
| `src/views/dialogs/plugin_designer/action_builder.py`   | Management action editor | ~300       |
| `src/views/dialogs/plugin_designer/workflow_builder.py` | Visual workflow editor   | ~400       |
| `src/views/dialogs/plugin_designer/yaml_preview.py`     | YAML preview pane        | ~100       |
| **Subtotal Designer**                                   |                          | **~1,950** |

### Example Plugins

| File                                     | Purpose                  |
| ---------------------------------------- | ------------------------ |
| `plugins/examples/simple_applet.yaml`    | Minimal example          |
| `plugins/examples/ndef_config.yaml`      | NDEF with full UI        |
| `plugins/examples/smartpgp.yaml`         | Dynamic AID + management |
| `plugins/examples/fido_attestation.yaml` | Full workflow example    |

### **Total New Code: ~4,750 lines**

---

## Example YAML Plugins

### 1. Simple Applet (No UI)

```yaml
schema_version: "1.0"
plugin:
  name: "memory-reporter"
  version: "1.0.0"
applet:
  source:
    type: "http"
    url: "https://example.com/memory.cap"
  metadata:
    name: "Memory Reporter"
    aid: "A0000008466D656D01"
```

### 2. SmartPGP with Dynamic AID + Management

```yaml
schema_version: "1.0"
plugin:
  name: "smartpgp"
  version: "1.0.0"

applet:
  source:
    type: "github_release"
    owner: "DangerousThings"
    repo: "flexsecure-applets"
    asset_pattern: "SmartPGPApplet*.cap"
  metadata:
    name: "SmartPGP"
    aid_construction:
      base: "D276000124010304"
      segments:
        - name: "manufacturer"
          length: 2
          source: "field:manufacturer_id"
        - name: "serial"
          length: 4
          source: "field:serial_number"
        - name: "reserved"
          length: 2
          default: "0000"

install_ui:
  form:
    fields:
      - id: "manufacturer_id"
        type: "text"
        label: "Manufacturer ID (4 hex)"
        default: "000A"
        validation:
          pattern: "^[0-9A-Fa-f]{4}$"
      - id: "serial_number"
        type: "text"
        label: "Serial Number (8 hex)"
        default: "00000001"
        validation:
          pattern: "^[0-9A-Fa-f]{8}$"

management_ui:
  actions:
    - id: "change_pin"
      label: "Change User PIN"
      dialog:
        fields:
          - id: "old_pin"
            type: "password"
            label: "Current PIN"
          - id: "new_pin"
            type: "password"
            label: "New PIN"
          - id: "confirm_pin"
            type: "password"
            label: "Confirm PIN"
            validation:
              equals_field: "new_pin"
      apdu_sequence:
        - command: "CHANGE_PIN"
          apdu: "002400{old_pin_hex}{new_pin_hex}"
    - id: "generate_keys"
      label: "Generate Key Pair"
      workflow: "pgp_keygen"

workflows:
  pgp_keygen:
    steps:
      - id: "select"
        type: "apdu"
        apdu: "00A4040007{aid}"
      - id: "verify_admin"
        type: "dialog"
        fields:
          - id: "admin_pin"
            type: "password"
            label: "Admin PIN"
      - id: "auth"
        type: "apdu"
        apdu: "00200083{admin_pin_hex}"
      - id: "generate"
        type: "apdu"
        apdu: "0047800002B600"
        description: "Generating signature key..."
```

### 3. FIDO Attestation Workflow

```yaml
schema_version: "1.0"
plugin:
  name: "fido-attestation"
  version: "1.0.0"

applet:
  source:
    type: "github_release"
    owner: "AmaruEscwororth"
    repo: "vivokey-u2f"
    asset_pattern: "vk-u2f*.cap"
  metadata:
    name: "VivoKey U2F"
    aid: "A0000006472F000101"

install_ui:
  form:
    fields:
      - id: "aaguid"
        type: "text"
        label: "AAGUID (32 hex chars)"
        validation:
          pattern: "^[0-9A-Fa-f]{32}$"

management_ui:
  actions:
    - id: "load_attestation"
      label: "Load Attestation Certificate"
      workflow: "attestation_flow"

workflows:
  attestation_flow:
    steps:
      - id: "create_ca"
        name: "Create Certificate Authority"
        type: "script"
        script: |
          from cryptography.hazmat.primitives.asymmetric import ec
          from cryptography.hazmat.backends import default_backend
          key = ec.generate_private_key(ec.SECP256R1(), default_backend())
          context.set("ca_key", key)
      - id: "create_cert"
        name: "Create Attestation Certificate"
        type: "script"
        depends_on: ["create_ca"]
        script: |
          # Generate attestation cert signed by CA
          ...
      - id: "upload"
        name: "Upload to Card"
        type: "apdu"
        depends_on: ["create_cert"]
        apdu: "00DA006E{cert_der_hex}"
```

---

## Implementation Phases

### Phase 1: Core Schema & Parser [COMPLETE]
- [x] Define `PluginSchema` dataclasses in `schema.py`
- [x] Implement YAML parser with validation
- [x] Add schema version handling
- [x] Unit tests for parsing (17 tests passing)

### Phase 2: Installation UI Generation [COMPLETE]
- [x] Implement `FieldFactory` with all field types
- [x] Build `DialogBuilder` for forms and tabs
- [x] Add validation engine
- [x] Create `HexEditorWidget`
- [x] Unit tests (25 tests passing)

### Phase 3: Parameter Encoding [COMPLETE]
- [x] Template-based encoding
- [x] TLV structure builder
- [x] Dynamic AID construction
- [x] Unit tests (33 tests passing)

### Phase 4: Plugin Adapter & Loader [COMPLETE]
- [x] Implement `YamlPluginAdapter`
- [x] Create `YamlPluginLoader`
- [x] Integration with BaseAppletPlugin interface
- [x] Unit tests (24 tests passing)

### Phase 5: Workflow Engine [COMPLETE]
- [x] Implement `WorkflowContext` for variable storage
- [x] Implement `SandboxedContext` for restricted script access
- [x] Implement `WorkflowEngine` orchestrator with dependency resolution
- [x] Build step types:
  - `ScriptStep` - Python snippets with sandboxing
  - `CommandStep` - Shell commands with allowlist
  - `ApduStep` - Card communication
  - `DialogStep` - User input collection
  - `ConfirmationStep` - Simple confirmations
- [x] Add script sandboxing (whitelist imports, block dangerous operations)
- [x] Add topological sort for step dependencies
- [x] Unit tests (51 tests passing)

### Phase 6: Management UI + State Monitoring [COMPLETE]
- [x] Add `get_management_actions()` to plugin interface
- [x] Add `get_state_readers()` to plugin interface
- [x] Create `ManagementPanel` widget
- [x] Create `ManagementDialog` wrapper
- [x] Implement `StateMonitor` for reading applet state
- [x] Add `StateParser` for APDU response parsing (byte, hex, tlv, ascii)
- [x] Implement `StateDisplayWidget` for showing state values
- [x] Update `YamlPluginAdapter` with management methods
- [x] Unit tests (30 tests passing)

### Phase 7: Visual Plugin Designer [IN PROGRESS]
- [x] Create `PluginDesignerWizard` main dialog with page navigation
- [x] Build `IntroPage` for plugin name, description, version, author
- [x] Build `SourceConfigPage` for CAP source selection (local, HTTP, GitHub)
- [x] Build `MetadataPage` for AID/storage config with validation
- [x] Build `UIBuilderPage` with field editor and live preview
- [x] Build `FieldDefinitionDialog` for adding/editing form fields
- [x] Add `YamlPreviewPane` with syntax highlighting
- [x] Add `PreviewPage` with YAML display and clipboard copy
- [ ] Build `ActionBuilderPage` for management actions (optional)
- [ ] Build `WorkflowBuilderPage` with visual step editor (optional)
- [ ] Add "Create Plugin" button to main UI

### Phase 8: Import/Export & Polish [IN PROGRESS]
- [x] YAML export from UI-designed plugins (via wizard)
- [x] Import validation via YamlPluginParser
- [x] Plugin loader with duplicate detection
- [x] Example plugins:
  - `simple_applet.yaml` - Minimal example
  - `smartpgp.yaml` - Full-featured (dynamic AID, management UI, workflows)
  - `ndef_config.yaml` - NDEF container with management actions
- [ ] User documentation
- [x] Add "Create Plugin" button to main UI integration

---

## Verification Plan

1. **Unit Tests**
   - Schema parsing with valid/invalid YAML
   - Field factory widget creation
   - Parameter encoding (template, TLV)
   - AID construction

2. **Integration Tests**
   - Load example YAML plugins
   - Generate and interact with install dialogs
   - Execute workflows (mocked card)

3. **Manual Testing**
   - Create NDEF plugin via YAML, compare to Python override
   - Create SmartPGP plugin with dynamic AID
   - Test management UI on installed applet

---

---

## Visual Plugin Designer

A GUI wizard that generates YAML, with the option to hand-edit the resulting file.

### Designer Workflow

```
1. Create New Plugin
   └─> Basic Info (name, description, author)

2. Configure Source
   └─> URL input / file picker / GitHub release selector

3. Define Applet Metadata
   └─> AID (static or dynamic builder)
   └─> Storage requirements
   └─> Mutual exclusions (dropdown of known applets)

4. Build Installation UI (drag & drop)
   └─> Field palette (text, dropdown, checkbox, hex, etc.)
   └─> Form/Tab layout builder
   └─> Preview pane (live dialog preview)
   └─> Parameter template editor

5. Build Management UI
   └─> Action editor (label, dialog fields, APDU sequence)
   └─> State readers (APDU → display mapping)
   └─> Workflow builder (step-by-step with dependencies)

6. Export
   └─> Preview YAML
   └─> Save to plugins/ directory
   └─> Export for sharing
```

### Designer Components

| Component              | Purpose                                   |
| ---------------------- | ----------------------------------------- |
| `PluginDesignerWizard` | Main wizard dialog with steps             |
| `SourceConfigPage`     | CAP source configuration                  |
| `MetadataPage`         | AID, storage, exclusions                  |
| `UIBuilderPage`        | Drag-drop form/dialog designer            |
| `ActionBuilderPage`    | Management action editor                  |
| `WorkflowBuilderPage`  | Visual workflow step editor               |
| `YamlPreviewPane`      | Live YAML output with syntax highlighting |

### New Files for Designer

| File                                                    | Purpose              | Est. Lines |
| ------------------------------------------------------- | -------------------- | ---------- |
| `src/views/dialogs/plugin_designer/wizard.py`           | Main wizard          | ~300       |
| `src/views/dialogs/plugin_designer/source_page.py`      | Source config        | ~150       |
| `src/views/dialogs/plugin_designer/metadata_page.py`    | Metadata config      | ~200       |
| `src/views/dialogs/plugin_designer/ui_builder.py`       | Drag-drop UI builder | ~500       |
| `src/views/dialogs/plugin_designer/action_builder.py`   | Action editor        | ~300       |
| `src/views/dialogs/plugin_designer/workflow_builder.py` | Workflow editor      | ~400       |
| `src/views/dialogs/plugin_designer/yaml_preview.py`     | YAML preview         | ~100       |
| **Total Designer**                                      |                      | **~1,950** |

---

## State Monitoring

Read current applet configuration and display it in the management panel.

### State Definition Schema

```yaml
management_ui:
  state_readers:
    - id: "pin_retries"
      label: "PIN Retries Remaining"
      apdu: "00CA00C4"  # GET DATA
      parse:
        type: "byte"
        offset: 0
        display: "{value}/3 attempts"

    - id: "key_status"
      label: "Signature Key"
      apdu: "00CA006E"
      parse:
        type: "tlv"
        tag: "C0"
        display_map:
          "00": "Not generated"
          "01": "RSA 2048"
          "02": "ECC P-256"

    - id: "serial"
      label: "Card Serial"
      apdu: "00CA004F"
      parse:
        type: "hex"
        offset: 10
        length: 8
```

### State Display Components

| Component            | Purpose                                  |
| -------------------- | ---------------------------------------- |
| `StateMonitor`       | Executes state reader APDUs periodically |
| `StateDisplayWidget` | Shows current state with labels          |
| `StateParser`        | Parses APDU responses per schema         |

---

## Security Considerations

### Script Sandboxing

Python scripts run in a restricted environment:

```python
ALLOWED_IMPORTS = [
    "cryptography",      # For key generation, certificates
    "hashlib",           # Hashing
    "struct",            # Binary packing
    "binascii",          # Hex conversion
    "ndef",              # NDEF encoding
    "os.path",           # Path operations only
    "tempfile",          # Temp file creation
]

BLOCKED_OPERATIONS = [
    "open()",            # No arbitrary file access
    "exec()",            # No dynamic execution
    "eval()",            # No eval
    "__import__",        # No dynamic imports
    "subprocess",        # No shell commands (use CommandStep)
]
```

### Command Allowlist

```python
ALLOWED_COMMANDS = [
    "gp",                # GlobalPlatformPro
    "openssl",           # Certificate operations
    "gpg",               # GPG operations (for SmartPGP testing)
]
```

### User Confirmation

- Scripts show preview before execution
- External commands require explicit confirmation
- APDU commands to card show warning for destructive operations

## Sources

- [DangerousThings/fido-attestation-loader](https://github.com/DangerousThings/fido-attestation-loader)
- [SmartPGP JavaCard](https://github.com/github-af/SmartPGP)
- [VivoKey Flex-SmartPGP](https://github.com/VivoKey/Flex-SmartPGP)
