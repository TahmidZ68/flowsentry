from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.schemas.intelligence import InvestigationOutputSchema

SYSTEM_PROMPT = """You are FlowSentry's Root-Cause Investigation Engine.
Analyze the provided SANITIZED execution evidence and return ONLY valid JSON matching this schema:
{
  "summary": "Short factual explanation of what failed",
  "root_cause_hypothesis": "Most likely underlying cause, clearly stating uncertainty",
  "confidence": 0.0 to 1.0,
  "evidence": ["List only facts directly observed in the provided input"],
  "possible_causes": ["Plausible explanations"],
  "recommended_actions": ["Safe, non-destructive remediation steps with why each helps"],
  "severity_assessment": "critical|high|medium|low|informational",
  "requires_human_review": true
}
STRICT RULES:
1. NEVER fabricate execution IDs, logs, timestamps, or metrics not present in the input.
2. Distinguish observed facts from hypotheses.
3. Never claim a fix has been applied.
4. Never recommend destructive actions (like deleting databases or disabling auth).
5. Never expose or guess secrets."""


@dataclass(frozen=True)
class ProviderResult:
    output: InvestigationOutputSchema
    provider: str
    model: str
    token_usage: dict[str, int]


class BaseAIProvider(Protocol):
    def analyze(self, evidence_payload: dict[str, Any]) -> ProviderResult: ...


class AIProviderError(Exception):
    """Raised when an external AI provider call fails or returns invalid output."""


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self._transport = transport

    def analyze(self, evidence_payload: dict[str, Any]) -> ProviderResult:
        try:
            with httpx.Client(timeout=20.0, transport=self._transport) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "temperature": 0.1,
                        "max_tokens": 900,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": json.dumps(evidence_payload)},
                        ],
                    },
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"OpenAI network error: {exc}") from exc

        if resp.status_code >= 400:
            raise AIProviderError(f"OpenAI API returned HTTP {resp.status_code}")

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = InvestigationOutputSchema.model_validate_json(content)
        except Exception as exc:
            raise AIProviderError(f"Invalid OpenAI structured JSON output: {exc}") from exc

        usage = data.get("usage") or {}
        return ProviderResult(
            output=parsed,
            provider="openai",
            model=self.model,
            token_usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
            },
        )


class GeminiProvider:
    def __init__(self, api_key: str, model: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self._transport = transport

    def analyze(self, evidence_payload: dict[str, Any]) -> ProviderResult:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        prompt_text = f"{SYSTEM_PROMPT}\n\nEVIDENCE:\n{json.dumps(evidence_payload)}"
        try:
            with httpx.Client(timeout=20.0, transport=self._transport) as client:
                resp = client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt_text}]}],
                        "generationConfig": {
                            "temperature": 0.1,
                            "maxOutputTokens": 900,
                            "responseMimeType": "application/json",
                        },
                    },
                )
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Gemini network error: {exc}") from exc

        if resp.status_code >= 400:
            raise AIProviderError(f"Gemini API returned HTTP {resp.status_code}")

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = InvestigationOutputSchema.model_validate_json(text)
        except Exception as exc:
            raise AIProviderError(f"Invalid Gemini structured JSON output: {exc}") from exc

        meta = data.get("usageMetadata") or {}
        return ProviderResult(
            output=parsed,
            provider="gemini",
            model=self.model,
            token_usage={
                "prompt_tokens": int(meta.get("promptTokenCount", 0)),
                "completion_tokens": int(meta.get("candidatesTokenCount", 0)),
                "total_tokens": int(meta.get("totalTokenCount", 0)),
            },
        )


