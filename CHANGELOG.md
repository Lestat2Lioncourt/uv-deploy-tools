# Changelog

All notable changes to UV Deploy Tools will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-03

###  Initial Release

#### Features
-  Multi-OS support (Windows and Linux)
-  Automatic Python version fallback (3.14  3.13)
-  Self-contained deployments with embedded Python and UV
-  SSH/SFTP secure transfers with progress tracking
-  Group deployments for multiple servers
-  Package versioning (project-version-date.zip)
-  Separate package and deployment paths
-  Automatic permission fixes for Linux
-  Zero dependencies on target servers

#### Tested On
- Windows Server 2019/2022
- Ubuntu 20.04/22.04 
- WSL2 (Windows Subsystem for Linux)

#### Known Issues
- Python 3.14 standalone builds not yet available for Linux (automatic fallback to 3.13 works)
- ARM architecture (Raspberry Pi) requires manual Python installation

---

Made with  by Laurent Alary (DeTraX)
## [0.2.0] - 2024-12-03

###  New Features
- **GUI Interface**: Complete graphical interface with CustomTkinter
- **Secure Password Input**: Masked password dialog boxes
- **Configuration Editor**: Edit servers.yaml directly from the GUI
- **Windows Notifications**: Desktop notifications on deployment completion
- **Real-time Logs**: Live deployment progress in the interface
- **Group Selection**: Deploy to server groups from the GUI

###  Bug Fixes
- Fixed escape sequence warning in Linux chmod command
- Fixed BOM character encoding issues in output

###  Documentation
- Updated README with GUI usage instructions
- Added GUI screenshot (if available)

