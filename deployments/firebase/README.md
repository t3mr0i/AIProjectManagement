# Firebase / Google Cloud Storage

Plane can store uploads (attachments, images, avatars, exports) in a Firebase Storage
bucket instead of AWS S3 or MinIO. Firebase Storage buckets are Google Cloud Storage (GCS)
buckets, so the API talks to them with the `google-cloud-storage` client.

How it works:

- The API signs a V4 POST policy; the browser uploads directly to `storage.googleapis.com`.
- Downloads are served through short-lived V4 signed URLs.
- The bucket stays private. Firebase security rules deny all SDK access (`storage.rules`),
  signed URLs are not affected by them.

The database (PostgreSQL), Redis and RabbitMQ are unchanged.

## 1. Firebase project and bucket

```bash
firebase login
firebase projects:list                       # or: firebase projects:create <project-id>
```

In the Firebase console open **Build → Storage → Get started** and pick a location
(e.g. `europe-west3`). The bucket is called `<project-id>.firebasestorage.app`
(older projects: `<project-id>.appspot.com`).

Deploy the deny-all rules from this directory:

```bash
cd deployments/firebase
firebase deploy --only storage --project <project-id>
```

## 2. Service account

Create a service account the API uses to read, write and sign:

```bash
PROJECT=<project-id>
BUCKET=$PROJECT.firebasestorage.app
gcloud iam service-accounts create plane-storage --project $PROJECT
SA=plane-storage@$PROJECT.iam.gserviceaccount.com

# read/write objects in the bucket; bucket metadata for the CORS setup in step 4
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member=serviceAccount:$SA --role=roles/storage.admin
```

Then either:

- **Docker / VM:** create a key and mount it into the `api`, `worker` and `beat-worker` containers:
  ```bash
  gcloud iam service-accounts keys create firebase-service-account.json --iam-account $SA
  ```
  ```yaml
  # docker-compose.yml, for api, worker and beat-worker
  volumes:
    - ./firebase-service-account.json:/secrets/firebase-service-account.json:ro
  ```
- **Cloud Run / GKE / GCE:** attach `$SA` to the service instead of using a key file. Signing then
  goes through the IAM API, so the account needs to be allowed to sign as itself:
  ```bash
  gcloud iam service-accounts add-iam-policy-binding $SA --member=serviceAccount:$SA --role=roles/iam.serviceAccountTokenCreator
  ```

## 3. Environment (`apps/api/.env`)

```bash
STORAGE_BACKEND=gcs
GCS_BUCKET_NAME=<project-id>.firebasestorage.app
GCS_PROJECT_ID=<project-id>
GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json   # omit on Google Cloud
USE_MINIO=0
```

The `AWS_*` variables are ignored with `STORAGE_BACKEND=gcs`, and the `plane-minio` container
is no longer needed.

## 4. CORS

Browsers upload straight to the bucket, so it needs CORS rules for the web app origins.
The API container runs this on start (`create_bucket` delegates to it for GCS); to run it by hand:

```bash
python manage.py configure_gcs_bucket
```

It allows `WEB_URL`, `APP_BASE_URL`, `ADMIN_BASE_URL`, `SPACE_BASE_URL` and `CORS_ALLOWED_ORIGINS`.

## 5. Move existing files

Object keys stay the same, so the database does not change. Copy the MinIO bucket
(default name `uploads`) into the root of the Firebase bucket, e.g. with [rclone](https://rclone.org):

```bash
rclone config create minio s3 provider=Minio endpoint=http://localhost:9000 \
  access_key_id=<AWS_ACCESS_KEY_ID> secret_access_key=<AWS_SECRET_ACCESS_KEY>
rclone config create firebase "google cloud storage" \
  service_account_file=firebase-service-account.json bucket_policy_only=true
rclone copy minio:uploads firebase:<project-id>.firebasestorage.app --progress
```

## 6. Sign in with Google

Plane already ships a Google OAuth provider, it only needs a client from the same Google project:

1. Google Cloud console → **APIs & Services → OAuth consent screen**, then
   **Credentials → Create credentials → OAuth client ID → Web application**.
2. Authorized redirect URI: `https://<your-domain>/auth/google/callback/`
3. In the admin app (`/god-mode`) → **Authentication → Google**, enter client ID and secret,
   or set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `IS_GOOGLE_ENABLED=1` in `apps/api/.env`.
