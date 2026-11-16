from __future__ import annotations

import json
import logging

import pytest

from pa_rag.bootstrap import AppState


def test_audit_log_records_ids_never_content(
    state: AppState, caplog: pytest.LogCaptureFixture
) -> None:
    cora = state.directory.resolve("cora")
    with caplog.at_level(logging.INFO, logger="pa_rag.audit"):
        state.service.ask(cora, "What is the CEO's salary and bonus?")
    record = json.loads(caplog.records[-1].getMessage())
    assert record["user"] == "cora"
    assert any(c.startswith("exec_comp_2026.md#") for c in record["chunks"])
    assert "410,000" not in caplog.text
    assert "salary" not in caplog.text  # not even the question
