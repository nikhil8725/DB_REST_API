# Deutsche Bank Trade Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, enterprise-grade, TDD-driven Trade Store REST API in Python conforming to all Deutsche Bank specifications, including version replacement/rejection, maturity date validation, automated background trade expiry, and an institutional GitHub Actions CI pipeline with automated vulnerability gating.

**Architecture:** Clean/Hexagonal Architecture separating pure Domain rules and exceptions, Application Services, SQLAlchemy 2.0 Async Persistence with atomic concurrency controls, and FastAPI REST endpoints. Temporal logic is decoupled through an injectable `IClockService` interface to guarantee deterministic TDD testing.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 Async, aiosqlite, pytest, pytest-asyncio, pytest-cov, ruff, Trivy, pip-audit, Gitleaks, Semgrep.

**Spec:** [`docs/architecture/ARCHITECTURE.md`](file:///Users/nikhilbahalkar/Documents/antigravity/Deutsche_Bank_Assignment/docs/architecture/ARCHITECTURE.md)

## Global Constraints
- Target language: Python 3.12+ with strict static typing.
- Database: SQLite via `aiosqlite` for zero-dependency local runs and CI test speed, using SQLAlchemy 2.0 async ORM models convertible to PostgreSQL.
- Business Validation Rules:
  - Reject trade with lower version than stored record (`HTTP 422`).
  - Replace/overwrite existing trade with same version (`HTTP 200`).
  - Accept trade with higher version (`HTTP 200` or `201`).
  - Reject trade where `maturity_date < today_utc` (`HTTP 422`).
  - Automatic expiry: Mark `expired = 'Y'` when `today_utc > maturity_date` via dual-layer (background scheduler + read-time fallback).
- Security Gate: GitHub Actions must fail build (`exit-code 1`) on any `CRITICAL` vulnerability detected by Aqua Trivy or `pip-audit`.

## Review Focus
1. Input where `trade_id` is identical but casing differs (e.g. `t1` vs `T1`) -> Store must normalize `trade_id.upper()` to prevent duplicate logical records.
2. Trade submitted at 23:59:59 UTC maturing tomorrow -> Time calculations must be strictly UTC timezone-aware to prevent day-boundary race conditions.
3. Rapid concurrent submissions for same `trade_id` -> Database conditional write or row-lock must ensure a lower version never overwrites a higher version due to thread interleaving.
4. Auto-expiry job failure -> Read-time dynamic check must still mark trade as expired when requested by API consumers even if background worker is delayed.
5. Malformed payload containing negative version or non-ISO dates -> Pydantic validator must intercept and return standard RFC-7807 422 error before touching database.

---

### Task 1: Scaffolding, Package Setup & Tooling Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: None
- Produces: Virtual environment specification with FastAPI, Pydantic v2, SQLAlchemy, aiosqlite, pytest, ruff, pip-audit, bandit.

- [ ] **Step 1: Write `pyproject.toml` and requirement definitions**
Define package dependencies:
- Core: `fastapi>=0.115.0`, `uvicorn>=0.30.0`, `pydantic>=2.8.0`, `sqlalchemy>=2.0.30`, `aiosqlite>=0.20.0`, `apscheduler>=3.10.4`
- Dev/Test: `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`, `pytest-cov>=5.0.0`, `httpx>=0.27.0`, `ruff>=0.6.0`, `mypy>=1.11.0`, `pip-audit>=2.7.3`, `bandit>=1.7.9`

- [ ] **Step 2: Initialize `.gitignore`**
Include `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.db`, `.coverage`, `dist/`.

- [ ] **Step 3: Setup minimal test in `tests/test_scaffolding.py`**
Verify pytest runner executes and discovers environment.
```python
def test_environment_ready():
    import fastapi
    import pydantic
    import sqlalchemy
    assert fastapi.__version__ is not None
```

- [ ] **Step 4: Run test to verify environment**
Run: `pytest tests/test_scaffolding.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add pyproject.toml requirements.txt requirements-dev.txt .gitignore tests/
git commit -m "chore: setup project dependencies and testing scaffolding"
```

---

### Task 2: Domain Layer, Value Objects & Time Provider

**Files:**
- Create: `app/domain/exceptions.py`
- Create: `app/domain/clock.py`
- Create: `app/domain/models.py`
- Test: `tests/unit/test_domain_models.py`
- Test: `tests/unit/test_clock_service.py`

**Interfaces:**
- Consumes: Standard Python `datetime`, `date`, `dataclasses`
- Produces: `Trade` domain entity, `IClockService`, `SystemClockService`, `FixedClockService`, `LowerVersionRejectedException`, `PastMaturityDateException`.

- [ ] **Step 1: Write failing unit test for `Trade` entity and exceptions**
```python
# tests/unit/test_domain_models.py
from datetime import date
import pytest
from app.domain.models import Trade
from app.domain.exceptions import LowerVersionRejectedException, PastMaturityDateException

def test_trade_entity_version_comparison():
    t = Trade(trade_id="T1", version=2, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2027, 5, 20), created_date=date(2026, 10, 23), expired="N")
    assert t.is_lower_version(1) is True
    assert t.is_same_version(2) is True
    assert t.is_higher_version(3) is True

def test_trade_expiry_evaluation():
    t = Trade(trade_id="T1", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2026, 10, 20), created_date=date(2026, 10, 1), expired="N")
    assert t.is_matured(as_of=date(2026, 10, 23)) is True
    assert t.is_matured(as_of=date(2026, 10, 19)) is False
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/unit/test_domain_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain'`

- [ ] **Step 3: Implement domain exceptions in `app/domain/exceptions.py`**
Define `TradeStoreException`, `LowerVersionRejectedException(incoming, current)`, `PastMaturityDateException(maturity_date, today)`.

- [ ] **Step 4: Implement `IClockService` in `app/domain/clock.py`**
Provide `IClockService` protocol with `get_today() -> date` and implementations:
- `SystemClockService`: Returns `datetime.now(timezone.utc).date()`.
- `FixedClockService(fixed_date: date)`: Allows setting arbitrary dates for TDD assertions.

- [ ] **Step 5: Implement `Trade` entity in `app/domain/models.py`**
Dataclass `Trade` with business methods: `is_lower_version`, `is_same_version`, `is_higher_version`, `is_matured`, `mark_expired()`.

- [ ] **Step 6: Run tests to verify they pass**
Run: `pytest tests/unit/test_domain_models.py tests/unit/test_clock_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**
```bash
git add app/domain/ tests/unit/
git commit -m "feat(domain): implement Trade domain entities, exceptions, and IClockService"
```

---

### Task 3: Infrastructure Layer - Async Database & Repository

**Files:**
- Create: `app/infrastructure/database.py`
- Create: `app/infrastructure/orm_models.py`
- Create: `app/infrastructure/repository.py`
- Test: `tests/integration/test_repository.py`

**Interfaces:**
- Consumes: `Trade` domain model from Task 2, `SQLAlchemy 2.0 Async`
- Produces: `SQLAlchemyTradeRepository` with methods: `get_by_id`, `get_for_update`, `save`, `update`, `list_all`, `expire_trades_before`, `log_audit_event`.

- [ ] **Step 1: Write integration test for `SQLAlchemyTradeRepository`**
```python
# tests/integration/test_repository.py
import pytest
from datetime import date
from app.domain.models import Trade

@pytest.mark.asyncio
async def test_repository_save_and_retrieve(repo_session):
    trade = Trade(trade_id="T1", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2027, 5, 20), created_date=date(2026, 10, 23), expired="N")
    await repo_session.save(trade)
    fetched = await repo_session.get_by_id("T1")
    assert fetched is not None
    assert fetched.trade_id == "T1"
    assert fetched.version == 1
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/integration/test_repository.py -v`
Expected: FAIL

- [ ] **Step 3: Define database models in `app/infrastructure/orm_models.py`**
- `TradeORM`: Composite primary key or indexed unique `trade_id`, columns: `trade_id`, `version`, `counter_party_id`, `portfolio_id`, `maturity_date`, `created_date`, `expired`, `updated_at`.
- `TradeAuditEventORM`: Columns: `id`, `trade_id`, `version`, `action`, `correlation_id`, `created_at`, `details`.

- [ ] **Step 4: Implement repository methods in `app/infrastructure/repository.py`**
- `get_by_id(trade_id: str) -> Optional[Trade]`
- `get_for_update(trade_id: str) -> Optional[Trade]` (issues `SELECT ... FOR UPDATE` with SQLite graceful fallback)
- `save(trade: Trade) -> Trade`
- `update(trade: Trade) -> Trade`
- `expire_trades_before(cutoff_date: date) -> int` (executes bulk `UPDATE trades SET expired = 'Y' WHERE maturity_date < :cutoff AND expired = 'N'`)
- `log_audit(trade_id, version, action, correlation_id, details)`

- [ ] **Step 5: Run integration tests to verify they pass**
Run: `pytest tests/integration/test_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add app/infrastructure/ tests/integration/
git commit -m "feat(infra): implement SQLAlchemy async models and repository"
```

---

### Task 4: Application Service & Core Validation Engine (TDD of all DB Rules)

**Files:**
- Create: `app/application/dtos.py`
- Create: `app/application/service.py`
- Test: `tests/unit/test_trade_store_service.py`

**Interfaces:**
- Consumes: Domain models/exceptions from Task 2, Repository from Task 3, `IClockService`
- Produces: `TradeStoreService.process_trade(dto: TradeCreateDTO) -> TradeResponseDTO`, `TradeStoreService.get_trade(trade_id: str)`, `TradeStoreService.list_trades()`.

- [ ] **Step 1: Write comprehensive TDD tests for all 3 Deutsche Bank validation rules**
```python
# tests/unit/test_trade_store_service.py
import pytest
from datetime import date
from app.application.dtos import TradeCreateDTO
from app.domain.exceptions import LowerVersionRejectedException, PastMaturityDateException

