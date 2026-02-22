---
name: privateapp
description: "Personal PWA dashboard server. Use this skill when building, modifying, or adding apps to PrivateApp."
---

# PrivateApp — Development Guide

## Overview

PrivateApp is a personal PWA dashboard built with FastAPI (backend) + React/Vite (frontend). Apps are self-contained plugins inside the `apps/` directory.

## Adding a New App

### 1. Create the app directory

```
apps/my-app/
├── app.json              # App metadata (required)
├── backend/
│   └── routes.py         # FastAPI router (required)
└── frontend/
    ├── index.html         # HTML entry point
    ├── package.json       # Node dependencies
    ├── tsconfig.json      # TypeScript config
    ├── vite.config.ts     # Vite config (set base path)
    └── src/
        ├── main.tsx       # React entry point
        ├── App.tsx        # Main component
        └── index.css      # Self-contained styles
```

### 2. app.json — App metadata

```json
{
  "id": "my-app",
  "name": "My App",
  "shortcode": "myapp",
  "icon": "🔧",
  "version": "1.0.0",
  "description": "What this app does",
  "author": "your-name",
  "builtin": true,
  "frontend_route": "/app/my-app"
}
```

**Fields:**
- `id` — Directory name, must match the folder name in `apps/`
- `name` — Display name shown on the home screen
- `shortcode` — **Must be unique across all apps.** Determines the API mount point: `/api/app/{shortcode}/`. Keep it short, lowercase, no hyphens (e.g. `myapp`, `sysmon`, `files`). Two apps with the same shortcode will conflict.
- `icon` — Emoji shown on the home screen grid
- `builtin` — `true` for apps bundled with PrivateApp, `false` for add-ons
- `frontend_route` — URL path where the SPA is mounted (usually `/app/{id}`)

### 3. Backend — routes.py

Create a FastAPI router. It gets mounted at `/api/app/{shortcode}/`.

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/stats")
async def my_stats():
    return {"status": "ok", "items": 42}

@router.get("/items")
async def list_items():
    return {"items": [...]}
```

**Rules:**
- Export a `router = APIRouter()` — the app loader imports it automatically
- Routes are relative — `@router.get("/stats")` becomes `/api/app/myapp/stats`
- Use `async def` for all route handlers
- Import only stdlib + packages in the server's venv
- For database access, use `sqlite3` directly (no ORM)
- Return plain dicts — FastAPI handles JSON serialization

### 4. Frontend — React SPA

Each app is a standalone React SPA with its own dependencies.

**package.json:**
```json
{
  "name": "my-app",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "~5.6.3",
    "vite": "^5.4.11"
  }
}
```

**vite.config.ts** — IMPORTANT: set `base` to your app's frontend route:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/my-app/',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 5174,
    proxy: { '/api': 'http://localhost:8800' },
  },
})
```

**src/App.tsx:**
```tsx
import { useEffect, useState } from 'react'

const API = import.meta.env.VITE_API_BASE || '/api/app/myapp'

export default function App() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setData)
  }, [])

  return (
    <div className="page">
      <div className="nav-bar">
        <button className="nav-btn" onClick={() => window.location.href = '/'}>← Back</button>
        <div className="title">My App</div>
        <div className="spacer" />
      </div>
      <div className="content">
        {data ? <pre>{JSON.stringify(data, null, 2)}</pre> : <div className="loading"><div className="spinner" /></div>}
      </div>
    </div>
  )
}
```

**src/main.tsx:**
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

### 5. Styles — index.css

Each app manages its own styles. Follow this pattern for consistency:

```css
/* My App — self-contained styles */

:root {
  --accent: #2563eb;
  --bg: #f2f2f7;
  --card-bg: #ffffff;
  --text: #1c1c1e;
  --text-secondary: #8e8e93;
  --border: rgba(0, 0, 0, 0.1);
  --radius: 12px;
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  color-scheme: light;
}

@media (prefers-color-scheme: dark) {
  :root {
    --accent: #3b82f6;
    --bg: #000000;
    --card-bg: #1c1c1e;
    --text: #f2f2f7;
    --text-secondary: #8e8e93;
    --border: rgba(255, 255, 255, 0.1);
    color-scheme: dark;
  }
}

*, *::before, *::after {
  margin: 0; padding: 0; box-sizing: border-box;
  -webkit-tap-highlight-color: transparent;
}

body { background: var(--bg); color: var(--text); font-family: -apple-system, system-ui, sans-serif; }

.page { min-height: 100dvh; display: flex; flex-direction: column; }

.nav-bar {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center;
  padding: calc(12px + var(--safe-top)) 16px 12px;
  background: var(--card-bg); border-bottom: 0.5px solid var(--border);
}

.nav-btn { background: none; border: none; color: var(--accent); font-size: 15px; cursor: pointer; }
.title { flex: 1; text-align: center; font-size: 17px; font-weight: 600; }
.spacer { width: 60px; }

.content { flex: 1; padding: 12px; }

.stat-card {
  background: var(--card-bg); border-radius: var(--radius);
  padding: 16px; margin-bottom: 12px;
}
```

