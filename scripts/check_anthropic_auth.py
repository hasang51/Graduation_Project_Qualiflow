"""Minimal Anthropic auth smoke check.

Sends the smallest possible message to verify that the configured API key is
valid. The script NEVER prints the key (not even partially) and never prints
raw response headers. It exits with:

* ``0`` on success
* ``2`` when the key is missing
* ``3`` when the key is invalid / unauthorized
* ``4`` when Anthropic rate-limits or errors transiently
* ``5`` on network / other failures

Usage::

    python -m scripts.check_anthropic_auth
"""

from __future__ import annotations

import sys

from app.config import ENV_FILES_LOADED, settings


def main() -> int:
    if ENV_FILES_LOADED:
        print(f"env sources loaded: {', '.join(ENV_FILES_LOADED)}")
    else:
        print("env sources loaded: (process environment only)")

    if not settings.anthropic_api_key:
        print("FAIL: ANTHROPIC_API_KEY is not set in the environment or any loaded .env file.")
        return 2

    print(f"ANTHROPIC_API_KEY present: yes (length={len(settings.anthropic_api_key)})")
    print(f"Anthropic model: {settings.anthropic_model}")

    try:
        from anthropic import Anthropic
    except ImportError:
        print("FAIL: anthropic SDK is not installed. Run `pip install -r requirements.txt`.")
        return 5

    client = Anthropic(api_key=settings.anthropic_api_key)

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )
    except Exception as exc:  # noqa: BLE001 — we classify below
        name = type(exc).__name__
        # Scrub the message to avoid any chance of echoing secrets if the
        # underlying SDK ever embedded them in the error string.
        summary = str(exc).splitlines()[0][:200]
        lowered = f"{name} {summary}".lower()
        if "authentication" in lowered or "401" in lowered or "invalid x-api-key" in lowered:
            print(f"FAIL: authentication error ({name}). The API key is invalid or revoked.")
            return 3
        if "rate" in lowered or "429" in lowered or "overloaded" in lowered:
            print(f"FAIL: rate limit / overloaded ({name}).")
            return 4
        print(f"FAIL: request error ({name}): {summary}")
        return 5

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", "?") if usage else "?"
    output_tokens = getattr(usage, "output_tokens", "?") if usage else "?"
    stop_reason = getattr(response, "stop_reason", "?")
    print(
        "OK: Anthropic auth succeeded. "
        f"input_tokens={input_tokens} output_tokens={output_tokens} stop_reason={stop_reason}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