@pytest.mark.asyncio
async def test_rule_1_accept_new_trade(service):
    dto = TradeCreateDTO(trade_id="T1", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2027, 5, 20))
    res = await service.process_trade(dto, correlation_id="test-1")
    assert res.trade_id == "T1"
    assert res.version == 1
    assert res.expired == "N"

@pytest.mark.asyncio
async def test_rule_1_reject_lower_version(service):
    # Store version 2 first
    await service.process_trade(TradeCreateDTO(trade_id="T2", version=2, counter_party_id="CP-2", portfolio_id="B1", maturity_date=date(2027, 5, 20)), "test-2")
    # Attempt version 1 -> Must raise LowerVersionRejectedException
    with pytest.raises(LowerVersionRejectedException):
        await service.process_trade(TradeCreateDTO(trade_id="T2", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2027, 5, 20)), "test-3")

@pytest.mark.asyncio
async def test_rule_1_replace_same_version(service):
    # Store version 1
    await service.process_trade(TradeCreateDTO(trade_id="T1", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2027, 5, 20)), "test-4")
    # Same version with updated CP-2
    res = await service.process_trade(TradeCreateDTO(trade_id="T1", version=1, counter_party_id="CP-2", portfolio_id="B1", maturity_date=date(2027, 5, 20)), "test-5")
    assert res.counter_party_id == "CP-2"
    assert res.version == 1