**Key rules:**
- No shared CSS library — each app is fully self-contained
- Always support dark mode via `prefers-color-scheme`
- Use CSS custom properties for theming
- Use `env(safe-area-inset-*)` for iPhone notch/home bar
- Input font-size must be ≥ 16px to prevent iOS Safari auto-zoom

### 6. Build and test

```bash
# Install frontend deps
cd apps/my-app/frontend && npm install

# Dev mode (hot reload)
npm run dev

# Build for production
npm run build

# Restart server to pick up new app
# (kill existing, then start)
.venv/bin/python3 scripts/server.py --port 8800
```

The app loader auto-discovers apps at startup — no registration needed.

## Common Interfaces (`scripts/commons/`)

Shared Python modules that any app can import from its `routes.py`. These live in `scripts/commons/` and are on the import path automatically.

### Push Notifications — `push_client`

Send push notifications to all subscribed devices (iPhone, Android, desktop browser).

```python
from commons.push_client import send_push

# Async (inside a route handler)
await send_push(
    title="Alert",
    body="Something important happened",
    url="/app/system-monitor/",   # opens this path when tapped
    tag="my-alert",               # replaces previous notification with same tag
)

# Sync (outside async context, e.g. a cron script)
from commons.push_client import send_push_sync
send_push_sync("Build done", "All tests passed", url="/app/system-monitor/")
```

**How it works:** The server exposes `/api/push/send` (POST). `push_client` calls this endpoint internally. The server uses VAPID Web Push to deliver to all subscribers. Push keys are configured in `config.json` under `push.vapid_email`.

**Push API endpoints** (handled by the server, not by apps):
- `GET /api/push/vapid-key` — returns the VAPID public key (frontend uses this to subscribe)
- `POST /api/push/subscribe` — registers a push subscription
- `POST /api/push/unsubscribe` — removes a subscription
- `POST /api/push/send` — sends a notification to all subscribers
- `GET /api/push/test` — sends a test notification

### OpenClaw Messaging — `openclaw_client`

Send messages to OpenClaw chat rooms (Matrix, Discord, Telegram, etc.) through the gateway API.

```python
from commons.openclaw_client import send_message

# Async
await send_message("System alert: disk usage at 90%", room="cronjob")

# Sync
from commons.openclaw_client import send_message_sync
send_message_sync("Build complete", room="cronjob", channel="matrix")
```

Reads gateway URL from `OPENCLAW_GATEWAY_URL` env var (default: `localhost:18789` — the standard OpenClaw gateway port).

### SQLite Helpers — `db`

Convenience wrapper for opening SQLite databases with sensible defaults.

```python
from commons.db import get_connection, ensure_table

conn = get_connection("~/workspace/mydata/mydata.db")  # expands ~, creates dirs
ensure_table(conn, "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT)")
rows = conn.execute("SELECT * FROM items").fetchall()
```

`get_connection` sets `row_factory = sqlite3.Row` so rows work like dicts.

## How the App Loader Works

On startup, `app_loader.py`:

1. Scans `apps/` for directories containing `app.json`
2. Reads metadata from `app.json`
3. Imports `backend/routes.py` and mounts the `router` at `/api/app/{shortcode}/`
5. Mounts `frontend/dist/` as static files at `/app/{app-id}/`

## Conventions

- **API prefix**: `/api/app/{shortcode}/` — shortcode from app.json
- **Frontend URL**: `/app/{app-id}/` — id from app.json
- **No shared frontend deps** — each app has its own node_modules
- **SQLite for data** — no ORM, use sqlite3 directly
- **Dark mode required** — follow system `prefers-color-scheme`
- **Mobile-first** — designed for iPhone PWA, no desktop layout needed
- **Back button** — every app must have `← Back` linking to `/` (home)
