# CrickScorer

CrickScorer is a live cricket scoring system for limited-overs matches. Scorers run matches from an **Admin** app; spectators follow the same match in real time from a **Viewer** scoreboard.

The backend owns all scoring rules and match state. Clients never invent scores, Free Hit state, or innings totals — they submit intents (or read state) and render what the server returns.

Supported formats:

| Format | Status |
| --- | --- |
| T10 | Supported |
| T20 | Supported |
| One Day | Supported |
| Custom overs | Supported |
| Test | Intentionally disabled |

---

## What it does

### Admin (scorer)

- Create matches between seeded teams
- Start the match and innings lifecycle
- Record deliveries (runs, extras, wickets)
- Handle Free Hit after a no-ball
- Replace batters when required (e.g. after catch / run out)
- Undo the last scoring event with full state reconstruction
- Receive live Socket.IO updates so multiple Admin sessions stay in sync

### Viewer (spectator)

- Browse matches
- Open a live scoreboard (score, wickets, overs, batters, bowler, recent balls, Free Hit)
- Stay current via Socket.IO — no polling

### Backend (authority)

- Persists every durable fact in PostgreSQL
- Validates cricket rules and match lifecycle transitions
- Publishes live snapshots over Socket.IO only after a successful database commit
- Reconstructs match state from delivery / replacement history (including undo)

---

## Architecture

```text
                    PostgreSQL 18.3
                           │
                           │ SQLAlchemy 2
                           ▼
                        FastAPI
                       /       \
                      /         \
                 REST API    Socket.IO
                    │             │
                    ▼             ▼
              Admin (React)  Viewer (React)
```

| Concern | Design |
| --- | --- |
| Source of truth | PostgreSQL |
| Domain authority | FastAPI services |
| Mutations | Admin → REST |
| Live updates | Socket.IO (`match:join` / `match:update`) |
| Bootstrap reads | REST |
| Polling | Not used |
| Optimistic scoring | Not used |

Persistent entity IDs are **UUIDv7** (`uuid` + PostgreSQL `uuidv7()`). See [`docs/architecture/UUIDv7_Entity_IDs.md`](docs/architecture/UUIDv7_Entity_IDs.md).

---

## Application stack

### Repository layout

```text
crickscorer/
├── package.json          # npm start / stop / test → Compose + suites
├── compose.yml
├── .env.example
├── server/               # FastAPI backend
├── admin/                # Scorer React app
├── viewer/               # Spectator React app
└── docs/                 # Plans, prompts, phase outputs
```

### Services (Docker Compose)

| Service | Technology | Role | Default host port |
| --- | --- | --- | --- |
| `db` | PostgreSQL **18.3** | Persistent store (volume `crickscorer_pgdata`) | `5432` |
| `server` | FastAPI, Uvicorn, SQLAlchemy 2, Alembic, python-socketio | REST + Socket.IO API | `8000` |
| `admin` | React 19, TypeScript, Vite, TanStack Query, Tailwind, Socket.IO client | Match create, lifecycle, scoring | `5173` |
| `viewer` | Same frontend stack as Admin | Match discovery + live scoreboard | `5174` |

Startup is health-gated:

```text
db (healthy) → server (healthy) → admin + viewer
```

Containers talk to each other by Compose service name (`db`, `server`). Browsers call relative `/api` and `/socket.io`; the Vite apps proxy those paths to the server (`API_PROXY_TARGET`).

### Domain data

Seeded baseline roster (Asia Cup 2025 playing XIs + head coaches):

| Entity | Count |
| --- | --- |
| Teams | 5 (India, Pakistan, Bangladesh, Sri Lanka, Afghanistan) |
| Roles | 6 (`Batsman`, `Bowler`, `Wicket Keeper`, `Captain`, `Vice-Captain`, `Coach`) |
| Players | 60 (11 + coach per team) |
| Player–role links | derived from seed role mappings (`python -m app.db.seed` prints the count) |

Roles live in `roles` / `player_role` (many-to-many), not a player enum.

Core tables: `teams`, `players`, `roles`, `player_role`, `matches`, `innings`, `deliveries`, `batter_replacements`.

Single Alembic revision: `20260918_0001`.

### Intentionally out of scope

These are deferred product choices, not missing bug fixes for this exercise:

- Authentication / authorisation
- Redis / distributed Socket.IO
- Advanced scorecard analytics beyond the current batting/bowling tables
- Test cricket