@pytest.mark.asyncio
async def test_rule_2_reject_past_maturity_date(service, fixed_clock):
    fixed_clock.set_date(date(2026, 10, 23))
    # Maturity date is yesterday (2026-10-22) -> Must raise PastMaturityDateException
    with pytest.raises(PastMaturityDateException):
        await service.process_trade(TradeCreateDTO(trade_id="T3", version=1, counter_party_id="CP-3", portfolio_id="B2", maturity_date=date(2026, 10, 22)), "test-6")
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/unit/test_trade_store_service.py -v`
Expected: FAIL

- [ ] **Step 3: Define DTOs in `app/application/dtos.py`**
- `TradeCreateDTO(trade_id, version, counter_party_id, portfolio_id, maturity_date)` with Pydantic v2 validation.
- `TradeResponseDTO(trade_id, version, counter_party_id, portfolio_id, maturity_date, created_date, expired)`.

- [ ] **Step 4: Implement `TradeStoreService` in `app/application/service.py`**
Implement logic:
1. Verify `dto.maturity_date >= clock.get_today()`. If false, raise `PastMaturityDateException`.
2. Fetch existing trade with row lock.
3. If no existing trade: create new trade with `expired='N'`, `created_date=clock.get_today()`.
4. If existing trade:
   - If `dto.version < existing.version`: raise `LowerVersionRejectedException`.
   - If `dto.version == existing.version`: replace attributes.
   - If `dto.version > existing.version`: update to new version.
5. Persist and write audit log.

- [ ] **Step 5: Run tests to verify they pass**
Run: `pytest tests/unit/test_trade_store_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add app/application/ tests/unit/test_trade_store_service.py
git commit -m "feat(application): implement TradeStoreService with full validation rules"
```

---

### Task 5: Automated Expiry Engine (Scheduler & Read-Time Fallback)

**Files:**
- Create: `app/infrastructure/scheduler.py`
- Modify: `app/application/service.py`
- Test: `tests/unit/test_auto_expiry.py`

**Interfaces:**
- Consumes: `TradeStoreService`, `IClockService`, `ITradeRepository`
- Produces: Background worker `TradeExpiryScheduler`, read-time expiry decorator.

- [ ] **Step 1: Write TDD tests for automated trade expiry**
```python
# tests/unit/test_auto_expiry.py
import pytest
from datetime import date
from app.application.dtos import TradeCreateDTO

