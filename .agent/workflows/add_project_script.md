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
      [Detailed Description about the script to cover the what exactly script will do in not more than three lines]

      Inputs:
      [Input Details]
      """
      ```

2. **Create Excel Template**
    - Create a corresponding Excel file in `sample_templates/` (e.g., `Script.xlsx`).
    - Define all required columns/headers that the script expects.

3. **Configuration & URL Configuralization**
    - Open `app/script_configs.py`.
    - Add a new block inside the `SCRIPT_CONFIGS` dictionary with the script name as the key (e.g., `"New_Script.py": { ... }`).
    - Define the base API URL (`url`, `url2`), the display labels (`label`, `label2`), and any necessary boolean UI flags (e.g., `"show_pr_weather": True`, `"show_address_config": True`).
    - The frontend (`static/js/app.js` and `index.html`) will *automatically* render the required configuration fields based on these flags! No JavaScript or HTML changes are needed.

4. **Final System Verification**
    - Verify the script is listed in the UI.
    - Test "Generate Template" functionality.
    - Perform a test run (or dry run) to ensure the full flow (UI -> Backend -> Script) works as expected.