class DeterministicFallbackAnalyzer:
    """Rule-based root-cause analyzer used when AI is unconfigured or unavailable."""

    def analyze(self, evidence_payload: dict[str, Any]) -> ProviderResult:
        inc = evidence_payload.get("incident", {})
        executions = evidence_payload.get("recent_executions", [])
        latest = executions[0] if executions else {}
        err_type = str(latest.get("error_type") or inc.get("error_type") or "EXECUTION_ERROR").upper()
        failed_node = latest.get("failed_node")
        err_summary = latest.get("error_summary") or inc.get("description") or "No error details recorded"
        occ_count = int(inc.get("occurrence_count", 1))
        wf_name = inc.get("workflow_name") or "Workflow"

        evidence: list[str] = [
            f"Incident '{inc.get('title')}' recorded {occ_count} occurrence(s) on workflow '{wf_name}'.",
        ]
        if failed_node:
            evidence.append(f"Observed failing node: '{failed_node}'.")
        if err_summary:
            evidence.append(f"Observed error summary: {str(err_summary)[:300]}")
        if evidence_payload.get("prior_incidents_count", 0) > 0:
            evidence.append(
                f"Detected {evidence_payload['prior_incidents_count']} historical incident(s) on this workflow."
            )

        if err_type == "HTTP_429":
            summary = f"Workflow '{wf_name}' failed due to upstream API rate limiting (HTTP 429)."
            hypothesis = (
                "Downstream API quota or burst rate limit was exceeded during node execution, "
                "causing requests to be throttled."
            )
            causes = [
                "Burst traffic or parallel workflow executions exceeded downstream API rate limits.",
                "Missing retry-with-backoff or batching on high-volume API calls.",
            ]
            actions = [
                "Enable exponential backoff / retry-on-fail in the failing node to absorb transient 429 bursts.",
                "Add batching or rate-limit throttling between iterations to stay within downstream API quotas.",
                "Inspect API provider quota usage and upgrade limits if sustained volume requires it.",
            ]
            confidence = 0.86
            sev = "high"
        elif err_type in {"HTTP_401", "HTTP_403"}:
            summary = f"Workflow '{wf_name}' failed authorization ({err_type}) against a downstream service."
            hypothesis = (
                "The stored API credential, OAuth token, or service permission used by the failing node "
                "is expired, revoked, or lacks required scopes."
            )
            causes = [
                "Expired OAuth refresh token or rotated API key in the workflow credential store.",
                "Insufficient role/scope permissions on the target account.",
            ]
            actions = [
                "Verify and refresh the credential configured on the failing node in the automation platform.",
                "Confirm the service account retains required API scopes for the target endpoint.",
            ]
            confidence = 0.88
            sev = "critical"
        elif err_type in {"HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504"}:
            summary = f"Downstream service returned an internal/gateway error ({err_type})."
            hypothesis = (
                "The external API experienced a server-side failure or transient outage while handling "
                "the workflow request."
            )
            causes = [
                "Temporary upstream service instability or maintenance window.",
                "Malformed or unexpected payload triggering an unhandled upstream server exception.",
            ]
            actions = [
                "Check the downstream provider status page and verify service availability.",
                "Configure bounded retries with backoff for 5xx responses and validate request payload shape.",
            ]
            confidence = 0.80
            sev = "high"
        elif err_type in {"TIMEOUT", "CONNECTION_ERROR"}:
            summary = f"Workflow '{wf_name}' encountered a network timeout or connection failure ({err_type})."
            hypothesis = (
                "Network connectivity between the workflow runner and target endpoint was interrupted "
                "or response latency exceeded the configured timeout."
            )
            causes = [
                "Upstream endpoint latency spike or firewall/DNS resolution issue.",
                "Node HTTP timeout configured too low for large payload processing.",
            ]
            actions = [
                "Verify target endpoint reachability and DNS/firewall rules.",
                "Increase node request timeout where appropriate and enable safe retries for idempotent calls.",
            ]
            confidence = 0.78
            sev = "high"
        elif err_type == "SILENT_FAILURE":
            summary = f"Outcome monitor detected a silent business-outcome failure on '{wf_name}'."
            hypothesis = (
                "The workflow completed without throwing a technical exception, but the expected "
                "downstream business outcome (record, field, webhook, or cadence) was not verified."
            )
            causes = [
                "Conditional branch skipped downstream creation step silently.",
                "Downstream API accepted the request asynchronously or dropped invalid fields without HTTP 4xx/5xx.",
            ]
            actions = [
                "Inspect the latest execution output and verify downstream target records exist.",
                "Add explicit output validation or confirmation checks after the critical business step.",
            ]
            confidence = 0.82
            sev = "high"
        elif err_type == "PERFORMANCE_ANOMALY":
            summary = f"Execution latency on '{wf_name}' deviated significantly above baseline/SLA."
            hypothesis = (
                "Downstream API slowness, increased payload volume, or unbatched loops increased execution duration."
            )
            causes = [
                "Growth in input batch size or external API degradation.",
                "Sequential processing inside loops without pagination limits.",
            ]
            actions = [
                "Inspect item counts in recent executions and compare against historical baseline.",
                "Paginate or split large payloads to keep workflow duration predictable.",
            ]
            confidence = 0.75
            sev = "medium"
        else:
            summary = f"Workflow '{wf_name}' failed with {err_type}."
            hypothesis = (
                "Execution halted at the failing step; inspect the sanitized error message and input structure "
                "to confirm whether data validation or external dependency state caused the error."
            )
            causes = [
                "Unexpected input payload structure or missing required field.",
                "Transient external dependency failure.",
            ]
            actions = [
                "Review the sanitized error summary and recent execution metadata.",
                "Re-run with verified test input in staging before applying workflow changes.",
            ]
            confidence = 0.65
            sev = "high" if occ_count >= 2 else "medium"

        if occ_count >= 3 and sev != "critical":
            sev = "critical"

        return ProviderResult(
            output=InvestigationOutputSchema(
                summary=summary,
                root_cause_hypothesis=hypothesis,
                confidence=confidence,
                evidence=evidence,
                possible_causes=causes,
                recommended_actions=actions,
                severity_assessment=sev,  # type: ignore[arg-type]
                requires_human_review=True,
            ),
            provider="deterministic",
            model="rule-engine-v1",
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )


def resolve_ai_provider(transport: httpx.BaseTransport | None = None) -> BaseAIProvider | None:
    settings = get_settings()
    if settings.AI_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.OPENAI_MODEL, transport=transport)
    if settings.AI_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL, transport=transport)
    return None
