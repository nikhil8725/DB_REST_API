from datetime import date

from app.domain.models import Trade


def test_trade_entity_normalization():
    t = Trade(
        trade_id="t1",
        version=1,
        counter_party_id="cp-1",
        portfolio_id="b1",
        maturity_date=date(2027, 5, 20),
        created_date=date(2026, 10, 23),
        expired="N",
    )
    assert t.trade_id == "T1"
    assert t.counter_party_id == "CP-1"
    assert t.portfolio_id == "B1"


def test_trade_entity_version_comparison():
    t = Trade(
        trade_id="T1",
        version=2,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
        created_date=date(2026, 10, 23),
        expired="N",
    )
    assert t.is_lower_version(1) is True
    assert t.is_lower_version(2) is False
    assert t.is_same_version(2) is True
    assert t.is_higher_version(3) is True
    assert t.is_higher_version(2) is False


def test_trade_expiry_evaluation():
    t = Trade(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2026, 10, 20),
        created_date=date(2026, 10, 1),
        expired="N",
    )
    assert t.is_matured(as_of=date(2026, 10, 23)) is True
    assert t.is_matured(as_of=date(2026, 10, 19)) is False

    t.mark_expired()
    assert t.expired == "Y"
