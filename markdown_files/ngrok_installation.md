# Remote Access Guide

This project allows you to access the automation server from other devices (remote laptops, mobile, etc.) using **ngrok**.

## 🚀 Quick Start

### 1. Setup Auth Token (One Time Setup)
Before starting, you need to authenticate your ngrok agent.
1.  Go to your [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken).
2.  Copy your Authtoken.
3.  Open a terminal in this project folder.
4.  Run the following command (replace `<YOUR_TOKEN>` with your actual token):
    ```bash
    ngrok config add-authtoken <YOUR_TOKEN>
    ```
    *Or on Windows if not in PATH:*
    ```bash
    .\ngrok.exe config add-authtoken <YOUR_TOKEN>
    ```

### 2. Start the Server
First, ensure your local web server is running.
- **Windows**: Double-click `run_server.bat`
- **Mac/Linux**: Run `bash run_server.bat`

### 3. Start the Tunnel (ngrok)
This creates the "bridge" to the internet.
- **Windows**: Double-click `run_ngrok.bat`
- **Mac/Linux**: Run `bash run_ngrok.bat`

> **Note**: A terminal window will open. **Keep it open!** If you close it, the remote link will stop working.

### 4. Access Remotely
Look at the ngrok window. It will show a URL line like:
`Forwarding https://random-name.ngrok-free.app -> http://localhost:4444`

- Copy the **`https://...`** link.
- Open it on any other device to use the app.

---

## 🛠️ Management Scripts

We have created several helper scripts to make this easy:

| Script Filename | Function |
| :--- | :--- |
| **`run_ngrok.bat`** | Starts the remote tunnel. Shows you the public URL. |
| **`restart_ngrok.bat`** | Restarts the tunnel (gets a new URL). Useful if the connection gets stuck. |
| **`stop_ngrok.bat`** | **Forcefully kills** all background ngrok processes. Use this if you get an "already online" error. |

---

## ⚠️ Troubleshooting

**"The endpoint is already online" Error**
This means a "ghost" ngrok process is running in the background.
- **Fix**: Run `stop_ngrok.bat` to clear it, then try `run_ngrok.bat` again.

**"ngrok is not recognized" Error**
- Ensure `ngrok.exe` is inside this project folder, OR installed in your system path.
