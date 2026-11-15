# CareKey 🔑

> **Elderly Care & Medication Management Platform with Two-Key Authorization**  
> Built with dignity, privacy, and accessibility at its foundation for the hackathon.

---

## 🌐 Live Demo

| Component | Link / Value |
|---|---|
| **Live App URL** | https://carekey.onrender.com/login |
| **Circle Code** | CARE-JU8C |
| **Elder Owner Passcode** | `N6B3HAC5V55G` |
| **Caretaker (Helper) Passcode** | `42MQ3RDJN7XJ` |

> **Note:** The demo runs on a free instance with in-memory data. The first visit may take up to a minute to wake up. If a passcode says invalid after a restart, create a fresh circle at https://carekey.onrender.com/circle/create (about 30 seconds), then issue a caretaker key under Manage Keys.
>
> **Local demo data:** run `python -m scripts.seed_demo` to create a sample circle with medications.
---

## 📋 Requirements to Features & Files Mapping

The table below maps each hackathon requirement to its implemented capability, business layer, and source files.

| Hackathon Requirement | Implemented Feature & Capabilities | Primary Source Files |
|---|---|---|
| **Passcode-based shared access** | Scoped, expiring 12-character passcodes from an unambiguous charset (no `0`, `O`, `1`, `I`, `L`). Input normalization (strips spaces/hyphens, uppercases). Scrypt hashing with unique salt. Lockout after 5 failures for 15 mins. Per-IP rate limiting. Instant revocation. Show/Hide toggle and accessible Copy button. | `app/services/auth.py`<br>`app/routes/auth.py`<br>`app/templates/login.html`<br>`app/templates/keys.html`<br>`app/templates/circle_created.html` |
| **View, add & edit medication schedules** | Complete medication profile management: dosage, instructions, prescribing doctor, days of week, times of day, max doses per day. Non-elder managers submit `ChangeProposal` records; elders apply changes directly. | `app/services/medication.py`<br>`app/services/proposals.py`<br>`app/routes/medications.py`<br>`app/routes/proposals.py`<br>`app/templates/medications.html` |
| **Adherence tracking** | Automatic punctuality classification per dose event: `on_time` (within 30m), `late` (30m–2h), `missed` (>2h), `skipped`. Calculates total adherence percentage, dose counts, and consecutive days streak. | `app/services/medication.py`<br>`app/routes/caretaker.py`<br>`app/templates/caretaker_dashboard.html` |
| **Appointments** | Scheduled healthcare visits tracking doctor, clinical facility, appointment datetime, and notes. Upcoming chronological list. Automated 24-hour and 2-hour pre-appointment email reminders. | `app/models.py`<br>`app/routes/appointments.py`<br>`app/templates/appointments.html`<br>`app/services/reminders.py` |
| **Email reminders & escalation** | Stateless `POST /internal/tick` protected by constant-time secret header. Batched query with idempotent `ReminderSent` tracking. Dose escalation ladder: 10m before (reminder to elder), 15m late (second nudge), 60m late (alert caretakers and mark dose missed). One-tap signed actions ("I took it", "Snooze 15 min", "Call me") with GET confirmation and CSRF POST execution. | `app/services/reminders.py`<br>`app/services/action_tokens.py`<br>`app/services/email.py`<br>`app/routes/internal.py`<br>`app/routes/actions.py`<br>`app/templates/action_confirm.html` |
| **Elder-centred design** | High-contrast, clutter-free `/today` screen with single-tap "I took it" buttons per scheduled dose. Plain-language confirmation feedback. Elder time zone localization (default `Asia/Kolkata`). Self-serve circle creation where elder holds master keys. | `app/routes/elder.py`<br>`app/templates/today.html`<br>`app/templates/create_circle.html`<br>`app/templates/circle_created.html` |
| **Security & Two-Key Rule** | Role hierarchy (`ELDER` > `MANAGER` > `HELPER` > `VIEWER`). Two-key rule with automated risk scoring (`LOW`/`MEDIUM`/`HIGH`) checking ingredient overlaps, dose increases >1.5x, and deletions. Emergency override with mandatory audit trail. Append-only SHA-256 cryptographic audit chain (`AuditEntry`). Signed HttpOnly SameSite=Lax Secure session cookies. CSRF tokens on all POST forms. Production startup secret enforcement. | `app/services/risk.py`<br>`app/services/audit.py`<br>`app/services/session.py`<br>`app/routes/dependencies.py`<br>`app/config.py`<br>`app/main.py`<br>`app/templates/audit.html` |
| **Tests** | Comprehensive automated test suite with 55 unit and integration tests. Covers hashing, lockouts, expiry, revocation, role enforcement, cross-circle isolation, dose status, adherence metrics, risk rules, proposal workflows, audit tampering detection, escalation ladders, signed action tokens, end-to-end app wiring, Firestore repository typing, and production configuration. | `tests/test_access_control.py`<br>`tests/test_appointments.py`<br>`tests/test_audit_chain.py`<br>`tests/test_auth.py`<br>`tests/test_e2e_wiring.py`<br>`tests/test_email_sender.py`<br>`tests/test_firestore_repo.py`<br>`tests/test_healthz.py`<br>`tests/test_medications_and_doses.py`<br>`tests/test_one_tap_actions.py`<br>`tests/test_passcodes_and_emails.py`<br>`tests/test_production_config.py`<br>`tests/test_proposals_workflow.py`<br>`tests/test_reminders_escalation.py`<br>`tests/test_routes_integration.py`<br>`tests/test_two_key_risk.py` |
| **Accessibility (WCAG 2.1 AA+)** | High contrast color palette (18:1 text contrast ratio), minimum 20px base typography for elder screens, 48px+ touch targets, visible 3px focus indicators, keyboard skip links, semantic landmarks, and dual ARIA live regions (`#aria-live-polite` and `#aria-live-assertive`). | `app/static/css/main.css`<br>`app/static/js/main.js`<br>`app/templates/base.html`<br>`app/templates/today.html`<br>`app/templates/login.html` |

