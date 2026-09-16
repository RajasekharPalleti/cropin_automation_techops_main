---
description: Rule for writing cross-platform deployment and startup scripts.
---
# Cross-Platform Scripting Rule

The Cropin Automation Server is deployed in two distinctly different environments:
1. **Local QA Environment:** Windows using `.bat` files (`restart_server.bat`, `run_server.bat`, etc.).
2. **Cloud Environment:** Render (Ubuntu Linux) using shell scripts (`start.sh`, `Dockerfile`, etc.).

Whenever you are tasked with modifying the deployment, server startup, or environment initialization logic, you MUST:
- **Update Both OS Scripts:** If you add a feature like environment variable checking, dependency installation, or background task scheduling, ensure it is added to **both** the `.bat` files (for Windows) and the `.sh` or `Dockerfile` scripts (for Linux).
- **Paths:** Always use standard `pathlib` in Python rather than string concatenation to prevent `\` vs `/` bugs when the app is run across different OSes.
- **Port Management:** Be aware that Windows uses `netstat`/`taskkill` for port management, whereas Linux uses `lsof`/`kill`. If you modify port killing logic, verify the syntax for both OSes.
