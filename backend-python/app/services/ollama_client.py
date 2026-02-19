"""
Unified Ollama Client

Single shared client for all LLM interactions. Replaces the 3 separate
implementations that existed in:
  - enhanced_llm_service._call_llm()
  - base_pipeline._call_llm()
  - intelligence_extraction_service._call_llm()

Features:
  - Configurable per-call model, temperature, num_predict, num_ctx
  - Retry with exponential backoff
  - Concurrency control via asyncio.Semaphore
  - Structured logging (no print statements)
"""

import asyncio
import json
import re
from typing import Optional, Dict, Any

import httpx

from app.core.config import settings
from app.utils.logger import logger


class OllamaClient:
    """Shared async client for Ollama API calls."""

    # Class-level semaphore: limits concurrent LLM calls across the whole app
    _semaphore: Optional[asyncio.Semaphore] = None
    _max_concurrent: int = 2

    def __init__(self):
        self.base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.default_model = getattr(settings, "DEFAULT_MODEL", "phi")
        self.default_temperature = getattr(settings, "DEFAULT_TEMPERATURE", 0.1)
        self.default_timeout = getattr(settings, "LLM_TIMEOUT", 180)
        self.default_max_retries = getattr(settings, "LLM_MAX_RETRIES", 2)
        self.default_num_predict = getattr(settings, "LLM_NUM_PREDICT", 4096)
        logger.info(f"OllamaClient initialized: base_url={self.base_url}, model={self.default_model}")

    # ------------------------------------------------------------------
    # Semaphore
    # ------------------------------------------------------------------
    @classmethod
    def get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._max_concurrent)
        return cls._semaphore

    # ------------------------------------------------------------------
    # Core generate call
    # ------------------------------------------------------------------
    async def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        num_predict: Optional[int] = None,
        num_ctx: Optional[int] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        use_semaphore: bool = True,
        caller: str = "",
        format: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send a prompt to Ollama and return the raw text response.

        Args:
            prompt: The full prompt string.
            model: Override default model.
            temperature: Override default temperature.
            num_predict: Max tokens to generate.
            num_ctx: Context window size.
            timeout: Request timeout in seconds.
            max_retries: Number of retry attempts.
            use_semaphore: Whether to use the concurrency limiter.
            caller: Identifier for log messages (e.g. pipeline name).
            format: Response format - set to "json" to force JSON output.

        Returns:
            Raw response text or None on total failure.
        """
        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        num_predict = num_predict or self.default_num_predict
        timeout = timeout or self.default_timeout
        max_retries = max_retries if max_retries is not None else self.default_max_retries

        endpoint = f"{self.base_url}/api/generate"
        prefix = f"[{caller}] " if caller else ""

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        if num_ctx:
            payload["options"]["num_ctx"] = num_ctx
        if format:
            payload["format"] = format

        async def _do_call() -> Optional[str]:
            last_error: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"{prefix}LLM call attempt {attempt}/{max_retries} "
                        f"model={model} prompt={len(prompt)} chars"
                    )
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(endpoint, json=payload)
                        if resp.status_code != 200:
                            logger.error(f"{prefix}Ollama HTTP {resp.status_code}: {resp.text[:500]}")
                            resp.raise_for_status()
                        data = resp.json()
                        result = data.get("response", "")
                        if not result:
                            raise ValueError("Empty response from Ollama")
                        logger.info(f"{prefix}LLM response: {len(result)} chars")
                        return result

                except httpx.ConnectError as exc:
                    last_error = exc
                    logger.error(f"{prefix}Ollama connection failed (is it running?): {exc}")
                    break  # no point retrying a connection failure
                except httpx.TimeoutException as exc:
                    last_error = exc
                    logger.warning(f"{prefix}Ollama timeout after {timeout}s (attempt {attempt})")
                except Exception as exc:
                    last_error = exc
                    logger.warning(f"{prefix}LLM call failed (attempt {attempt}): {exc}")

                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

            logger.error(f"{prefix}All {max_retries} LLM attempts failed: {last_error}")
            return None

        if use_semaphore:
            async with self.get_semaphore():
                return await _do_call()
        else:
            return await _do_call()

    # ------------------------------------------------------------------
    # Generate + JSON parse convenience
    # ------------------------------------------------------------------
    async def generate_json(
        self,
        prompt: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Call generate() with JSON format enforcement, then parse the result.
        Returns None if LLM fails or JSON is unparseable.
        """
        # Force JSON format in Ollama API
        kwargs.setdefault("format", "json")
        raw = await self.generate(prompt, **kwargs)
        if raw is None:
            return None
        return parse_llm_json(raw)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    async def test_connection(self) -> Dict[str, Any]:
        """Quick health check."""
        endpoint = f"{self.base_url}/api/generate"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "model": self.default_model,
                        "prompt": 'Respond with just "OK"',
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "model": self.default_model,
                    "endpoint": endpoint,
                    "response": data.get("response", ""),
                }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# ======================================================================
# Shared JSON parser  (P1-B)
# Consolidates base_pipeline._parse_llm_json, enhanced_llm_service._parse_json_response,
# and intelligence_extraction_service._parse_llm_response JSON extraction logic.
# ======================================================================

def parse_llm_json(response: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extract a JSON object or array from a raw LLM response.

    Handles: markdown code fences, leading prose, trailing commas,
    truncated output (attempts bracket-closure repair).
    """
    if not response:
        return None

    text = response.strip()

    # 1. Strip markdown code blocks
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = re.sub(r"`", "", text)

    # 2. Remove common LLM preamble
    for prefix in (
        "Here is the JSON:", "Here's the JSON:", "JSON:", "Output:",
        "Result:", "Response:",
    ):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    # 3. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 4. Try to locate JSON object or array
    for opener, closer in (('{', '}'), ('[', ']')):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Fix trailing commas and retry
                fixed = re.sub(r",(\s*[}\]])", r"\1", candidate)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

    # 5. Attempt truncated-JSON repair
    start = text.find('{')
    if start == -1:
        start = text.find('[')
    if start != -1:
        fragment = text[start:]
        repaired = _repair_truncated_json(fragment)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

    logger.warning(f"JSON parse failed for response: {response[:300]}...")
    return None


def _repair_truncated_json(json_str: str) -> Optional[str]:
    """Close unclosed brackets/braces so truncated JSON can be parsed."""
    open_braces = json_str.count('{') - json_str.count('}')
    open_brackets = json_str.count('[') - json_str.count(']')
    if open_braces <= 0 and open_brackets <= 0:
        return None

    repaired = json_str.rstrip()
    # Remove trailing comma
    if repaired.endswith(','):
        repaired = repaired[:-1]
    # Remove incomplete key-value pair at end
    repaired = re.sub(r',?\s*"[^"]*":\s*$', '', repaired)
    repaired = re.sub(r',?\s*"[^"]*":\s*"[^"]*$', '', repaired)
    repaired = repaired.rstrip().rstrip(',')

    repaired += ']' * max(0, open_brackets)
    repaired += '}' * max(0, open_braces)
    logger.debug(f"JSON repair: closed {open_brackets} brackets, {open_braces} braces")
    return repaired


# ======================================================================
# Global singleton
# ======================================================================
ollama_client = OllamaClient()
