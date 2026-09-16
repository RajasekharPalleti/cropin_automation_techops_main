---
description: Guide for developing browser automation scripts using Playwright in this project.
---
# Playwright Automation Skill

When building new automation tasks that interact with web interfaces (such as `app/automation.py`), you must adhere to these project-specific standards:

1. **Async Playwright**
   - Always use `playwright.async_api`.
   - Ensure the function is strictly `async def` and `await` is used for all page actions.

2. **Headless Execution Compatibility**
   - The project is deployed both locally (Windows) and on cloud servers (Render - Linux).
   - Cloud servers do not have a graphical display (X11/Wayland). 
   - You MUST dynamically set `headless=True` when running on a server.
   - Use the environment variable `RENDER="true"` to check if the app is deployed in the cloud:
     ```python
     is_server = os.environ.get("RENDER") == "true"
     browser = await p.chromium.launch(headless=is_server)
     ```

3. **Status Callbacks**
   - Automation functions must accept an `update_callback` parameter (an async function).
   - Periodically call `await update_callback("Current status message...")` so the backend can push real-time updates to the UI.

4. **Resource Management**
   - Always close the `browser` before returning from the function or exiting due to an error.
   - Use `async with async_playwright() as p:` to automatically manage the Playwright context lifecycle.
