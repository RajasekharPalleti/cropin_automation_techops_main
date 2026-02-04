# Hosting on Google Cloud Platform (GCP)

This guide provides step-by-step instructions to host your generic python script runner on **Google Cloud Run**. Cloud Run is a fully managed platform that automatically scales your stateless containers.

## 1. Prerequisites

Before you begin, ensure you have:
1.  **GCP Project**: Created a project in the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Billing Enabled**: Linked a billing account to your project.
3.  **gcloud CLI**: Installed and initialized the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).

## 2. Initial Setup (One-Time)

Run the following commands in your terminal to set up your environment. Replace `YOUR_PROJECT_ID` with your actual GCP project ID.

```bash
# 1. Login to Google Cloud
gcloud auth login

# 2. Set your project context
gcloud config set project YOUR_PROJECT_ID

# 3. Enable necessary APIs (Cloud Run and Cloud Build)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

## 3. Deploy to Cloud Run

We will use the "deploy from source" feature, which builds your Docker container and deploys it in one step.

Run this command in the project root directory:

```bash
gcloud run deploy cropin-automation \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi
```

### Explanation of Flags:
- `--source .`: Uses the `Dockerfile` in the current directory to build the image.
- `--platform managed`: Uses the fully managed Cloud Run platform.
- `--region us-central1`: Deploys to the US Central region (change if needed).
- `--allow-unauthenticated`: Makes the application accessible publicly (remove this if you want to restrict access).
- `--memory 1Gi`: Allocates 1GB of RAM (adjust based on your script needs, e.g. `2Gi`).

## 4. Accessing Your App

Once the deployment completes, the terminal will output a **Service URL**:

```text
Service URL: https://cropin-automation-xxxxx-uc.a.run.app
```

Click the URL to access your live application.

## ⚠️ Important Considerations

### Ephemeral Storage
Cloud Run containers are **stateless**. Files stored in `uploads/` or `outputs/` will **disappear** if the container restarts or scales down.
- **Impact**: If a user uploads a file, runs a script, and downloads the result immediately, it will work fine.
- **Risk**: If the process takes too long or the user waits to download, the file might vanish.
- **Solution**: For production persistence, modify the app to upload files to **Google Cloud Storage (GCS)** instead of the local filesystem.

### Timeouts
Cloud Run has a default timeout of **5 minutes** (300 seconds) for requests.
- If your scripts (e.g., `Bulk_Delete_Farmers.py`) take longer than 5 minutes to run, the request will be terminated.
- **Fix**: You can increase the timeout up to 60 minutes using the `--timeout` flag (e.g., `--timeout 3600`).
