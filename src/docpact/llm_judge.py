"""docpact.llm_judge — usa un LLM para evaluar si un test verifica la regla.

Mejora #8 de docpact. Cierra el gap que las heuristicas estaticas
(test_quality de Mejora #3) no cierran: tests que pasan las heuristicas
pero NO verifican la regla de negocio (e.g., 'assert True', tests
vacios, tests que importan pero no llaman a la funcion relevante).

API OpenAI-compatible: funciona con OpenAI, OpenRouter, Azure,
cualquier provider que exponga /v1/chat/completions.

Config via env:
- DOCPACT_LLM_API_KEY     (requerido para llamar al LLM)
- DOCPACT_LLM_BASE_URL    (default: https://api.openai.com/v1/chat/completions)
- DOCPACT_LLM_MODEL       (default: gpt-4o-mini)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests


DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

_PROMPT_TEMPLATE = """Eres un auditor de tests. Dada una regla de negocio y el codigo de un test, \
evalua si el test realmente verifica la regla.

Regla de negocio: {rn_descripcion}

Codigo del test:
```python
{test_code}
```

Responde UNICAMENTE con un objeto JSON con esta estructura exacta:
{{
  "verifica": true | false,
  "confidence": 0.0 a 1.0,
  "razon": "una frase corta explicando por que"
}}

Criterios:
- "verifica": true solo si el test EJECUTA el codigo que implementa la regla y verifica su efecto
- "verifica": false si el test es trivial (assert True), vacio, no llama a la funcion, o solo importa sin probar
- "confidence": tu nivel de certeza en la evaluacion (0.0 = inseguro, 1.0 = muy seguro)
"""


@dataclass(frozen=True)
class LLMScore:
    """Resultado de evaluar un test con el LLM."""

    verifica: bool
    confidence: float
    razon: str


# ──────────────────── _build_prompt ────────────────────


def _build_prompt(rn_descripcion: str, test_code: str) -> str:
    """Construye el prompt para el LLM con la regla y el test."""
    return _PROMPT_TEMPLATE.format(rn_descripcion=rn_descripcion, test_code=test_code)


# ──────────────────── _parse_llm_response ────────────────────


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_llm_response(texto: str) -> Optional[LLMScore]:
    """Parsea la respuesta del LLM, tolerando wrappers markdown.

    Acepta:
    - JSON puro en una linea
    - JSON envuelto en ```json ... ```
    - JSON embebido en prosa

    Retorna None si no se puede parsear un JSON valido con los
    campos requeridos (verifica, confidence, razon).
    """
    # Intento 1: parsear todo el texto como JSON
    candidatos = [texto.strip()]

    # Intento 2: extraer bloque ```json ... ```
    m = _JSON_BLOCK.search(texto)
    if m:
        candidatos.append(m.group(1))

    # Intento 3: buscar el primer {...} completo
    brace_match = re.search(r"\{[^{}]*\}", texto, re.DOTALL)
    if brace_match:
        candidatos.append(brace_match.group(0))

    for candidato in candidatos:
        try:
            data = json.loads(candidato)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if not all(k in data for k in ("verifica", "confidence", "razon")):
            continue
        try:
            return LLMScore(
                verifica=bool(data["verifica"]),
                confidence=float(data["confidence"]),
                razon=str(data["razon"]),
            )
        except (TypeError, ValueError):
            continue

    return None


# ──────────────────── _call_openai_compatible ────────────────────


def _call_openai_compatible(
    prompt: str,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> str:
    """Llama al endpoint /v1/chat/completions y retorna el content del primer choice."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,  # queremos eval determinista
    }
    response = requests.post(base_url, headers=headers, json=body, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# ──────────────────── evaluar_test_con_llm (pipeline) ────────────────────


def evaluar_test_con_llm(
    rn_descripcion: str,
    test_code: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[LLMScore]:
    """Pipeline: construye prompt, llama al LLM, parsea respuesta.

    Returns:
        LLMScore si el LLM respondio JSON parseable con los campos
        requeridos, None en caso contrario (incluyendo errores HTTP).
    """
    api_key = api_key or os.environ.get("DOCPACT_LLM_API_KEY", "")
    base_url = base_url or os.environ.get("DOCPACT_LLM_BASE_URL", DEFAULT_BASE_URL)
    model = model or os.environ.get("DOCPACT_LLM_MODEL", DEFAULT_MODEL)

    if not api_key:
        return None

    prompt = _build_prompt(rn_descripcion, test_code)
    try:
        texto = _call_openai_compatible(
            prompt=prompt, api_key=api_key, base_url=base_url, model=model
        )
    except (requests.RequestException, KeyError, IndexError):
        return None

    return _parse_llm_response(texto)
