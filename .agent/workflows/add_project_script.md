---
description: Workflow to follow when adding a new automation script to the project.
---

Follow these steps strictly whenever adding a new script:

1. **Code Review & Adaptation**
    - Analyze the provided script logic.
    - Ensure it fits the project structure (`run` function signature).
    - functionality should use the `token` from `config` for authentication.
    - delay_time should be used for time delay
    - Adapt hardcoded values to be configurable.
    - Add default URL if the url is not from configuration.
    - Add log_callback as other scripts.
    - Add Author details as Rajasekhar Palleti
    - Add log that shows which rows is executing
    - **Add Docstring**: Ensure the script has a structured docstring at the top of the file:
      ```python
      """
      [Short Description about the script to cover the what exactly script will do]

      Inputs:
      [Input Details]
      """
      ```

2. **Create Excel Template**
    - Create a corresponding Excel file in `sample_templates/` (e.g., `Script.xlsx`).
    - Define all required columns/headers that the script expects.

3. **Configuration & URL Configuralization**
    - Modify `app/main.py` to register the script in `default_configs`.
    - Extract API URLs and make them configurable (add to `url`, `url2`, etc., in the config dictionary).
    - Ensure `static/js/app.js` handles the new script selection to populate the configuration fields (Primary URL, Secondary URL, etc.).
    - If new inputs are needed, add them to `static/index.html` and update `app.js` to hide/show them.

4. **Final System Verification**
    - Verify the script is listed in the UI.
    - Test "Generate Template" functionality.
    - Perform a test run (or dry run) to ensure the full flow (UI -> Backend -> Script) works as expected.