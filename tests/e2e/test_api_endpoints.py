import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database import Base, get_db_session
from app.main import create_app, lifespan


@pytest_asyncio.fixture
async def client():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db_session():
        async with test_session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    res = await client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_e2e_assignment_table_scenarios(client: AsyncClient):
    # 1. Ingest T1 Version 1
    res1 = await client.post(
        "/api/v1/trades",
        json={
            "trade_id": "T1",
            "version": 1,
            "counter_party_id": "CP-1",
            "portfolio_id": "B1",
            "maturity_date": "2027-05-20",
        },
    )
    assert res1.status_code == 201
    assert res1.json()["trade_id"] == "T1"

    # 2. Ingest T2 Version 2
    res2 = await client.post(
        "/api/v1/trades",
        json={
            "trade_id": "T2",
            "version": 2,
            "counter_party_id": "CP-2",
            "portfolio_id": "B1",
            "maturity_date": "2027-05-20",
        },
    )
    assert res2.status_code == 201

    # 3. Attempt T2 Version 1 (Lower Version -> MUST REJECT WITH 422)
    res_lower = await client.post(
        "/api/v1/trades",
        json={
            "trade_id": "T2",
            "version": 1,
            "counter_party_id": "CP-1",
            "portfolio_id": "B1",
            "maturity_date": "2027-05-20",
        },
    )
    assert res_lower.status_code == 422
    assert "rejected" in res_lower.json()["detail"]

    # 4. Attempt T3 Version 3 with past maturity date 2014-05-20 -> MUST REJECT WITH 422
    res_past = await client.post(
        "/api/v1/trades",
        json={
            "trade_id": "T3",
            "version": 3,
            "counter_party_id": "CP-3",
            "portfolio_id": "B2",
            "maturity_date": "2014-05-20",
        },
    )
    assert res_past.status_code == 422
    assert "earlier than current date" in res_past.json()["detail"]

    # 5. Overwrite T1 Version 1 with same version but CP-2
    res_same = await client.post(
        "/api/v1/trades",
        json={
            "trade_id": "T1",
            "version": 1,
            "counter_party_id": "CP-2",
            "portfolio_id": "B1",
            "maturity_date": "2027-05-20",
        },
    )
    assert res_same.status_code == 200
    assert res_same.json()["counter_party_id"] == "CP-2"

    # 6. Fetch single trade
    res_single = await client.get("/api/v1/trades/T1")
    assert res_single.status_code == 200
    assert res_single.json()["trade_id"] == "T1"

    # 7. Query all trades with pagination
    list_res = await client.get("/api/v1/trades?limit=10&offset=0")
    assert list_res.status_code == 200
    paginated_data = list_res.json()
    assert paginated_data["total"] == 2
    assert paginated_data["limit"] == 10
    assert paginated_data["offset"] == 0
    assert len(paginated_data["items"]) == 2

    # 8. Query with filtering by portfolio_id
    b1_res = await client.get("/api/v1/trades?portfolio_id=B1")
    assert b1_res.status_code == 200
    assert b1_res.json()["total"] == 2

    empty_res = await client.get("/api/v1/trades?portfolio_id=UNKNOWN_PORTFOLIO")
    assert empty_res.status_code == 200
    assert empty_res.json()["total"] == 0

    # 9. Query nonexistent trade -> 404
    res_404 = await client.get("/api/v1/trades/UNKNOWN")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_correlation_id_propagation(client: AsyncClient):
    custom_cid = "corr-header-db-12345"
    res = await client.get("/healthz", headers={"X-Correlation-ID": custom_cid})
    assert res.headers.get("x-correlation-id") == custom_cid


@pytest.mark.asyncio
async def test_app_lifespan():
    app = create_app()
    async with lifespan(app):
        assert app is not None
