# Global Platform GUI
A quick attempt at GUI wrapper for [Global Platform Pro](https://github.com/martinpaljak/GlobalPlatformPro) by 
[Martin Paljak](https://github.com/martinpaljak) geared towards the [flexSecure](https://dngr.us/flexsecure).
Tons of credit go to [@Stargate01](https://github.com/stargate01), [@GrimEcho](https://forum.dangerousthings.com/u/grimecho/summary), and [@pilgrimsmaster](https://forum.dangerousthings.com/u/pilgrimsmaster/summary).

Looking for more information? Checkout the [flexSecure repo docs](https://github.com/DangerousThings/flexsecure-applets/tree/master/docs).

> [!CAUTION]
> DO NOT USE ON APEX DEVICES OR THOSE OTHERWISE CONFIGURED WITH NON-DEFAULT PASSWORDS--THE DEVICE WILL BE BRICKED!

Rebooted from Tkinter to PyQt. Still early.

Features:
- Decodes AIDs to names of flexSecure apps
- Installs the latest version of an app
- Can uninstall apps
- Will probably break at random
- Supports NDEF Installation
  - Container Size
  - Permissions
  - Initial Record (Text only atm)

Want a feature? Feel free to submit a PR.

<img src="screenshot.png" width=350/>

## Known Issues
- Reader selection hasn't been tested
- Sometimes throws an error if a card is present on app start

## Quick Start

### Binary

Check the latest release

### From Source:

- Don't have Python? Get it.
- Download and extract or clone the repo
- Install the required packages

Install

```bash
pip install "requirements.txt" 
```

Run

```bash
python main.py
```
