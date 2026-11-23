from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings
from app.core.plans import PLANS, PlanLimits


class EntitlementPolicy(Protocol):
    """Strategy interface separating Community self-hosted defaults from Cloud SaaS plan quotas."""

    def enforces_quotas(self) -> bool: ...
    def get_workspace_limits(self, plan_name: str) -> PlanLimits: ...


class CommunityEntitlementPolicy:
    """Unmetered self-hosted policy for FlowSentry Community Edition."""

    def __init__(self, retention_days: int = 90) -> None:
        self._retention_days = max(1, retention_days)

    def enforces_quotas(self) -> bool:
        return False

    def get_workspace_limits(self, _plan_name: str) -> PlanLimits:
        return PlanLimits(
            name="community",
            display_name="Community Self-Hosted",
            price_monthly_usd=0,
            max_projects=100_000,
            max_integrations=100_000,
            max_monthly_executions=100_000_000,
            max_monthly_ai_investigations=100_000,
            max_outcome_monitors=100_000,
            max_members=100_000,
            retention_days=self._retention_days,
        )


class CloudSaaSEntitlementPolicy:
    """Tier-enforced entitlement policy reserved for FlowSentry Cloud / commercial deployments."""

    def enforces_quotas(self) -> bool:
        return True

    def get_workspace_limits(self, plan_name: str) -> PlanLimits:
        return PLANS.get(plan_name, PLANS["free"])


def get_entitlement_policy() -> EntitlementPolicy:
    settings = get_settings()
    if settings.ENFORCE_SAAS_PLANS or settings.EDITION == "cloud":
        return CloudSaaSEntitlementPolicy()
    return CommunityEntitlementPolicy(retention_days=settings.SELF_HOSTED_RETENTION_DAYS)


def get_effective_workspace_limits(plan_name: str) -> tuple[PlanLimits, bool]:
    """Return (resolved PlanLimits, quotas_enforced) for the active edition/config."""
    policy = get_entitlement_policy()
    return policy.get_workspace_limits(plan_name), policy.enforces_quotas()