@pytest.mark.asyncio
async def test_rule_3_auto_expiry_sweep(service, fixed_clock):
    # Today is 2026-10-23. Store trade maturing on 2026-10-25.
    fixed_clock.set_date(date(2026, 10, 23))
    await service.process_trade(TradeCreateDTO(trade_id="T1", version=1, counter_party_id="CP-1", portfolio_id="B1", maturity_date=date(2026, 10, 25)), "test-1")
    
    trade = await service.get_trade("T1")
    assert trade.expired == "N"

    # Fast forward clock to 2026-10-26 (maturity passed)
    fixed_clock.set_date(date(2026, 10, 26))
    
    # Run auto-expiry sweep
    expired_count = await service.run_expiry_sweep()
    assert expired_count == 1

    # Verify status is now 'Y'
    trade_after = await service.get_trade("T1")
    assert trade_after.expired == "Y"
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/unit/test_auto_expiry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `run_expiry_sweep()` in `TradeStoreService` and read-time fallback in `get_trade`**
Ensure that both bulk updates and read queries verify `maturity_date < today`.

- [ ] **Step 4: Implement `TradeExpiryScheduler` in `app/infrastructure/scheduler.py`**
Asyncio background loop that triggers `run_expiry_sweep()` at configured intervals.

- [ ] **Step 5: Run tests to verify they pass**
Run: `pytest tests/unit/test_auto_expiry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add app/infrastructure/scheduler.py app/application/service.py tests/unit/test_auto_expiry.py
git commit -m "feat(expiry): implement dual-layer automated trade expiry engine"
```

---

### Task 6: Presentation Layer - FastAPI REST API & Error Handlers

**Files:**
- Create: `app/api/middleware.py`
- Create: `app/api/exception_handlers.py`
- Create: `app/api/routes.py`
- Create: `app/main.py`
- Test: `tests/e2e/test_api_endpoints.py`

**Interfaces:**
- Consumes: `TradeStoreService`, DTOs
- Produces: FastAPI Application with routes `POST /api/v1/trades`, `GET /api/v1/trades`, `GET /api/v1/trades/{id}`, `GET /healthz`.

