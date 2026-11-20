from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings


class LLMError(RuntimeError):
    """Raised when an OpenAI-compatible endpoint cannot return usable JSON."""


class LLMClient:
    @property
    def configured(self) -> bool:
        return bool(settings.llm_api_key)

    async def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.configured:
            raise LLMError("LLM_API_KEY is not configured")

        endpoint = f"{settings.llm_api_base.rstrip('/')}/chat/completions"
        body = {
            "model": settings.llm_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(endpoint, headers=headers, json=body)

                # Some OpenAI-compatible providers reject response_format.
                if response.status_code == 400:
                    body.pop("response_format", None)
                    response = await client.post(endpoint, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM connection failed: {exc}") from exc

        if response.is_error:
            raise LLMError(
                f"LLM request failed with HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("LLM response does not contain message content") from exc

        if isinstance(content, list):
            content = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            )
        if not isinstance(content, str):
            raise LLMError("LLM message content is not text")

        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM message content is not valid JSON") from exc
        if not isinstance(result, dict):
            raise LLMError("LLM JSON root must be an object")
        return result


llm_client = LLMClient()
