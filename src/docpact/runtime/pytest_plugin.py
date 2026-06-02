import os
import sys
import tomllib
from functools import wraps
from pathlib import Path
import pytest
from docpact.checker.orchestrator import check_proyecto
from docpact.runtime.sentinels import sentinela_db, sentinela_disco, sentinela_email

# Mapa global de contratos de la sesión
_contratos_map = {}
_wrapped_functions = set()
_modo = "strict"
_runtime_enabled = False


def _runtime_habilitado(root_dir: Path) -> tuple[bool, str]:
    """Determina si el runtime debe activarse.

    Reglas (en orden de precedencia):
      1. DOCPACT_NO_RUNTIME=1 -> desactivado (compat historica)
      2. DOCPACT_RUNTIME=1   -> activado (opt-in explicito via env)
      3. [docpact.runtime] enabled = true en docpact.toml -> activado
      4. [docpact.runtime] enabled = false en docpact.toml -> desactivado
      5. Default: DESACTIVADO (antes era siempre activado)

    Returns:
        (habilitado, modo)
    """
    if os.environ.get("DOCPACT_NO_RUNTIME") == "1":
        return False, "off"

    if os.environ.get("DOCPACT_RUNTIME") == "1":
        # Tomar modo de toml si existe
        modo = _leer_modo_toml(root_dir)
        return True, modo

    # Sin env var: leer toml
    toml_path = root_dir / "docpact.toml"
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            docpact_cfg = data.get("docpact", {})
            runtime_cfg = docpact_cfg.get("runtime", {}) or data.get("runtime", {})
            enabled = runtime_cfg.get("enabled", False)
            modo = runtime_cfg.get("modo", "warning")
            return bool(enabled), modo
        except Exception:
            return False, "off"

    return False, "off"


def _leer_modo_toml(root_dir: Path) -> str:
    toml_path = root_dir / "docpact.toml"
    if not toml_path.exists():
        return "warning"
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        docpact_cfg = data.get("docpact", {})
        runtime_cfg = docpact_cfg.get("runtime", {}) or data.get("runtime", {})
        return runtime_cfg.get("modo", "warning")
    except Exception:
        return "warning"


def pytest_configure(config):
    """Escanea el proyecto usando AST en la configuración inicial de pytest.

    Construye el mapa de contratos estáticamente sin realizar imports.

    CAMBIO 2026-06-02: el runtime ahora es opt-in. Antes se activaba siempre,
    lo que generaba falsos positivos (ej. bloqueaba tests legitimos con
    db_write declarado correctamente). Para activar:
      - export DOCPACT_RUNTIME=1
      - o [docpact.runtime] enabled = true en docpact.toml
    """
    global _contratos_map, _modo, _runtime_enabled

    root_dir = Path(config.rootdir)
    enabled, modo = _runtime_habilitado(root_dir)

    if not enabled:
        # Default-off. Para activar, ver docstring de _runtime_habilitado.
        _modo = "off"
        _runtime_enabled = False
        return

    _modo = modo
    _runtime_enabled = True

    from docpact.config import DocpactConfig
    config_obj = DocpactConfig(run_tests=False)
    # Escaneo estático por AST — seguro y rápido, forzando run_tests=False
    resultado = check_proyecto(root_dir, config=config_obj)

    for archivo_res in resultado.archivos:
        for func_res in archivo_res.funciones:
            if func_res.tiene_contrato and func_res.contrato:
                try:
                    archivo_path = Path(func_res.archivo).resolve()
                    rel_path = archivo_path.relative_to(root_dir.resolve())
                except ValueError:
                    continue
                
                # Convertir ruta relativa a nombre de módulo calificado de python
                partes = list(rel_path.with_suffix("").parts)
                module_name = ".".join(partes)
                
                if module_name not in _contratos_map:
                    _contratos_map[module_name] = []
                    
                _contratos_map[module_name].append({
                    "nombre": func_res.nombre,
                    "contrato": func_res.contrato,
                    "archivo": str(rel_path),
                    "linea": func_res.linea
                })


@pytest.fixture(autouse=True, scope="session")
def docpact_runtime_wrapper(request):
    """Fixture de sesión autouse de pytest.

    Solo se activa si el runtime esta habilitado (opt-in via env o toml).
    Por defecto esta DESACTIVADO para no interferir con tests legitimos.

    Se ejecuta cuando Django y la base de datos de test ya están cargados.
    Importa dinámicamente y envuelve las funciones declaradas.
    """
    import importlib
    global _contratos_map, _wrapped_functions, _modo, _runtime_enabled

    # Opt-in: si el runtime no fue habilitado, no hacemos nada.
    if not _runtime_enabled:
        yield
        return

    for module_name, funciones in _contratos_map.items():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            # Omitir fallas de módulos externos o no importables en este contexto
            continue

        for func_data in funciones:
            func_name = func_data["nombre"]
            contrato = func_data["contrato"]
            archivo = func_data["archivo"]
            linea = func_data["linea"]
            
            key = (module_name, func_name)
            if key in _wrapped_functions:
                continue

            original_func = getattr(module, func_name, None)
            if original_func is not None and callable(original_func):
                side_effects_permitidos = [s.descripcion.strip() for s in contrato.side_effects]

                def make_wrapper(f, s_effects, f_name, file_p, line_n):
                    @wraps(f)
                    def wrapper(*args, **kwargs):
                        with sentinela_db(s_effects, funcion=f_name, archivo=file_p, linea=line_n, modo=_modo), \
                             sentinela_disco(s_effects, funcion=f_name, archivo=file_p, linea=line_n, modo=_modo), \
                             sentinela_email(s_effects, funcion=f_name, archivo=file_p, linea=line_n, modo=_modo):
                            return f(*args, **kwargs)
                    return wrapper

                wrapped_func = make_wrapper(original_func, side_effects_permitidos, func_name, archivo, linea)
                setattr(module, func_name, wrapped_func)
                _wrapped_functions.add(key)

                # Buscar y actualizar copias importadas previamente (from module import func)
                for loaded_module_name, loaded_module in list(sys.modules.items()):
                    if loaded_module and loaded_module_name != module_name:
                        try:
                            if getattr(loaded_module, func_name, None) is original_func:
                                setattr(loaded_module, func_name, wrapped_func)
                        except Exception:
                            pass

    # Yield para que pytest no falle por falta de yield en fixture.
    # No hay cleanup que hacer — el wrapping es permanente para esta sesion.
    yield
