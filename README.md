# Breathe ESG — Emissions Data Ingestion Platform

A Django REST + React application that ingests emissions activity data from SAP, utility portals, and corporate travel platforms, normalises it, and provides an analyst review dashboard before data is locked for audit.

**Demo credentials:** `analyst` / `Breathe2024!`

---

## Project Structure

```
breathe-esg/
├── backend/                 # Django REST API
│   ├── apps/
│   │   ├── clients/         # Multi-tenancy, plant mappings, emission factors
│   │   ├── ingestion/       # Batch tracking, raw record storage, parsers
│   │   │   └── parsers/
│   │   │       ├── sap.py       # SAP flat-file CSV parser
│   │   │       ├── utility.py   # Utility electricity CSV parser
│   │   │       └── travel.py    # Corporate travel CSV parser
│   │   ├── emissions/       # EmissionRecord model, review workflow
│   │   ├── audit/           # Append-only audit trail
│   │   └── users/           # Custom user model with roles
│   ├── config/              # Django settings, URLs, WSGI
│   └── requirements.txt
├── frontend/                # React + Vite + Tailwind
│   └── src/
│       ├── pages/           # Login, Dashboard, Ingest, Review, Batches
│       ├── components/      # Layout, shared UI
│       ├── api/             # Axios client with JWT interceptors
│       └── hooks/           # useAuth
├── sample_data/             # Realistic test files for each source type
│   ├── sap_export.csv
│   ├── utility_electricity.csv
│   └── travel_concur.csv
├── MODEL.md                 # Data model documentation
├── DECISIONS.md             # Every ambiguity resolved
├── TRADEOFFS.md             # Three things deliberately not built
└── SOURCES.md               # Real-world format research
```

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### 1. Clone and set up backend

```bash
git clone https://github.com/YOUR_USERNAME/breathe-esg.git
cd breathe-esg/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env if needed (defaults work for local dev)

# Run migrations
python manage.py migrate

# Seed emission factors, demo client, and users
python manage.py seed_data

# Start development server
python manage.py runserver
# → API running at http://localhost:8000
```

### 2. Set up frontend

```bash
# In a new terminal
cd breathe-esg/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
# → App running at http://localhost:3000
```

### 3. Log in

Open http://localhost:3000 and log in with:
- **Analyst:** `analyst` / `Breathe2024!`
- **Admin:** `admin` / `Breathe2024!`

### 4. Test ingestion

Upload the sample files from `sample_data/`:

| File | Source type | What to expect |
|------|-------------|----------------|
| `sap_export.csv` | SAP | 8 parsed, 2 errors (invalid date, invalid quantity) |
| `utility_electricity.csv` | UTILITY | 8 parsed, 1 error (empty consumption) |
| `travel_concur.csv` | TRAVEL | 9 parsed, some flagged for unknown IATA codes |

---

## Environment Variables

Create `backend/.env`:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

For production (Railway):

```env
SECRET_KEY=<generated>
DEBUG=False
DATABASE_URL=<railway postgres url>
ALLOWED_HOSTS=<your-railway-domain>.railway.app
CORS_ALLOWED_ORIGINS=https://<your-frontend>.vercel.app
```

---

## Deploying to Railway (Backend) + Vercel (Frontend)

See the step-by-step guide below.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/token/` | Login → JWT tokens |
| POST | `/api/v1/auth/token/refresh/` | Refresh access token |
| GET | `/api/v1/users/me/` | Current user info |
| GET | `/api/v1/ingestion/batches/` | List ingestion batches |
| POST | `/api/v1/ingestion/batches/upload/` | Upload file (multipart) |
| GET | `/api/v1/ingestion/batches/{id}/raw_records/` | Raw records for a batch |
| GET | `/api/v1/emissions/` | List emission records (filterable) |
| PATCH | `/api/v1/emissions/{id}/review/` | Approve / flag / reject |
| POST | `/api/v1/emissions/bulk_approve/` | Bulk approve |
| GET | `/api/v1/emissions/summary/` | Dashboard totals |
| GET | `/api/v1/audit/` | Audit log |

---

## Key Design Decisions

See **DECISIONS.md** for the full rationale. Summary:

- **SAP:** Flat-file CSV chosen over OData/IDoc — reflects what sustainability teams actually receive
- **Utility:** Portal CSV export — handles non-calendar billing periods
- **Travel:** Concur CSV export with Great Circle distance fallback (Haversine + 9% ICAO uplift)
- **Factors:** DEFRA 2023 primary, EPA eGRID and CEA India supplemental
- **Audit:** Append-only, full state snapshots, no deletes ever
