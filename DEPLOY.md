# MediaFlow Ubuntu Deployment

## 1) Suggested homelab layout

```bash
/srv/services/mediaflow   # this repository
/srv/data/mediaflow       # persistent data (outside repo)
```

## 2) Prepare server directories

```bash
sudo mkdir -p /srv/services /srv/data/mediaflow/{backend-data,outputs,secrets}
sudo chown -R $USER:$USER /srv/services /srv/data/mediaflow
```

## 3) Place code

Clone/copy this repo into:

```bash
/srv/services/mediaflow
```

## 4) Configure env

```bash
cd /srv/services/mediaflow
cp .env.production.example .env
```

Edit `.env` and set at minimum:
- `MEDIAFLOW_JWT_SECRET`
- `MEDIAFLOW_CORS_ORIGINS`
- `HOST_MEDIAFLOW_DATA_ROOT`
- `MEDIAFLOW_API_BASE` (recommended `/api`)

## 5) Create first user and migrate it into SQLite

Create a temporary legacy `/srv/data/mediaflow/backend-data/users.json` migration file:

```json
{
  "users": [
    {
      "username": "admin",
      "password_hash": "PASTE_BCRYPT_HASH"
    }
  ]
}
```

To generate a hash from this repo:

```bash
cd /srv/services/mediaflow/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "from app.core.security import hash_password; print(hash_password('ChangeMe123!'))"
```

Migrate that user into the SQLite users table:

```bash
USERS_FILE=/srv/data/mediaflow/backend-data/users.json \
DB_PATH=/srv/data/mediaflow/backend-data/app.sqlite \
python scripts/migrate_users_json_to_db.py
```

After migration, `users.json` is no longer the runtime source of truth.

Promote the first trusted user to admin so the admin API can manage users:

```bash
sqlite3 /srv/data/mediaflow/backend-data/app.sqlite \
  "UPDATE users SET role='admin', updated_at=datetime('now') WHERE username='admin';"
```

## 6) Start services

The frontend image runs the Vite production build during `docker compose build`
and nginx serves the generated `dist` output.

```bash
cd /srv/services/mediaflow
docker compose --env-file .env up -d --build
```

## 7) Verify

```bash
docker compose ps
curl http://127.0.0.1:18080/health
```

Open frontend:

```text
http://<SERVER_IP>:8080
```

## 8) Stop / update

```bash
docker compose down
docker compose --env-file .env up -d --build
```
