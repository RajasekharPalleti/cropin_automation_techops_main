# 🚀 How to Deploy to Railway

This guide will walk you through deploying your Cropin Automation tool to Railway.app.

## Prerequisites

1.  A GitHub account.
2.  Your project must be pushed to a GitHub repository (which it seems it is!).
3.  A [Railway.app](https://railway.app/) account (Sign up with GitHub).

## Step-by-Step Deployment

1.  **Login to Railway**: Go to [railway.app](https://railway.app/) and log in.
2.  **New Project**: Click **+ New Project**.
3.  **Deploy from GitHub**: Select **Deploy from GitHub repo**.
4.  **Connect Repo**:
    - If asked, grant Railway access to your GitHub repositories.
    - Search for and select your repository: `cropin_automation_techops`.
5.  **Deploy**: Click **Deploy Now**.

## Configuration (Important!)

Railway will automatically detect the `Dockerfile` we just added and start building. However, you might need to ensure the **PORT** is correct.

1.  Click on your new service card in the Railway dashboard.
2.  Go to the **Variables** tab.
3.  You don't usually need to set `PORT` manually (Railway sets it), but our Dockerfile is smart enough to use it.
    - *Note: Our app will listen on whatever port Railway assigns (usually `PORT` env var).*

## Networking

1.  Go to the **Settings** tab.
2.  Scroll down to **Networking**.
3.  Click **Generate Domain**.
    - This will create a public URL (e.g., `cropin-automation-production.up.railway.app`).
    - Use this URL to access your tool!

## Updates

Whenever you modify your code and push to GitHub (e.g., changing `app.js` or `main.py`), Railway will automatically detect the change and redeploy your new version within minutes.
