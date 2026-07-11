# Publish Back to God AOG

This Flask app needs a Python hosting service because it has login, SQLite data, uploads, live recordings, messages, and server-side routes.

## Recommended Option: Render

### Before You Start

Create accounts for:

- GitHub
- Render

You will publish the app by putting the project on GitHub, then connecting that GitHub repository to Render.

### Step 1: Put The Project On GitHub

1. Go to GitHub and create a new repository.
2. Keep the repository private while the app is still being prepared.
3. Upload this project folder to the repository.
4. Do not upload the local `instance/` folder. It contains local database and credential files.

### Step 2: Create The Render Service

1. Open Render.
2. Choose **New** then **Blueprint** if you want Render to read `render.yaml`.
3. Connect your GitHub repository.
4. Render should detect the `render.yaml` file and create the web service.

If you choose **New Web Service** instead of Blueprint, enter these manually:

   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180 --access-logfile - --error-logfile -`

### Step 3: Add Persistent Storage

Add a persistent disk mounted at:

```text
/var/data
```

This is important because the app stores SQLite data, profile pictures, email outbox logs, API keys, and live recordings under that folder.

### Step 4: Set Environment Variables

Set these environment variables:

   - `SECRET_KEY`: a long random value
   - `ENABLE_QUICK_LOGIN`: `0`
   - `SESSION_COOKIE_SECURE`: `1`
   - `INSTANCE_DIR`: `/var/data`
   - `DATABASE_PATH`: `/var/data/back_to_god.sqlite3`
   - `INITIAL_SUPER_ADMIN_NAME`: `Back to God Super Admin`
   - `INITIAL_SUPER_ADMIN_EMAIL`: your admin email address
   - `INITIAL_SUPER_ADMIN_PASSWORD`: a strong temporary password

Add SMTP settings if you want real emails. Without SMTP, emails are written to `/var/data/email-outbox.log`.

### Step 5: Deploy

1. Click **Deploy**.
2. Wait for Render to finish building.
3. Open the Render URL.
4. Sign in with the initial super admin email and password you set.
5. Change the password on first login.
6. Create proper users.
7. Keep quick login disabled in production.

### Step 6: After First Login

For better safety:

- Remove or rotate `INITIAL_SUPER_ADMIN_PASSWORD` after the first successful login.
- Configure SMTP so new users receive temporary passwords by email.
- Keep the app private until you are ready for real members.

## Docker Option

The included `Dockerfile` runs the app with Gunicorn and stores SQLite data at `/var/data`.

Required production environment variables:

```text
SECRET_KEY=replace-with-a-long-random-secret
ENABLE_QUICK_LOGIN=0
SESSION_COOKIE_SECURE=1
INSTANCE_DIR=/var/data
DATABASE_PATH=/var/data/back_to_god.sqlite3
```

Mount `/var/data` as persistent storage. Without a persistent disk, users, messages, uploads, and videos can be lost when the host restarts.

## Important Production Notes

- Keep `instance/` private. It contains the database, generated credentials, email outbox, and API key files.
- Do not publish with `SECRET_KEY=change-this-before-production`.
- Disable quick login in production with `ENABLE_QUICK_LOGIN=0`.
- SQLite is acceptable for this first hosted version, but use one Gunicorn worker with threads to reduce lock risk.
- When the app becomes heavily used, move the database and media storage to managed services.