---

## 🔒 Security Model & Threat Defenses

CareKey is engineered with defense-in-depth security tailored for healthcare and vulnerable users:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          CAREKEY SECURITY MODEL                        │
├────────────────────────────────────────────────────────────────────────┤
│  Authentication       │ Scrypt (N=16384, r=8, p=1) + Per-Key Salt      │
│                       │ Unambiguous charset, constant-time compare     │
│                       │ Lockout: 5 failed attempts -> 15 min lock      │
│                       │ IP rate limit: max 10 attempts per minute      │
├───────────────────────┼────────────────────────────────────────────────┤
│  Session & State      │ Signed HMAC-SHA256 HttpOnly session cookies    │
│                       │ SameSite=Lax, Secure=True in production        │
│                       │ Per-session CSRF token validation on all POSTs │
├───────────────────────┼────────────────────────────────────────────────┤
│  Authorization        │ Strict Role Hierarchy:                         │
│                       │ ELDER (Owner) > MANAGER > HELPER > VIEWER     │
│                       │ Route-level role guards, Circle-scoped queries │
├───────────────────────┼────────────────────────────────────────────────┤
│  Two-Key Rule         │ Manager medication modifications -> Proposal   │
│                       │ Pure risk engine evaluates LOW / MED / HIGH    │
│                       │ Elder approves atomically or rejects           │
│                       │ Emergency override requires written reason     │
├───────────────────────┼────────────────────────────────────────────────┤
│  Tamper-Evident Audit │ Append-only cryptographic hash chain           │
│                       │ Hash = SHA256(prev_hash + canonical_json)      │
│                       │ Automatic verification detects broken links    │
│                       │ Passcodes and raw secrets strictly REDACTED    │
├───────────────────────┼────────────────────────────────────────────────┤
│  One-Tap Action Links │ Signed, single-use, expiring action tokens     │
│                       │ GET displays confirmation; POST executes       │
├───────────────────────┼────────────────────────────────────────────────┤
│  Production Guardrail │ Refuses to start if SECRET_KEY or TICK_SECRET  │
│                       │ is missing or uses insecure defaults           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture & Engineering Design

