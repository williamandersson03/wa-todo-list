# WA TODO

A small production-ready TODO web app built with FastAPI, Jinja2, and SQLite.

## Features

- Session-cookie authentication (server-side sessions)
- CSRF protection on all state-changing routes
- Argon2 password hashing
- Login rate limiting
- Per-user TODO ownership checks
- SQLite with WAL mode and indexes
- Category parser for:
  - `P###` (project)
  - `K###` (K project)
  - `M######` (machine)
  - `§CustomCategory` (takes precedence over P/K/M)

---

## Run locally (recommended for development)

### 1) Prerequisites

- Python 3.11+ (3.10 may also work in many environments)
- `pip`

### 2) Clone and enter project

```bash
git clone <your-repo-url>
cd wa-todo-list
```

### 3) Create environment file

```bash
cp .env.example .env
```

For local HTTP testing, set this in `.env`:

```env
SESSION_SECURE_COOKIE=false
```

> Why: secure cookies are not sent over plain `http://localhost`.

### 4) Install dependencies

```bash
pip install -r requirements.txt
```

### 5) Start app

```bash
make run
```

App will be available at:

- http://localhost:8000

### 6) Verify core flow manually

1. Open `/register` and create an account
2. You should be redirected to `/app`
3. Add multi-line TODO input, e.g.:
   ```
   P842 prepare report
   §Office water the plants
   buy coffee
   ```
4. Toggle a TODO as done
5. Delete a done TODO
6. Use “Clear completed” in a category
7. Logout

---

## Run tests

```bash
make test
```

---

## Run with Docker Compose + Caddy

### 1) Prepare `.env`

```bash
cp .env.example .env
```

Set at least:

```env
DOMAIN=localhost
SESSION_SECURE_COOKIE=true
```

### 2) Start stack

```bash
make compose-up
```

This starts:

- `app` (FastAPI)
- `caddy` (reverse proxy)

### 3) Stop stack

```bash
make compose-down
```

---

## Common issues

### "I can register but seem logged out immediately"

Most often caused by `SESSION_SECURE_COOKIE=true` while using HTTP locally.

Fix in `.env` for local development:

```env
SESSION_SECURE_COOKIE=false
```

### "docker compose fails due to env/domain"

Make sure `.env` exists and includes `DOMAIN`.

---

## Useful commands

```bash
make run          # start dev server
make test         # run pytest
make compose-up   # start docker stack
make compose-down # stop docker stack
```
