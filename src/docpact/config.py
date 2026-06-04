"""Configuración de docpact — lectura de docpact.toml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


# Patrones por defecto (genéricos — sin referencias a ningún proyecto específico)
# Los patrones específicos de cada proyecto van en docpact.toml
PATRONES_DEFECTO: dict[str, list[str]] = {
    "db_write": [
        ".create",
        ".save",
        ".update",
        ".bulk_create",
        ".delete",
        "transaction.atomic",
    ],
    "email": ["send_mail", "EmailMessage"],
    "external": ["requests.", "httpx.", "urllib.request"],
    "audit": ["registrar_evento_bitacora"],
    "notification": ["_notificar_", "notificar_"],
}

EXCLUIDOS_DEFECTO = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    "migrations",
    ".pytest_cache",
    "__init__.py",
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
        warnings_suppress: Optional[list[str]] = None,
        rn_patrones: Optional[dict[str, dict[str, str]]] = None,
        modules: Optional[dict[str, dict]] = None,
        types_allowlist: Optional[set[str]] = None,
        run_tests: bool = True,
        run_runtime: bool = True,
        marker_honesty: Optional[dict] = None,
    ):
        self.strict = strict
        self.min_score = min_score
        self.exclude = exclude or EXCLUIDOS_DEFECTO
        self.patrones_side_effects = patrones_side_effects or PATRONES_DEFECTO
        self.rn_prefix = rn_prefix
        self.warnings_suppress = warnings_suppress or []
        self.rn_patrones = rn_patrones or {}
        self.modules = modules or {}
        self.types_allowlist: set[str] = types_allowlist or set()
        self.run_tests = run_tests
        self.run_runtime = run_runtime
        # Marker honesty: defaults conservadores
        mh = marker_honesty or {}
        self.marker_honesty_enabled: bool = mh.get("enabled", True)
        self.marker_honesty_max_rns: int = mh.get("max_rns_per_function", 5)
        self._patrones_compilados: Optional[dict[str, list[re.Pattern[str]]]] = None

    def debe_suprimir(self, mensaje: str) -> bool:
        """True si el mensaje contiene algún patrón de supresión."""
        if not self.warnings_suppress:
            return False
        for patron in self.warnings_suppress:
            if patron in mensaje:
                return True
        return False

    @property
    def patrones_compilados(self) -> dict[str, list[re.Pattern[str]]]:
        """Patrones compilados por categoría para matching rápido."""
        if self._patrones_compilados is None:
            self._patrones_compilados = {}
            for categoria, patrones in self.patrones_side_effects.items():
                compiled = []
                for p in patrones:
                    if p.startswith("."):
                        # Evitar falsos positivos como updated_at coincidiendo con .update
                        compiled.append(re.compile(r"\." + re.escape(p[1:]) + r"\b"))
                    else:
                        compiled.append(re.compile(re.escape(p)))
                self._patrones_compilados[categoria] = compiled
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
            if parte == path.name:
                if path.suffix not in (".py", ".ts", ".tsx", ".jsx", ""):
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
            import tomllib  # type: ignore[import-not-found]

            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (ImportError, tomllib.TOMLDecodeError):
            # Python <3.11 o archivo mal formado
            return cls()

        docpact_cfg = data.get("docpact", {})
        strict = docpact_cfg.get("strict", False)
        min_score = docpact_cfg.get("min_score", 75)
        exclude = set(docpact_cfg.get("exclude", []))
        run_tests = docpact_cfg.get("run_tests", True)

        patrones = dict(PATRONES_DEFECTO)
        se_cfg = docpact_cfg.get("side_effects", {})
        for categoria, lista in se_cfg.items():
            if isinstance(lista, list):
                patrones[categoria] = lista

        rn_prefix = docpact_cfg.get("rules", {}).get("rn_prefix", "RN-")

        warnings_cfg = docpact_cfg.get("warnings", {})
        warnings_suppress = warnings_cfg.get("suppress", [])

        rn_cfg = docpact_cfg.get("rn_patrones", {})
        rn_patrones = {}
        for rn_id, cfg in rn_cfg.items():
            # Acepta specs legacy (con 'patron') y semánticos (con 'type').
            if isinstance(cfg, dict) and ("patron" in cfg or "type" in cfg):
                rn_patrones[rn_id] = cfg

        # Types allowlist: tipos que nunca deben generar warning
        types_allowlist = set(docpact_cfg.get("types_allowlist", []))

        # Marker honesty config (sección [docpact.marker_honesty])
        mh_cfg = docpact_cfg.get("marker_honesty", {})

        # Cargar módulos desde docpact.toml (sección [modules])
        modules = dict(data.get("modules", {}))

        # Cargar modules.toml desde el mismo directorio (config de proyecto separada)
        modules_path = path.parent / "modules.toml"
        if modules_path.exists():
            try:
                with open(modules_path, "rb") as f:
                    modules_data = tomllib.load(f)
                modules_cfg = dict(modules_data.get("modules", {}))
                # modules.toml sobreescribe keys del docpact.toml
                modules_cfg.update(modules)
                modules = modules_cfg
            except (tomllib.TOMLDecodeError, Exception):
                pass

        return cls(
            strict=strict,
            min_score=min_score,
            exclude=exclude if exclude else None,
            patrones_side_effects=patrones,
            rn_prefix=rn_prefix,
            warnings_suppress=warnings_suppress,
            rn_patrones=rn_patrones,
            modules=modules,
            types_allowlist=types_allowlist if types_allowlist else None,
            run_tests=run_tests,
            marker_honesty=mh_cfg,
        )


def _serializar_config(config: DocpactConfig) -> dict[str, Any]:
    """Serializa la config para reportes."""
    return {
        "strict": config.strict,
        "min_score": config.min_score,
        "exclude": sorted(config.exclude),
        "categorias_side_effects": list(config.patrones_side_effects.keys()),
        "rn_prefix": config.rn_prefix,
        "modulos": list(config.modules.keys()),
        "types_allowlist": sorted(config.types_allowlist),
        "run_tests": config.run_tests,
    }
