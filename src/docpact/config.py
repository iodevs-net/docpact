"""Configuración de docpact — lectura de docpact.toml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


# Patrones por defecto (documentados en the-agent-code-manifesto)
PATRONES_DEFECTO: dict[str, list[str]] = {
    # Sin paréntesis — el AST walker extrae nombres de función, no código fuente
    "db_write": [".create", ".save", ".update", ".bulk_create", ".delete", "transaction.atomic"],
    "email": ["send_mail", "EmailMessage", "_enviar_email", "enviar_email_async"],
    "external": ["requests.", "httpx.", "urllib.request"],
    "audit": [
        "BitacoraEntry.objects.create", "AuditService.log",
        "registrar_evento_bitacora",
    ],
    "notification": [
        "NotificacionService.", "_notificar_", "notificar_",
        "_notificar_inicio_trabajo",
    ],
    "sesion": ["SesionTrabajo.objects.", "SessionService.", "iniciar_sesion", "detener_sesion"],
}

EXCLUIDOS_DEFECTO = {
    "__pycache__", ".venv", "venv", "node_modules",
    ".git", "migrations", ".pytest_cache", "__init__.py",
}


class DocpactConfig:
    """Configuración de docpact.

    Se lee de docpact.toml, con defaults sensibles.
    """

    def __init__(
        self,
        strict: bool = False,
        min_score: int = 75,
        exclude: Optional[set[str]] = None,
        patrones_side_effects: Optional[dict[str, list[str]]] = None,
        rn_prefix: str = "RN-",
    ):
        self.strict = strict
        self.min_score = min_score
        self.exclude = exclude or EXCLUIDOS_DEFECTO
        self.patrones_side_effects = patrones_side_effects or PATRONES_DEFECTO
        self.rn_prefix = rn_prefix
        self._patrones_compilados: Optional[dict[str, list[re.Pattern]]] = None

    @property
    def patrones_compilados(self) -> dict[str, list[re.Pattern]]:
        """Patrones compilados por categoría para matching rápido."""
        if self._patrones_compilados is None:
            self._patrones_compilados = {}
            for categoria, patrones in self.patrones_side_effects.items():
                self._patrones_compilados[categoria] = [
                    re.compile(re.escape(p)) for p in patrones
                ]
        return self._patrones_compilados

    def debe_excluir(self, path: Path) -> bool:
        """Verifica si un path debe ser excluido del análisis."""
        # Normalizar exclude: "tests/" → "tests"
        excl = {e.rstrip("/") for e in self.exclude}
        # Separar patrones con glob (*) para matching por prefijo
        prefijos = {e.rstrip("*") for e in excl if e.endswith("*")}
        exactos = {e for e in excl if not e.endswith("*")}
        for parte in path.parts:
            if parte in exactos:
                return True
            for prefijo in prefijos:
                if parte.startswith(prefijo):
                    return True
            # También excluir por extensión si es un archivo
            if parte == path.name:
                if path.suffix not in (".py", ""):
                    return True
        return False

    @classmethod
    def desde_toml(cls, ruta: str | Path) -> "DocpactConfig":
        """Lee configuración desde un archivo docpact.toml.

        Si no existe o hay error, retorna configuración por defecto.
        """
        path = Path(ruta)
        if not path.exists():
            return cls()

        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (ImportError, tomllib.TOMLDecodeError):
            # Python <3.11 o archivo mal formado
            return cls()

        docpact_cfg = data.get("docpact", {})
        strict = docpact_cfg.get("strict", False)
        min_score = docpact_cfg.get("min_score", 75)
        exclude = set(docpact_cfg.get("exclude", []))

        patrones = dict(PATRONES_DEFECTO)
        se_cfg = docpact_cfg.get("side_effects", {})
        for categoria, lista in se_cfg.items():
            if isinstance(lista, list):
                patrones[categoria] = lista

        rn_prefix = docpact_cfg.get("rules", {}).get("rn_prefix", "RN-")

        return cls(
            strict=strict,
            min_score=min_score,
            exclude=exclude if exclude else None,
            patrones_side_effects=patrones,
            rn_prefix=rn_prefix,
        )


def _serializar_config(config: DocpactConfig) -> dict:
    """Serializa la config para reportes."""
    return {
        "strict": config.strict,
        "min_score": config.min_score,
        "exclude": sorted(config.exclude),
        "categorias_side_effects": list(config.patrones_side_effects.keys()),
        "rn_prefix": config.rn_prefix,
    }
