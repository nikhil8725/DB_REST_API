from datetime import date

from app.domain.clock import FixedClockService, SystemClockService


def test_fixed_clock_service():
    fixed = date(2026, 10, 23)
    clock = FixedClockService(fixed_date=fixed)
    assert clock.get_today() == fixed

    new_date = date(2027, 1, 1)
    clock.set_date(new_date)
    assert clock.get_today() == new_date


def test_system_clock_service():
    clock = SystemClockService()
    today = clock.get_today()
    assert isinstance(today, date)
