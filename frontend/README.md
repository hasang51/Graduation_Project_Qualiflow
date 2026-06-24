# QualiFlow Frontend

React + Vite + TypeScript UI for authenticated PDF analysis.

## Prerequisites

- Backend running via Docker (`docker compose up -d`) or local uvicorn + worker
- API reachable at `http://127.0.0.1:8000`

## Run

```powershell
npm install
copy .env.example .env
npm run dev
```

Open **http://localhost:5173**

## Environment

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Features

- Register / login
- Async PDF upload with job progress
- Analysis detail view (`/analysis/:id`)
- Analysis history
