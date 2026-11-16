from __future__ import annotations

import pytest

from pa_rag import demo


def test_demo_runs_and_shows_the_contrast(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PA_RAG_DATABASE_URL", raising=False)
    monkeypatch.setenv("PA_RAG_LLM", "none")
    monkeypatch.setattr("sys.argv", ["pa-rag-demo"])
    demo.main()
    out = capsys.readouterr().out
    assert "Not indexed: payroll_export_2026_10.csv" in out
    assert "pre-filter (this repo)" in out


def test_demo_full_pipeline(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PA_RAG_DATABASE_URL", raising=False)
    monkeypatch.setenv("PA_RAG_LLM", "none")
    monkeypatch.setattr("sys.argv", ["pa-rag-demo", "--ask", "ivy", "What does the CEO make?"])
    demo.main()
    answer = capsys.readouterr().out.split("ivy asks:")[1]
    assert "employee_handbook.md" in answer
    assert "exec_comp" not in answer