CareKey enforces strict separation of concerns across a layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│                     Presentation Layer                  │
│       FastAPI Routes, Jinja2 Templates, Semantic HTML   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                     Domain Services                     │
│    AuthService, MedicationService, ReminderService,     │
│    ActionTokenManager, RiskEngine, AuditService         │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                    Persistence Layer                    │
│                 RepositoryProtocol Interface            │
├────────────────────────────┬────────────────────────────┤
│     InMemoryRepository     │    FirestoreRepository     │
│    (Fast automated tests)  │  (Cloud Run production)    │
└────────────────────────────┴────────────────────────────┘
```

- **In-Memory & Cloud Firestore Backends**: Selectable via `REPOSITORY_BACKEND=memory|firestore`.
- **Zero Composite Indexes Required**: Firestore queries perform in-memory predicate filtering (`find`), avoiding manual composite index maintenance.
- **Zero Node.js / Webpack Build Steps**: Pure semantic HTML5 + vanilla CSS/JS for instantaneous container builds.
- **Strict Typing**: Python 3.12 type annotations verified with `mypy app` with zero errors across 31 source files.
- **Clean Linting**: 100% compliant with `ruff check .`.

---

## 📁 Repository Directory Structure

```text
carekey/
├── .env.example              # Template for environment configuration
├── DEPLOY.md                 # Cloud Run & Cloud Scheduler deployment guide
├── Dockerfile                # Hardened non-root production container
├── pyproject.toml            # Project configuration (mypy, ruff, pytest)
├── requirements.txt          # Production dependencies (FastAPI, Firestore, etc.)
├── requirements-dev.txt      # Development & testing dependencies
├── README.md                 # Project documentation
│
├── app/
│   ├── config.py             # Pydantic Settings with production validation
│   ├── main.py               # FastAPI application factory and ASGI entrypoint
│   ├── models.py             # Pydantic domain models & enums
│   │
│   ├── routes/               # Presentation layer (HTTP endpoints)
│   │   ├── actions.py        # One-tap email action confirmation & execution
│   │   ├── appointments.py   # Healthcare appointments management
│   │   ├── audit.py          # Audit log viewing and chain verification
│   │   ├── auth.py           # Circle creation, login, logout, key issuance
│   │   ├── caretaker.py      # Caretaker dashboard & adherence summary
│   │   ├── dependencies.py   # FastAPI dependency injection providers
│   │   ├── elder.py          # Elder "Today" screen
│   │   ├── health.py         # /healthz liveness & readiness probe
│   │   ├── internal.py       # POST /internal/tick reminder scheduler
│   │   ├── medications.py    # Medication listing & deletion
│   │   └── proposals.py      # Two-key proposals, review, approve, reject
│   │
│   ├── services/             # Domain business logic layer
│   │   ├── action_tokens.py  # Signed, expiring, single-use action tokens
│   │   ├── audit.py          # Append-only SHA-256 tamper-evident audit trail
│   │   ├── auth.py           # Scrypt hashing, lockout, rate limiting, keys
│   │   ├── email.py          # EmailSender interface (SMTP & Fake for tests)
│   │   ├── health.py         # System health diagnostic service
│   │   ├── medication.py     # Dose calculation, adherence, streak tracking
│   │   ├── reminders.py      # Stateless escalation ladder & appointment alerts
│   │   ├── risk.py           # Pure two-key risk engine (LOW/MED/HIGH)
│   │   └── session.py        # Signed session cookies & CSRF tokens
│   │
│   ├── repositories/         # Storage layer
│   │   ├── base.py           # RepositoryProtocol & abstract contracts
│   │   ├── in_memory.py      # Thread-safe in-memory store for fast tests
│   │   └── firestore.py      # Google Cloud Firestore persistent adapter
│   │
│   ├── static/               # Client-side static assets
│   │   ├── css/main.css      # High-contrast accessible styling
│   │   └── js/main.js        # Accessible ARIA announcements, copy & toggles
│   │
│   └── templates/            # Accessible Jinja2 HTML templates
│       ├── action_confirm.html
│       ├── action_success.html
│       ├── appointments.html
│       ├── audit.html
│       ├── base.html
│       ├── caretaker_dashboard.html
│       ├── circle_created.html
│       ├── create_circle.html
│       ├── keys.html
│       ├── login.html
│       ├── medications.html
│       ├── proposals.html
│       └── today.html
│
├── scripts/
│   ├── __init__.py
│   └── seed_demo.py          # Demo data seeder (Elder, Caretaker, Meds, Appts)
│
└── tests/                    # 55 automated tests (100% passing)
    ├── conftest.py
    ├── test_access_control.py
    ├── test_appointments.py
    ├── test_audit_chain.py
    ├── test_auth.py
    ├── test_e2e_wiring.py
    ├── test_email_sender.py
    ├── test_firestore_repo.py
    ├── test_healthz.py
    ├── test_medications_and_doses.py
    ├── test_one_tap_actions.py
    ├── test_passcodes_and_emails.py
    ├── test_production_config.py
    ├── test_proposals_workflow.py
    ├── test_reminders_escalation.py
    ├── test_routes_integration.py
    └── test_two_key_risk.py
```

---

## 🚀 Quickstart & Local Development

### 1. Set Up Environment
```bash
# Clone the repository
git clone https://github.com/premsuchak26/carekey.git
cd carekey

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Configure Local Settings
```bash
cp .env.example .env
```
*(By default, `REPOSITORY_BACKEND=memory` is enabled for instant local testing without GCP credentials).*

### 3. Seed Demo Data
```bash
python -m scripts.seed_demo
```
This generates and prints the **Circle Code**, **Elder Passcode**, and **Caretaker Passcode**.

### 4. Run the Development Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Open [http://localhost:8080](http://localhost:8080) to sign in.

---

## 🧪 Testing & Quality Gates

Run all automated quality checks:

```bash
# 1. Run the comprehensive test suite (55 tests)
pytest

# 2. Check code style and formatting
ruff check .

# 3. Static type analysis across all 31 source files
mypy app
```

---

## ☁️ Cloud Run Deployment & Cloud Scheduler

For complete step-by-step instructions on deploying CareKey to **Google Cloud Run** with **Cloud Firestore** and setting up the **Cloud Scheduler** escalation cron job, please refer to [DEPLOY.md](file:///C:/Users/hp/.gemini/antigravity/scratch/carekey/DEPLOY.md).
