# CareKey — Google Cloud Run & Cloud Scheduler Deployment Guide

This guide walks you through deploying **CareKey** to Google Cloud Run directly from GitHub, configuring Cloud Firestore persistent storage, setting up production secrets, and scheduling the automated reminder escalation ladder with Cloud Scheduler.

---

## 1. Environment Variables Reference

Configure the following variables in the Cloud Run service settings or via Google Secret Manager.

| Variable Name | Purpose | Example Value | Secret? |
|---|---|---|:---:|
| `APP_NAME` | Display name of the application across UI headers and title tags | `CareKey` | **No** |
| `ENVIRONMENT` | Runtime environment mode (`development`, `production`, `test`). In `production`, cookies are strictly `Secure` and the app refuses to start without non-default secrets | `production` | **No** |
| `DEBUG` | Enables verbose stack traces and OpenAPI documentation (`/docs`). Must be `false` in production | `false` | **No** |
| `HOST` | Interface IP for the ASGI server (default `0.0.0.0`) | `0.0.0.0` | **No** |
| `PORT` | Container listen port. Cloud Run automatically sets this to `8080` | `8080` | **No** |
| `SECRET_KEY` | 256-bit cryptographic key used for HMAC session cookies, CSRF tokens, and signed one-tap email action links | `c68fb719a4e8d2e67a030...` | **YES** |
| `TICK_SECRET` | Shared secret header required for `POST /internal/tick` to trigger dose escalation and appointment reminders | `f409ac9b2e71d34...` | **YES** |
| `APP_BASE_URL` | Public HTTPS URL of the deployed Cloud Run service, used for one-tap email actions ("I took it", "Snooze", "Call me") | `https://carekey-xyz-uc.a.run.app` | **No** |
| `REPOSITORY_BACKEND` | Storage persistence adapter: `firestore` for production, `memory` for automated tests | `firestore` | **No** |
| `FIRESTORE_PROJECT_ID` | Google Cloud Project ID hosting Cloud Firestore. If omitted, automatically reads `GOOGLE_CLOUD_PROJECT` on Cloud Run | `carekey-prod-12345` | **No** |
| `GOOGLE_CLOUD_PROJECT` | Standard GCP project identifier automatically injected by Cloud Run metadata | `carekey-prod-12345` | **No** |
| `SMTP_HOST` | Outbound SMTP relay hostname for reminder and escalation emails | `smtp.gmail.com` | **No** |
| `SMTP_PORT` | Outbound SMTP port (`587` for STARTTLS, `465` for SSL) | `587` | **No** |
| `SMTP_USER` | SMTP authentication username / account email | `carekey.alerts@gmail.com` | **No** |
| `SMTP_PASSWORD` | SMTP authentication password or Google App Password | `abcd-efgh-ijkl-mnop` | **YES** |
| `SMTP_FROM_EMAIL` | "From" sender address on outbound emails | `reminders@carekey.local` | **No** |
| `SMTP_USE_TLS` | Enables STARTTLS transport security | `true` | **No** |

---

## 2. GCP Project & Firestore Setup

