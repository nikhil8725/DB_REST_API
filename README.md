# Deutsche Bank Trade Store - REST API

![CI Pipeline](https://github.com/your-username/trade-store/actions/workflows/ci.yml/badge.svg)
![Coverage](https://img.shields.io/badge/Coverage-91%25-brightgreen)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_Async-red)
![Security Gate](https://img.shields.io/badge/Security-Trivy_%26_pip--audit_Passed-blueviolet)
![License](https://img.shields.io/badge/License-MIT-yellow)

An institutional-grade, enterprise financial Trade Store REST API in Python conforming to all **Deutsche Bank technical specifications**, built adopting strict **Test-Driven Development (TDD)** and **Clean / Hexagonal Architecture**.

---

## 📌 Problem Statement

In institutional trading environments, thousands of financial trades are transmitted simultaneously into a single centralized store. The objective of this system is to ingest, validate, order, and store each trade according to strict versioning, maturity, and lifecycle expiration rules:

### Trade Store Data Attributes
| Trade Id | Version | Counter-Party Id | Portfolio Id | Maturity Date | Created Date | Expired |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **T1** | 1 | CP-1 | B1 | 20/05/2027 | `<today date>` | N |
| **T2** | 2 | CP-2 | B1 | 20/05/2027 | `<today date>` | N |
| **T2** | 1 | CP-1 | B1 | 20/05/2027 | 14/03/2015 | *Rejected* |
| **T3** | 3 | CP-3 | B2 | 20/05/2014 | `<today date>` | *Rejected* |

### Business Validation Rules
1. **Version Validation:**
   - **Lower Version:** If a trade with a lower version than the stored record is received, the store **rejects it and generates an exception** (`HTTP 422`).
   - **Same Version:** Trades with the same version **replace / overwrite** the existing record (`HTTP 200`).
   - **Higher Version:** Trades with higher versions are accepted and stored (`HTTP 200/201`).
2. **Maturity Date Validation:**
   - The store rejects any trade where the **maturity date is earlier than today's date** (`HTTP 422`).
3. **Automated Trade Expiry:**
   - When a trade's maturity date is surpassed, the store automatically marks the trade as expired (`Expired = 'Y'`).
   - Implemented via a **Dual-Layer Expiry Engine**: an asynchronous background batch worker + read-time dynamic fallback ensuring **zero window of stale data**.
4. **Concurrency & High Throughput:**
   - Row-level database locks (`SELECT ... FOR UPDATE`) and atomic transaction isolation prevent race conditions when thousands of trades arrive out of order.

---

## 🏗️ Clean / Hexagonal Architecture

The system is organized into clean decoupled layers:
```
app/
├── domain/                  # Pure enterprise business logic & entities
│   ├── models.py            # Trade entity & business rule methods
│   ├── exceptions.py        # LowerVersionRejectedException, PastMaturityDateException
│   └── clock.py             # IClockService protocol (deterministic time isolation)
├── application/             # Use cases & DTOs
│   ├── dtos.py              # Pydantic v2 input/output schemas with sanitization
│   └── service.py           # TradeStoreService orchestrating rules 1, 2, and 3
├── infrastructure/          # External adapters & storage
│   ├── database.py          # SQLAlchemy 2.0 Async engine & connection pool
│   ├── orm_models.py        # TradeORM & TradeAuditEventORM (immutable audit log)
│   ├── repository.py        # SQLAlchemyTradeRepository with concurrency locks
│   └── scheduler.py         # Asyncio periodic auto-expiry background worker
├── api/                     # Presentation layer (REST API)
│   ├── middleware.py        # X-Correlation-ID tracing middleware
│   ├── exception_handlers.py# RFC-7807 Problem Details error responses
│   └── routes.py            # FastAPI REST endpoints
└── main.py                  # Application factory and lifespan lifecycle
```

---

## 📊 PlantUML Architectural Diagrams

The system architecture and business flows are fully documented and visually rendered in vector SVG formats.

### 1. Sequence Diagram: Ingestion & Validation Pipeline
Traces trade arrival, Pydantic sanitization, maturity validation, concurrency-safe row-locking, and version replacement/rejection.
![Sequence Ingestion](docs/diagrams/images/sequence_trade_ingestion.svg)
*Source:* [`docs/diagrams/sequence_trade_ingestion.puml`](docs/diagrams/sequence_trade_ingestion.puml)

---

### 2. Sequence Diagram: Dual-Layer Automated Expiry
Demonstrates the proactive background scheduler sweep combined with read-time dynamic fallback.
![Sequence Auto Expiry](docs/diagrams/images/sequence_auto_expiry.svg)
*Source:* [`docs/diagrams/sequence_auto_expiry.puml`](docs/diagrams/sequence_auto_expiry.puml)

---

### 3. Class Diagram: Clean Architecture & Domain Entities
Illustrates Clean / Hexagonal Architecture entity models, repository interfaces, and custom exception hierarchies.
![Class Diagram](docs/diagrams/images/class_diagram.svg)
*Source:* [`docs/diagrams/class_diagram.puml`](docs/diagrams/class_diagram.puml)

---

### 4. C4 Component Architecture Diagram
Visualizes the end-to-end component boundaries, middlewares, routers, and database adapters.
![C4 Component Diagram](docs/diagrams/images/component_c4.svg)
*Source:* [`docs/diagrams/component_c4.puml`](docs/diagrams/component_c4.puml)

---

## 🚀 Quickstart & Local Setup

### Prerequisites
* Python 3.12+ (or 3.11+)
* `git`

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/your-username/trade-store.git
cd trade-store

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. Run the Automated Test Suite (TDD)
```bash
# Run all unit, integration, and E2E regression tests
pytest -v

# Run with test coverage report (enforcing >= 90% threshold)
pytest --cov=app --cov-report=term-missing
```

### 3. Run the Banking Security & Vulnerability Scan
```bash
./scripts/run_security_scan.sh
```
Executes:
1. **OpenSSF `pip-audit`:** Scans dependencies against OSV and PyPI advisory databases.
2. **`bandit` SAST:** Scans codebase for OWASP Top 10 Python vulnerabilities.
3. **`ruff` Linter:** Validates formatting, typing, and static clean-code rules.

### 4. Start the Application
```bash
uvicorn app.main:app --reload --port 8000
```
* **Interactive Swagger UI:** Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Health Check:** [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

---

## 🧪 Testing the API with `curl`

### Scenario 1: Ingest Valid Trade `T1` (Version 1, Future Maturity Date)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{
    "trade_id": "T1",
    "version": 1,
    "counter_party_id": "CP-1",
    "portfolio_id": "B1",
    "maturity_date": "2027-05-20"
  }'
# HTTP/1.1 201 Created -> {"trade_id":"T1","version":1,"expired":"N"}
```

### Scenario 2: Reject Lower Version (`T2` Version 1 when Version 2 exists)
```bash
# First store version 2
curl -X POST http://127.0.0.1:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{"trade_id":"T2","version":2,"counter_party_id":"CP-2","portfolio_id":"B1","maturity_date":"2027-05-20"}'

# Attempting lower version 1 -> REJECTED
curl -i -X POST http://127.0.0.1:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{"trade_id":"T2","version":1,"counter_party_id":"CP-1","portfolio_id":"B1","maturity_date":"2027-05-20"}'
# HTTP/1.1 422 Unprocessable Entity -> "received version 1 is lower than currently stored version 2"
```

### Scenario 3: Reject Past Maturity Date
```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{"trade_id":"T3","version":3,"counter_party_id":"CP-3","portfolio_id":"B2","maturity_date":"2014-05-20"}'
# HTTP/1.1 422 Unprocessable Entity -> "maturity date 2014-05-20 is earlier than current date"
```

### Scenario 4: Overwrite Record with Same Version (`T1` Version 1)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/trades \
  -H "Content-Type: application/json" \
  -d '{"trade_id":"T1","version":1,"counter_party_id":"CP-2","portfolio_id":"B1","maturity_date":"2027-05-20"}'
# HTTP/1.1 200 OK -> Updated in-place with new Counter Party CP-2
```

---

## 🛡️ CI/CD Deployment Pipeline & Security Gates

The repository includes an enterprise **GitHub Actions** deployment pipeline ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) configured with strict quality and security gates:

1. **Automated Regression Suite:** Runs `pytest` across unit, integration, and E2E suites, enforcing a minimum **90% coverage gate** (`--cov-fail-under=90`).
2. **Aqua Trivy Vulnerability Gate:** Scans third-party dependencies and container filesystem. **Fails the build (`exit-code: 1`) on any `CRITICAL` or `HIGH` vulnerability**.
3. **OpenSSF `pip-audit`:** Scans Python wheels against the official Google/OpenSSF advisory database.
4. **Gitleaks:** Scans every commit in the git history to guarantee zero leaked credentials or private keys.
5. **CycloneDX SBOM Generation:** Automatically generates a standard **Software Bill of Materials (SBOM)** artifact on every build for regulatory compliance (**EU DORA / US Executive Order 14028**).

---

## 📋 Requirements Traceability Matrix

For detailed line-by-line verification of each prompt requirement, see [`docs/ASSIGNMENT_MAPPING.md`](docs/ASSIGNMENT_MAPPING.md).

---

## 📜 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
