"""Vigencia de suscripción según estado y fin de período."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.enums import SubscriptionStatus
from app.core.subscription_lifecycle import (
    is_period_expired,
    subscription_block_reason,
    subscription_is_usable,
    validate_subscription_period_status,
)
from app.schemas.subscription import SubscriptionAssign


def test_active_with_future_period_is_usable():
    end = datetime.now(timezone.utc) + timedelta(days=30)
    assert subscription_is_usable(SubscriptionStatus.ACTIVE, end) is True


def test_active_with_past_period_is_not_usable():
    end = datetime.now(timezone.utc) - timedelta(days=1)
    assert subscription_is_usable(SubscriptionStatus.ACTIVE, end) is False
    assert subscription_block_reason(SubscriptionStatus.ACTIVE, end) == "period_expired"


def test_suspended_is_never_usable():
    end = datetime.now(timezone.utc) + timedelta(days=30)
    assert subscription_is_usable(SubscriptionStatus.SUSPENDED, end) is False


def test_no_period_end_active_is_usable():
    assert subscription_is_usable(SubscriptionStatus.ACTIVE, None) is True


def test_assign_rejects_active_with_past_period():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with pytest.raises(ValidationError):
        SubscriptionAssign(
            plan_code="starter",
            status=SubscriptionStatus.ACTIVE,
            current_period_end=past,
        )


def test_assign_allows_cancelled_with_past_period():
    past = datetime.now(timezone.utc) - timedelta(days=10)
    row = SubscriptionAssign(
        plan_code="starter",
        status=SubscriptionStatus.CANCELLED,
        current_period_end=past,
    )
    assert row.status == SubscriptionStatus.CANCELLED


def test_validate_raises_for_trial_past():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(ValueError, match="active o trial"):
        validate_subscription_period_status(SubscriptionStatus.TRIAL, past)


def test_is_period_expired_naive_datetime():
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 15, 23, 0, 0)
    assert is_period_expired(end, now=now) is True