### Step 2.1 — Enable Required Google Cloud APIs
In the Google Cloud Console, open the [Cloud Shell](https://shell.cloud.google.com/) or execute with `gcloud`:
```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    firestore.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com
```

### Step 2.2 — Initialize Cloud Firestore in Native Mode
1. In the GCP Console, go to **Firestore** (or **Databases**).
2. Click **Create Database**.
3. Select **Firestore Native mode** (do NOT select Datastore mode).
4. Choose a region close to your users (e.g., `asia-south1` or `us-central1`).
5. Click **Create Database**.

> **Note:** CareKey's Firestore adapter performs in-memory predicate filtering for complex queries, avoiding the need for manual composite index definitions.

---

## 3. Deploy from GitHub in Cloud Run Console

### Step 3.1 — Create Cloud Run Service with Continuous Deployment
1. Open the [Google Cloud Run Console](https://console.cloud.google.com/run).
2. Click **Deploy Container** -> **Service**.
3. Select **Continuously deploy from a repository** and click **Set up with Cloud Build**.
4. In the setup panel:
   - **Repository Provider**: Select **GitHub**.
   - Authenticate your GitHub account and authorize Google Cloud Build.
   - **Repository**: Select `premsuchak26/carekey`.
   - **Branch**: `^main$`.
   - **Build Type**: Select **Dockerfile**.
   - **Source location**: `/Dockerfile`.
   - Click **Save**.

### Step 3.2 — Configure Service Settings
1. **Service name**: `carekey`
2. **Region**: Select the same region as your Firestore database (e.g., `asia-south1` or `us-central1`).
3. **CPU allocation and pricing**: *CPU is only allocated during request processing*.
4. **Autoscaling**: Min instances `0`, Max instances `10`.
5. **Authentication**: Select **Allow unauthenticated invocations** (CareKey handles authentication internally via its own role-based session cookies and passcodes).

### Step 3.3 — Configure Environment Variables & Secrets
Under **Container, Networking, Security** -> **Variables & Secrets**:

1. **Add Environment Variables**:
   - `ENVIRONMENT` = `production`
   - `DEBUG` = `false`
   - `REPOSITORY_BACKEND` = `firestore`
   - `FIRESTORE_PROJECT_ID` = `<your-gcp-project-id>`
   - `SMTP_HOST` = `smtp.gmail.com`
   - `SMTP_PORT` = `587`
   - `SMTP_USER` = `your-email@gmail.com`
   - `SMTP_FROM_EMAIL` = `your-email@gmail.com`
   - `SMTP_USE_TLS` = `true`

2. **Add Secrets (from Secret Manager)**:
   - `SECRET_KEY`: Create a random 64-character hex string (`python -c "import secrets; print(secrets.token_hex(32))"`) and mount as environment variable `SECRET_KEY`.
   - `TICK_SECRET`: Create a random 32-character string and mount as environment variable `TICK_SECRET`.
   - `SMTP_PASSWORD`: Store your SMTP/App password in Secret Manager and mount as environment variable `SMTP_PASSWORD`.

3. Click **Create**.
4. Once deployment finishes, copy the generated service URL (e.g., `https://carekey-xyz-uc.a.run.app`).
5. Update the service configuration to set:
   - `APP_BASE_URL` = `https://carekey-xyz-uc.a.run.app`

### Step 3.4 — Grant Firestore Permissions to Cloud Run Service Account
By default, Cloud Run uses the Compute Engine default service account (`<project-number>-compute@developer.gserviceaccount.com`). Ensure it has the `Cloud Datastore User` role:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/datastore.user"
```

---

## 4. Cloud Scheduler Job for Escalation Ladder

CareKey features a stateless reminder and escalation endpoint at `POST /internal/tick`. Cloud Scheduler invokes this every minute.

### Step 4.1 — Create the Scheduler Job in GCP Console
1. Navigate to [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler) in GCP Console.
2. Click **Create Job**.
3. Configure the job details:
   - **Name**: `carekey-escalation-tick`
   - **Region**: Same region as Cloud Run (e.g., `asia-south1` or `us-central1`).
   - **Frequency**: `* * * * *` *(runs every minute)*
   - **Timezone**: `UTC`
4. Configure the Execution Target:
   - **Target type**: `HTTP`
   - **URL**: `https://<YOUR-CLOUD-RUN-URL>/internal/tick`
   - **HTTP method**: `POST`
   - **HTTP Headers**:
     - `Content-Type`: `application/json`
     - `X-Internal-Secret`: `<YOUR-TICK-SECRET>`
   - **Body**: `{}`
5. Configure Retry settings:
   - Max retry attempts: `1`
6. Click **Create**.

### Step 4.2 — Alternative gcloud CLI Command
You can also create the job with a single command:
```bash
gcloud scheduler jobs create http carekey-escalation-tick \
    --location="asia-south1" \
    --schedule="* * * * *" \
    --uri="https://<YOUR-CLOUD-RUN-URL>/internal/tick" \
    --http-method="POST" \
    --headers="Content-Type=application/json,X-Internal-Secret=<YOUR-TICK-SECRET>" \
    --message-body="{}" \
    --time-zone="UTC" \
    --attempt-deadline="30s"
```

---

## 5. Seeding Demo Data in Production / Firestore

To initialize a sample circle with an Elder, Caretaker, and daily medication schedules directly in Firestore:

```bash
# In your local terminal or Cloud Shell
export REPOSITORY_BACKEND=firestore
export FIRESTORE_PROJECT_ID=your-gcp-project-id
export APP_BASE_URL=https://<your-cloud-run-url>

python -m scripts.seed_demo
```
The script will print the generated **Circle Code**, **Elder Owner Passcode**, and **Caretaker Manager Passcode** to the console.