---

## Run from scratch

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2+
- [Node.js](https://nodejs.org/) + npm (optional; only needed for host-side frontend tests/builds)

### 1. Clone and configure

```bash
git clone <repository-url> CrickScorer
cd CrickScorer

cp .env.example .env
```

Edit `.env` only if you need non-default ports or credentials. Do not commit `.env`.

### 2. Start the stack

```bash
npm start
```

This runs `docker compose up --build` and brings up `db`, `server`, `admin`, and `viewer`.

Wait until all four services report healthy (`docker compose ps`).

### 3. Migrate and seed

On a fresh database volume, apply schema and load the roster:

```bash
docker compose exec server alembic upgrade head
docker compose exec server python -m app.db.seed
```

Seed is idempotent; safe to re-run.

### 4. Open the apps

| App | URL |
| --- | --- |
| Admin — matches | http://localhost:5173/matches |
| Admin — scoring | http://localhost:5173/matches/:id |
| Viewer — matches | http://localhost:5174/matches |
| Viewer — scoreboard | http://localhost:5174/matches/:id/scoreboard |
| API health | http://localhost:8000/health |

Typical first-run flow:

1. In Admin, create a T20 (or T10 / One Day / Custom) match.
2. Start the match and first innings; score deliveries from the scoring workspace.
3. In Viewer, open the same match scoreboard and watch Socket.IO updates.

### 5. Stop

```bash
npm stop
```

Equivalent to `docker compose down`. The Postgres volume is kept unless you remove it explicitly.

---

## Interview task — find and fix three defects

This checkout intentionally contains **three small production bugs** (one each in **server**, **admin**, and **viewer**) for a debugging exercise. The automated tests still encode the correct behaviour — do **not** edit tests to make them pass.

### Run the suites

With the stack up (`npm start`), from the repo root:

```bash
npm test
```

That runs server pytest, then Admin vitest, then Viewer vitest. You should see **exactly one failure per suite** before fixing.

Optional per-suite scripts: `npm run test:server`, `npm run test:admin`, `npm run test:viewer`.

Frontend packages need dependencies installed once on the host (`cd admin && npm ci`, `cd viewer && npm ci`) if you have not already.

### What is broken

| Area | Symptom | Where to look |
| --- | --- | --- |
| **Server** | Strike-rotation / wide **crossing runs** disagree with cricket rules. A plain wide (penalty only) is treated as if batters changed ends. | `server/app/services/strike_rotation.py` — helpers that decide how many runs move batters between ends. Covered by `test_crossing_runs_normal_and_extras` in `server/tests/test_strike_rotation.py`. |
| **Admin** | On a completed match that should be a **win by runs**, the match-result summary shows a **wrong margin** (the wording still looks plausible; the number is wrong). | Admin match-result helpers (e.g. `computeMatchResult` in `admin/src/lib/api/types.ts`). Covered by `shows match result summary when the match is completed` in `admin/src/pages/ScoringPage.test.tsx`. Viewer has its own copy of this logic — fix Admin independently. |
| **Viewer** | In the second-innings **chase** panel, “need N runs from M balls” and/or **required run rate** are slightly wrong. Balls remaining may look fine; runs-needed math is off. | Viewer chase helpers (e.g. `computeChaseSummary` in `viewer/src/lib/utils.ts`). Covered by `shows chase target and required rate in the second innings` in `viewer/src/pages/ScoreboardPage.test.tsx`. |

### Domain rules to restore

1. **Wides and strike** — The wide **penalty** itself does not change ends. Only **extra** runs taken on the wide (beyond that penalty) count toward crossing. Bat runs, byes, and leg-byes always count.
2. **Win by runs** — Margin is `first_innings_runs − second_innings_runs`. Do not mix wickets into a runs margin.
3. **Chase** — Match `target` already means “one more than the first-innings total.” While chasing, `runsNeeded = max(0, target − currentRuns)`. Do not subtract an extra 1 as if `target` were only the opposition total. Required run rate follows from runs needed and balls remaining.

### Constraints

- Fix **production code** only; do not weaken, skip, or rewrite failing tests.
- Prefer the smallest correct change (expect roughly three one-line fixes).
- Do not add features, schema changes, or new bugs.

### Done when

```bash
npm test
```

reports **zero failures** across server, admin, and viewer.
