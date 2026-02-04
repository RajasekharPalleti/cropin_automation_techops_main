# Cropin Automation TechOps

This project is an automation utility designed for Cropin TechOps to streamline various API-based tasks using a user-friendly web interface.

## Features

-   **Script Execution**: Run Python automation scripts (`AddTags`, `UpdateFarmerName`, etc.) directly from the browser.
-   **Excel Integration**: Upload Excel files as input and download processed results with status columns.
-   **Live Console**: View real-time logs and execution feedback directly in the web UI.
-   **Dynamic Configuration**: Authentication and API URLs are configurable via the UI.
-   **Searchable Dropdown**: Easily find and select automation scripts.
-   **Template Management**: Download sample Excel templates for each script.

## Setup & Installation

Follow these steps to set up the project on a new machine.

### 1. Clone the Repository
create a folder in your local machine and clone the repository into that folder
```bash
git clone https://github.com/RajasekharPalleti/cropin_automation_techops.git
cd cropin_automation_techops
```

### 2. Install Dependencies
Ensure you have Python installed, then run:
```bash
pip install -r requirements.txt
```

### 3. Setup Configuration
_Important: Since credential files are private, they are not included in the git repository._

1.  Create the `json_config/` directory if it doesn't exist.
2.  Follow the guide in `markdown_files/GDrive_Setup_Instructions.md` to generate your `client_secret.json`.
3.  Place the `client_secret.json` file inside `json_config/`.

### 4. Run the Application
You can use the provided scripts to start and stop the server easily on both **Windows** and **macOS/Linux** using the scripts in `batch_scripts/`.

**Start Server:**
- **Windows**: Double-click `batch_scripts/run_server.bat`
- **macOS/Linux**: Run `./batch_scripts/run_server.bat` in terminal

**Stop Server:**
- **Windows**: Double-click `batch_scripts/stop_server.bat`
- **macOS/Linux**: Run `./batch_scripts/stop_server.bat` in terminal

**Restart Server:**
- **Windows**: Double-click `batch_scripts/restart_server.bat`
- **macOS/Linux**: Run `./batch_scripts/restart_server.bat` in terminal

The application will be accessible at: `http://127.0.0.1:4444`
## Usage

1.  **Select Script**: Choose the automation script you want to run from the dropdown.
2.  **Download Template**: If needed, click "Get Template" to see the expected Excel format.
3.  **Configure**: Enter the API URL (if different from default), other required parameters if available and Authentication details.
4.  **Upload Input**: Drag and drop your filled Excel file.
5.  **Run**: The script will execute, showing live logs in the console.
6.  **Download Result**: Once finished, the output file will verify automatically.

## Project Structure

-   `app/`: Core application logic and scripts.
    -   `main.py`: FastAPI server and API endpoints.
    -   `scripts/`: Folder for automation scripts.
-   `static/`: Frontend assets (HTML, CSS, JS).
-   `sample_templates/`: Excel templates for users.
-   `uploads/` & `outputs/`: Temporary directories for processing files.
-   `batch_scripts/`: Execution scripts for running the server and ngrok.
-   `markdown_files/`: Documentation and guides.
-   `json_config/`: Configuration files (credentials).
