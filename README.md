<div align="center">

#  UV Deploy Tools

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![UV](https://img.shields.io/badge/UV-latest-green)](https://github.com/astral-sh/uv)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](https://github.com/Lestat2Lioncourt/uv-deploy-tools)

</div>


> **Note**: This tool is built around [UV](https://github.com/astral-sh/uv), the modern Python package manager. 
> If you're not familiar with UV yet, it's a blazing-fast replacement for pip/pip-tools/pipenv/poetry that handles Python installations, virtual environments, and dependencies.

A powerful Python deployment automation tool that packages and deploys Python projects to remote servers without internet access, using UV package manager and embedded Python interpreters.

##  Features

- ** Offline Deployment**: Deploy Python projects to servers without internet access
- ** Self-Contained Packages**: Bundles UV, Python interpreter, and all dependencies
- ** Cross-Platform**: Supports both Windows and Linux servers
- ** Smart Fallback**: Automatically uses the closest available Python version
- ** Group Deployment**: Deploy to multiple servers simultaneously
- ** Package Management**: Organized package versioning with semantic naming
- ** SSH-based**: Secure deployment via SSH/SFTP
- ** Zero Server Setup**: No Python installation required on target servers

##  Prerequisites

### On Your Development Machine
- Windows or Linux with Python 3.10+
- [UV package manager](https://github.com/astral-sh/uv) installed
- SSH client (OpenSSH on Windows 10/11, native on Linux)

### On Target Servers
- SSH server running (OpenSSH)
- Basic shell access (cmd/PowerShell on Windows, bash on Linux)
- That's it! No Python, pip, or other tools needed

##  Installation

1. **Clone the repository**
```ash
git clone https://github.com/Lestat2Lioncourt/uv-deploy-tools.git
cd uv-deploy-tools
```

2. **Install UV (if not already installed)**
```ash
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. **Install dependencies**
```ash
uv venv
uv sync
```

##  Configuration

Edit `configs/servers.yaml` to define your servers:

```yaml
servers:
  production:
    host: 192.168.1.100
    port: 22
    os: windows
    user: deploy
    package_path: D:`packages        # Where to upload packages
    deploy_path: C:`apps             # Where to install apps
    cleanup_package: true             # Remove package after deployment

  staging-linux:
    host: staging.example.com
    port: 22
    os: linux
    user: ubuntu
    package_path: /tmp/packages
    deploy_path: /opt/apps
    cleanup_package: false

groups:
  all-prod: [production, backup-prod]
  testing: [staging-linux, test-windows]

defaults:
  port: 22
  os: windows
  cleanup_package: true
  python_version: "3.12"
```

##  Usage

### Basic Commands

**Deploy a project to a single server:**
```ash
uv run python deploy.py -p my-project -s production
```

**Deploy to a group of servers:**
```ash
uv run python deploy.py -p my-project -g all-prod
```

**List available projects:**
```ash
uv run python deploy.py --list-projects
```

**List configured servers:**
```ash
uv run python deploy.py --list-servers
```

**List created packages:**
```ash
uv run python deploy.py --list-packages
```

### Project Structure

Your Python projects should follow this structure:
```
my-project/
 main.py              # Entry point (required)
 pyproject.toml       # Project metadata (required)
 .python-version      # Python version (optional, e.g., "3.12")
 requirements.txt     # Dependencies (optional)
 src/                 # Your source code
```

##  Deployment Process

1. **Package Creation**
   - Detects project Python version
   - Downloads Python interpreter if needed (with automatic fallback)
   - Bundles UV package manager
   - Creates platform-specific scripts (.bat for Windows, .sh for Linux)
   - Compresses everything into a versioned ZIP

2. **Transfer**
   - Connects via SSH
   - Creates necessary directories
   - Transfers package via SFTP
   - Shows progress with transfer speed

3. **Installation**
   - Extracts package
   - Sets proper permissions (Linux)
   - Creates virtual environment
   - Tests the deployment

##  Advanced Features

### Python Version Fallback
If the requested Python version isn't available for the target platform, UV Deploy Tools automatically selects the closest lower version:
- Requested: Python 3.14 (not available for Linux standalone)
- Fallback: Python 3.13 (automatically selected and downloaded)

### Package Naming Convention
Packages are automatically named with semantic versioning:
```
project-name-v1.2.3-20241203.zip
```

### Multiple Deployment Paths
- **package_path**: Temporary location for package upload
- **deploy_path**: Final installation directory
- **cleanup_package**: Option to keep or remove packages after deployment

##  Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup
```ash
# Clone your fork
git clone https://github.com/Lestat2Lioncourt/uv-deploy-tools.git
cd uv-deploy-tools

# Create a virtual environment
uv venv
uv sync

# Make your changes and test
uv run python deploy.py --help
```

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

##  Acknowledgments

- [UV](https://github.com/astral-sh/uv) - The blazing-fast Python package manager
- [Paramiko](https://www.paramiko.org/) - SSH connectivity
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal output
- [Click](https://click.palletsprojects.com/) - Command-line interface

##  Project Status

 **Production Ready** - Successfully tested on:
- Windows Server 2019/2022
- Ubuntu 20.04/22.04
- WSL2

##  Known Issues

- Python 3.14 standalone builds not yet available for Linux (automatic fallback to 3.13)
- ARM architecture (Raspberry Pi) requires manual Python installation

##  Support

For issues, questions, or suggestions:
- Open an issue on [GitHub](https://github.com/Lestat2Lioncourt/uv-deploy-tools/issues)
- Check existing issues before creating a new one

---

**Made with  by Laurent Alary (DeTraX)** | **Powered by UV **




