---
description: Rule for managing Python dependencies and Dockerfile updates.
---
# Dependency Management Rule

Whenever a new Python dependency is introduced (such as Playwright, Pandas, etc.):
1. **Always** add it to `requirements.txt`. Ensure that it is added on a new line and does not accidentally merge with the previous line.
2. **System Dependencies**: If the new dependency requires system-level packages, browser binaries, or other non-Python OS requirements (for example, `playwright install chromium` or `apt-get install` packages):
   - You **MUST** update the `Dockerfile` to include the necessary installation commands.
   - You **MUST** update any relevant startup/deployment scripts (e.g., `batch_scripts/run_server.bat`, `start.sh`) if applicable.
3. **Environment Awareness**: For browser automation or UI-related libraries, ensure they are configured to run headlessly if deployed to a cloud environment (e.g., Render, Railway, AWS) without a display.
