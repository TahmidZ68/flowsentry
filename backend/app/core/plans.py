from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PlanLimits:
    name: str
    display_name: str
    price_monthly_usd: int
    max_projects: int
    max_integrations: int
    max_monthly_executions: int
    max_monthly_ai_investigations: int
    max_outcome_monitors: int
    max_members: int
    retention_days: int


PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        name="free",
        display_name="Free",
        price_monthly_usd=0,
        max_projects=2,
        max_integrations=2,
        max_monthly_executions=1000,
        max_monthly_ai_investigations=10,
        max_outcome_monitors=3,
        max_members=1,
        retention_days=30,
    ),
    "pro": PlanLimits(
        name="pro",
        display_name="Pro",
        price_monthly_usd=19,
        max_projects=5,
        max_integrations=5,
        max_monthly_executions=25000,
        max_monthly_ai_investigations=100,
        max_outcome_monitors=15,
        max_members=3,
        retention_days=90,
    ),
    "agency": PlanLimits(
        name="agency",
        display_name="Agency",
        price_monthly_usd=59,
        max_projects=25,
        max_integrations=25,
        max_monthly_executions=150000,
        max_monthly_ai_investigations=500,
        max_outcome_monitors=75,
        max_members=15,
        retention_days=180,
    ),
    "business": PlanLimits(
        name="business",
        display_name="Business",
        price_monthly_usd=149,
        max_projects=100,
        max_integrations=100,
        max_monthly_executions=1000000,
        max_monthly_ai_investigations=2500,
        max_outcome_monitors=300,
        max_members=50,
        retention_days=365,
    ),
}


def get_plan_limits(plan_name: str) -> PlanLimits:
    return PLANS.get(plan_name, PLANS["free"])


class BillingProvider(Protocol):
    """Abstraction reserved for future Stripe subscription integration."""

    def create_checkout_session(self, workspace_id: str, target_plan: str) -> str: ...
    def handle_webhook(self, payload: bytes, signature: str) -> None: ...


class NoopBillingProvider:
    """Placeholder billing provider until Stripe is connected."""

    def create_checkout_session(self, workspace_id: str, target_plan: str) -> str:
        raise NotImplementedError("Billing checkout is not enabled in this release")

    def handle_webhook(self, payload: bytes, signature: str) -> None:
        raise NotImplementedError("Billing webhooks are not enabled in this release")
