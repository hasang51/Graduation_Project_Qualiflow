from __future__ import annotations

import importlib

from config.settings import reset_settings_cache


def test_anthropic_missing_does_not_break_unrelated_imports():
    reset_settings_cache()
    mod = importlib.import_module("app.services.review_policy")
    assert hasattr(mod, "apply_review_policy")


def test_anthropic_client_lazy_init(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reset_settings_cache()
    from app.services.anthropic_client import get_anthropic_client, reset_anthropic_client_cache

    reset_anthropic_client_cache()
    try:
        get_anthropic_client()
        raised = False
    except RuntimeError:
        raised = True
    assert raised
