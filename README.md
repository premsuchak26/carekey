# CareKey 🔑

> **Elderly Care & Medication Management Platform with Two-Key Authorization**  
> Built with dignity, privacy, and accessibility at its foundation for the hackathon.

---

## 🌟 Vision & Core Principles

CareKey puts elderly individuals firmly in control of their healthcare circle. Too often, health management tools treat older adults as passive subjects. CareKey turns this upside down: **the elder owns the private care circle and holds the master keys.**

1. **Elder Circle Ownership**: The senior citizen is the primary owner of their profile, schedule, and permissions.
2. **Two-Key Authorization Rule**: Any medication adjustment, dosage alteration, or cancellation attempted by a non-elder caretaker or family member requires explicit confirmation from the elder.
3. **Scoped, Expiring Passcodes**: Caretakers and family members receive role-scoped, time-limited, and instantly revocable access codes.
4. **Tamper-Evident Audit Chain**: Every log entry, medication event, key generation, and approval is immutably timestamped in an append-only verification trail.
5. **Accessibility First**: Designed specifically with high contrast, legible typography, large touch targets, keyboard navigation, and full screen-reader live regions (WCAG 2.1 AA+).

---

## 🏗️ Architecture & Engineering Rules

CareKey enforces strict separation of concerns across a three-tier architecture:

```
┌────────────────────────────────────────┐
│             HTTP Routes                │  (FastAPI route handlers)
│       - No business logic              │  (Receives requests, maps DTOs, returns models/HTML)
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│            Domain Services             │  (Business Logic & Workflow Layer)
│       - Two-key authorization logic    │  (Passcode verification, validation, audit dispatch)
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│         Repository Interface           │  (RepositoryProtocol)
├───────────────────┬────────────────────┤
│ InMemoryRepository│ FirestoreRepository│  (Dual implementations: fast tests & production cloud)
└───────────────────┴────────────────────┘
```

- **Type Safety**: Python 3.12 type annotations throughout; verified strictly with `mypy`.
- **Code Quality**: Formatted and linted cleanly with `ruff`.
- **Zero Frontend Build Step**: FastAPI + Jinja2 templates + semantic HTML5 + lightweight vanilla JS.
- **Environment Secrets**: Zero hardcoded secrets; configuration validated via `pydantic-settings`.

---

## 📁 Repository Structure

```text
carekey/
├── .env.example              # Template for environment configuration
├── .gitignore                # Git exclusions (including .env and secrets)
├── Dockerfile                # Multi-stage/slim non-root production container
├── Makefile                  # Developer workflow automation (run, test, lint)
├── pyproject.toml            # Project metadata, ruff, mypy, and pytest config
├── requirements.txt          # Production Python dependencies
├── requirements-dev.txt      # Development & testing dependencies
├── README.md                 # Project documentation
│
├── app/
│   ├── __init__.py
│   ├── config.py             # Pydantic Settings configuration module
│   ├── main.py               # FastAPI application factory and ASGI entrypoint
│   │
│   ├── routes/               # Presentation layer (HTTP routes only, no business logic)
│   │   ├── __init__.py
│   │   └── health.py         # Health probe (/healthz)
│   │
│   ├── services/             # Core business logic layer
│   │   ├── __init__.py
│   │   └── health.py         # System health aggregation service
│   │
│   ├── repositories/         # Data persistence layer
│   │   ├── __init__.py
│   │   ├── base.py           # RepositoryProtocol & abstract contracts
│   │   ├── in_memory.py      # In-memory dictionary repository (for testing)
│   │   └── firestore.py      # Google Cloud Firestore persistent adapter
│   │
│   ├── static/               # Client-side static assets (no build step)
│   │   ├── css/
│   │   │   └── main.css      # High contrast WCAG AA compliant styles
│   │   └── js/
│   │       └── main.js       # Minimal vanilla JS with ARIA live announcements
│   │
│   └── templates/            # Accessible Jinja2 HTML templates
│       └── base.html         # Base semantic layout with skip-links & ARIA regions
│
└── tests/                    # Automated test suite
    ├── __init__.py
    ├── conftest.py           # Shared fixtures and test settings
    └── test_healthz.py       # Health endpoint unit and integration tests
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12+**
- (Optional) **Docker**
- (Optional) **Make** (Linux / macOS / Git Bash / WSL)

### 1. Clone & Set Up Virtual Environment

```bash
cd carekey

# Create Python 3.12 virtual environment
python -m venv .venv

# Activate environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Review `.env` to select either `REPOSITORY_TYPE=memory` (default for local development and tests) or `REPOSITORY_TYPE=firestore`.

### 3. Install Dependencies

Using `make`:
```bash
make install
```

Or using `pip`:
```bash
pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 4. Run the Development Server

```bash
make run
# Or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit the application:
- Application Base: [http://localhost:8000](http://localhost:8000)
- Health Check Probe: [http://localhost:8000/healthz](http://localhost:8000/healthz)

---

## 🧪 Testing & Code Quality

CareKey enforces testing alongside every new feature and strict code hygiene:

```bash
# Run pytest test suite
make test

# Check code style with ruff
make lint

# Auto-format code
make format

# Run static type checking with mypy
make typecheck

# Run full CI check (lint + typecheck + test)
make check
```

---

## 🐳 Docker Container

The application includes a production-ready, hardened Dockerfile:
- Base image: `python:3.12-slim`
- User: Dedicated non-root user `appuser` (UID 10001)
- Built-in `HEALTHCHECK` pinging `/healthz`

```bash
# Build the image
make docker-build
# or: docker build -t carekey:latest .

# Run the container
make docker-run
# or: docker run -p 8000:8000 --rm --name carekey-app carekey:latest
```

---

## ♿ Accessibility Compliance

- **Semantic Landmarks**: `<header>`, `<nav>`, `<main>`, `<section>`, `<footer>`
- **Skip Navigation**: Keyboard shortcut link directly to `#main-content`
- **High Contrast**: Background and foreground colors exceed WCAG 2.1 AA standards (minimum 4.5:1 ratio; primary text achieves ~18:1 ratio)
- **ARIA Live Regions**: Dedicated `#aria-live-polite` and `#aria-live-assertive` announcement areas for assistive technology
- **Focus Rings**: Prominent 3px solid focus indicators with 3px offsets (`:focus-visible`)
- **Large Click/Tap Targets**: Minimum 48px target height on interactive elements
- **Readable Typography**: 18px base text size with 1.6 line height for enhanced readability for elderly individuals
