"""Tests para docpact.llm_judge (Mejora #8 — LLM-as-judge).

Cubre:
- _build_prompt: incluye la regla y el test
- _parse_llm_response: parsea JSON valido, maneja invalido
- _call_openai_compatible: HTTP request con auth (mocked)
- evaluar_test_con_llm: pipeline completo
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from docpact.llm_judge import (
    LLMScore,
    _build_prompt,
    _call_openai_compatible,
    _parse_llm_response,
    evaluar_test_con_llm,
)


# ──────────────────── _build_prompt ────────────────────


def test_build_prompt_incluye_regla_y_test():
    """El prompt debe mencionar la regla y mostrar el codigo del test."""
    prompt = _build_prompt(
        rn_descripcion="solo admins pueden suspender tickets",
        test_code="def test_x(): assert suspender(usuario='admin') is None",
    )
    assert "solo admins pueden suspender tickets" in prompt
    assert "suspender(usuario='admin')" in prompt
    # Debe pedir respuesta en JSON estructurado
    assert "verifica" in prompt.lower() or "json" in prompt.lower()


# ──────────────────── _parse_llm_response ────────────────────


def test_parse_llm_response_json_puro():
    """Si el LLM responde JSON puro, lo parsea."""
    texto = json.dumps({"verifica": True, "confidence": 0.85, "razon": "ok"})
    score = _parse_llm_response(texto)
    assert score.verifica is True
    assert score.confidence == 0.85
    assert "ok" in score.razon


def test_parse_llm_response_json_en_bloque_markdown():
    """Si el LLM responde ```json ... ```, extrae y parsea el JSON."""
    texto = (
        "Aqui esta mi evaluacion:\n"
        "```json\n"
        + json.dumps({"verifica": False, "confidence": 0.9, "razon": "no verifica"})
        + "\n```\n"
        "Espero que sirva."
    )
    score = _parse_llm_response(texto)
    assert score.verifica is False
    assert score.confidence == 0.9
    assert "no verifica" in score.razon


def test_parse_llm_response_json_invalido_retorna_none():
    """Si la respuesta no tiene JSON parseable, retorna None."""
    texto = "Esto no es JSON, es solo texto sin estructura."
    assert _parse_llm_response(texto) is None


def test_parse_llm_response_json_sin_campos_requeridos_retorna_none():
    """Si el JSON no tiene verifica/confidence/razon, retorna None."""
    texto = json.dumps({"foo": "bar", "baz": 1})
    assert _parse_llm_response(texto) is None


# ──────────────────── _call_openai_compatible ────────────────────


def test_call_openai_compatible_manda_request_con_auth(monkeypatch):
    """_call_openai_compatible debe hacer POST con Bearer auth y leer respuesta."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"verifica": True, "confidence": 0.9, "razon": "ok"})}}]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("docpact.llm_judge.requests.post", return_value=fake_response) as mock_post:
        texto = _call_openai_compatible(
            prompt="evaluar test X",
            api_key="sk-test",
            base_url="https://api.example.com/v1/chat/completions",
            model="gpt-test",
        )

    assert "verifica" in texto
    # Verificar que mando Authorization header
    call_kwargs = mock_post.call_args.kwargs
    assert "headers" in call_kwargs
    assert "Bearer sk-test" in call_kwargs["headers"]["Authorization"]
    # Verificar que mando el prompt en el body
    body = call_kwargs["json"]
    assert body["model"] == "gpt-test"
    assert "evaluar test X" in body["messages"][0]["content"]


# ──────────────────── evaluar_test_con_llm (integracion) ────────────────────


def test_evaluar_test_con_llm_retorna_score_cuando_llm_responde(monkeypatch):
    """Pipeline: rule + test code + mock LLM -> LLMScore parseado."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"verifica": True, "confidence": 0.95, "razon": "el test cubre el caso"})}}]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("docpact.llm_judge.requests.post", return_value=fake_response):
        score = evaluar_test_con_llm(
            rn_descripcion="solo admins pueden suspender",
            test_code="def test_x(): assert suspender(usuario='admin') is None",
            api_key="sk-test",
        )

    assert score is not None
    assert score.verifica is True
    assert score.confidence == 0.95


def test_evaluar_test_con_llm_retorna_none_si_llm_falla(monkeypatch):
    """Si el LLM devuelve texto no parseable, retorna None."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "no se pudo evaluar"}}]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("docpact.llm_judge.requests.post", return_value=fake_response):
        score = evaluar_test_con_llm(
            rn_descripcion="regla X",
            test_code="def test(): pass",
            api_key="sk-test",
        )

    assert score is None