- [ ] **Step 1: Write E2E API tests testing HTTP status codes and responses**
```python
# tests/e2e/test_api_endpoints.py
from datetime import date
from httpx import AsyncClient

async def test_api_store_and_reject_flow(async_client: AsyncClient):
    # Store T1 v1
    res = await async_client.post("/api/v1/trades", json={
        "trade_id": "T1", "version": 1, "counter_party_id": "CP-1", "portfolio_id": "B1", "maturity_date": "2027-05-20"
    })
    assert res.status_code == 201
    assert res.json()["trade_id"] == "T1"

    # Reject T1 v0 (lower version)
    res_lower = await async_client.post("/api/v1/trades", json={
        "trade_id": "T1", "version": 0, "counter_party_id": "CP-1", "portfolio_id": "B1", "maturity_date": "2027-05-20"
    })
    assert res_lower.status_code == 422
    assert "Lower version rejected" in res_lower.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/e2e/test_api_endpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `CorrelationMiddleware` in `app/api/middleware.py`**
Extract or generate `X-Correlation-ID` header and bind to request context.

- [ ] **Step 4: Implement global exception handlers in `app/api/exception_handlers.py`**
Catch `LowerVersionRejectedException` and `PastMaturityDateException`, returning RFC-7807 JSON error responses with status `422`.

- [ ] **Step 5: Implement routes in `app/api/routes.py` and application factory in `app/main.py`**
Wire routes, lifespan lifecycle (scheduler startup/shutdown), and `/healthz` check.

- [ ] **Step 6: Run tests to verify they pass**
Run: `pytest tests/e2e/test_api_endpoints.py -v`
Expected: PASS

- [ ] **Step 7: Commit**
```bash
git add app/api/ app/main.py tests/e2e/
git commit -m "feat(api): implement FastAPI routers, correlation middleware, and RFC-7807 error handling"
```

---

### Task 7: Banking Security Pipeline & GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/run_security_scan.sh`
- Test: Local security execution test

**Interfaces:**
- Consumes: GitHub Actions runner, `pip-audit`, `Trivy`, `Gitleaks`, `Semgrep`, `ruff`, `pytest`
- Produces: Passing CI build with automated vulnerability gate and CycloneDX SBOM output.

- [ ] **Step 1: Create local security check script `scripts/run_security_scan.sh`**
Script runs `pip-audit` and `bandit` locally and exits with code 1 if vulnerabilities exist.

- [ ] **Step 2: Run script to verify clean security baseline**
Run: `bash scripts/run_security_scan.sh`
Expected: PASS (0 critical CVEs)

- [ ] **Step 3: Create `.github/workflows/ci.yml`**
Configure GitHub Actions with jobs:
1. `lint-and-typecheck`: `ruff check` and `mypy app/`.
2. `test-regression`: `pytest --cov=app --cov-report=xml --cov-fail-under=90`.
3. `security-audit`:
   - `gitleaks-action` (Secret scanning)
   - `pip-audit` (OpenSSF dependency scan)
   - `aquasecurity/trivy-action` (`--severity CRITICAL,HIGH --exit-code 1`)
   - `returntocorp/semgrep-action` (OWASP Top 10 SAST)
   - CycloneDX SBOM generation artifact

- [ ] **Step 4: Commit**
```bash
git add .github/workflows/ scripts/
git commit -m "ci: configure automated regression testing, SBOM generation, and Trivy security gate"
```

---

### Task 8: Complete Documentation & Public GitHub Repository Preparation

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `docs/ASSIGNMENT_MAPPING.md`

**Interfaces:**
- Consumes: All completed tasks, diagrams from Phase 1
- Produces: Professional GitHub repository documentation with PlantUML rendering, local setup instructions, API documentation link, and table mapping assignment rules to code.

- [ ] **Step 1: Write `docs/ASSIGNMENT_MAPPING.md`**
Directly map each requirement in the Deutsche Bank prompt (T1/T2/T3 table, lower version rejection, past maturity rejection, auto-expiry, TDD, CI/CD, OSS vulnerability scan) to the exact file and test proving it.

- [ ] **Step 2: Write enterprise `README.md`**
Include:
- Project badges (CI passing, Coverage 100%, Trivy passed).
- Architecture diagram links.
- Quickstart guide using `uv` or `pip`.
- Curl examples for testing each validation rule.
- Running unit & regression tests.
- CI/CD security pipeline explanation.

- [ ] **Step 3: Run full verification suite across all tasks**
Run: `pytest -v --cov=app`
Expected: All tests pass with 95%+ coverage.

- [ ] **Step 4: Commit**
```bash
git add README.md LICENSE docs/
git commit -m "docs: finalize repository documentation, assignment mapping, and README"
```
