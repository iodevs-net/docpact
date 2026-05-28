"""docpact run — Verificación dinámica en sandbox Docker.

Ejecuta código en un contenedor aislado (docpact-sandbox:latest)
y realiza un loop iterativo de prueba/feedback/arreglo hasta que
las pruebas pasen o se alcance el máximo de iteraciones.

Uso:
    docpact run <codigo.py> --tests <tests/> --max-iterations 5 --build
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SANDBOX_IMAGE = "docpact-sandbox:latest"
WORKDIR = "/workspace"


# ──────────────────────────────────────────────
# sha256_of_dir
# ──────────────────────────────────────────────


def sha256_of_dir(directory: str | Path) -> str:
    """Calcula un hash SHA256 determinístico del contenido de un directorio.

    Recorre todos los archivos (no excluye __pycache__ ni .git), ordenados
    por ruta relativa, y produce un hash combinado de sus contenidos.
    Útil para detectar cambios externos entre iteraciones del trap loop.

    Args:
        directory: Ruta al directorio.

    Returns:
        Hash hexadecimal SHA256 de 64 caracteres.
    """
    hasher = hashlib.sha256()
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"{directory} no es un directorio")

    archivos: list[Path] = []
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            archivos.append(entry)

    for path in archivos:
        rel = path.relative_to(root)
        hasher.update(str(rel).encode("utf-8"))
        try:
            hasher.update(path.read_bytes())
        except (OSError, PermissionError):
            hasher.update(b"\x00")

    return hasher.hexdigest()


# ──────────────────────────────────────────────
# build_sandbox
# ──────────────────────────────────────────────


def build_sandbox(
    dockerfile: str | Path = "Dockerfile",
    tag: str = SANDBOX_IMAGE,
    *,
    _run: object = subprocess.run,
) -> int:
    """Construye la imagen Docker del sandbox.

    Busca el Dockerfile en ``dockerfile`` (por defecto ``Dockerfile``
    en el CWD).  Si el archivo no existe, busca ``Dockerfile.sandbox``,
    y como último recurso usa un Dockerfile inline mínimo.

    Args:
        dockerfile: Ruta al Dockerfile.
        tag: Tag de la imagen a construir.
        _run: Callable para tests (inyección de dependencia).

    Returns:
        Código de retorno de ``docker build``.
    """
    df_path = Path(dockerfile)
    if not df_path.is_file():
        alt = Path("Dockerfile.sandbox")
        if alt.is_file():
            df_path = alt
        else:
            df_path = _write_inline_dockerfile()

    result = _run(
        ["docker", "build", "-t", tag, "-f", str(df_path), "."],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] docker build falló:\n{result.stderr}", file=sys.stderr)
    return result.returncode


def _write_inline_dockerfile() -> Path:
    """Escribe un Dockerfile mínimo para el sandbox."""
    content = (
        "FROM python:3.12-slim\n"
        "WORKDIR /workspace\n"
        "RUN pip install --no-cache-dir pytest\n"
        "COPY . /workspace\n"
    )
    df = Path(tempfile.gettempdir()) / "docpact_Dockerfile"
    df.write_text(content)
    return df


# ──────────────────────────────────────────────
# run_sandbox
# ──────────────────────────────────────────────


def run_sandbox(
    code: str | Path,
    tests_dir: str | Path,
    *,
    tag: str = SANDBOX_IMAGE,
    timeout: int = 120,
    env: dict[str, str] | None = None,
    _run: object = subprocess.run,
) -> subprocess.CompletedProcess:
    """Ejecuta el código dentro del sandbox Docker contra los tests.

    1. Monta el directorio de tests en ``WORKDIR/tests``.
    2. Copia ``code`` a ``WORKDIR/code.py``.
    3. Corre ``python -m pytest tests/ -v --tb=short`` dentro del contenedor.

    Args:
        code: Ruta al archivo .py a probar.
        tests_dir: Directorio con los tests (pytest).
        tag: Tag de la imagen Docker.
        timeout: Timeout en segundos para ``docker run``.
        env: Variables de entorno adicionales para el contenedor.
        _run: Callable para tests (inyección de dependencia).

    Returns:
        ``subprocess.CompletedProcess`` con stdout/stderr del contenedor.
    """
    code_path = Path(code).resolve()
    tests_path = Path(tests_dir).resolve()

    if not code_path.is_file():
        raise FileNotFoundError(f"Código no encontrado: {code}")
    if not tests_path.is_dir():
        raise NotADirectoryError(f"Directorio de tests no encontrado: {tests_dir}")

    mount_test = f"{tests_path}:{WORKDIR}/tests:ro"
    mount_code = f"{code_path}:{WORKDIR}/code.py:ro"

    cmd: list[str] = [
        "docker",
        "run",
        "--rm",
        "--cap-drop=ALL",
        "--network=none",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:size=64M",
        "--user",
        "1001:1001",
        "--memory",
        "256m",
        "--cpus",
        "0.5",
        "-v",
        mount_test,
        "-v",
        mount_code,
    ]

    if env:
        for k, v in env.items():
            cmd.extend(["-e", f"{k}={v}"])

    cmd.extend([tag, "python", "-m", "pytest", "tests/", "-v", "--tb=short"])

    hash_before = sha256_of_dir(tests_path)

    result = _run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    hash_after = sha256_of_dir(tests_path)
    if hash_before != hash_after:
        result.tamper_detected = True

    result.stderr = "\n".join(
        line
        for line in (result.stderr or "").splitlines()
        if "/workspace/tests" not in line
    )
    return result


# ──────────────────────────────────────────────
# trap_loop
# ──────────────────────────────────────────────


def trap_loop(
    code: str | Path,
    tests_dir: str | Path,
    max_iterations: int = 10,
    *,
    build: bool = False,
    tag: str = SANDBOX_IMAGE,
    delay: float = 0.5,
    _run: object = subprocess.run,
) -> dict:
    """Loop iterative que ejecuta código en sandbox hasta que pase los tests.

    En cada iteración:
      1. Calcula sha256 del directorio de tests para detectar cambios externos.
      2. Corre ``run_sandbox``.
      3. Si los tests pasan → éxito, termina.
      4. Si fallan → captura el error, lo muestra, y continúa.

    Args:
        code: Ruta al archivo .py a probar.
        tests_dir: Directorio con los tests.
        max_iterations: Máximo de iteraciones antes de rendirse.
        build: Si True, rebuild la imagen antes del loop.
        tag: Tag de la imagen Docker.
        delay: Pausa en segundos entre iteraciones.
        _run: Callable para tests (inyección de dependencia).

    Returns:
        Dict con:
          - "success": bool
          - "iterations": int
          - "final_output": str (stdout + stderr de la última ejecución)
          - "exit_code": int
    """
    code_path = Path(code)
    tests_path = Path(tests_dir)

    if build:
        print("[trap] Construyendo imagen sandbox...")
        rc = build_sandbox(tag=tag, _run=_run)
        if rc != 0:
            return {
                "success": False,
                "iterations": 0,
                "final_output": "docker build falló",
                "exit_code": rc,
            }

    if not tests_path.is_dir():
        return {
            "success": False,
            "iterations": 0,
            "final_output": f"Directorio de tests no encontrado: {tests_dir}",
            "exit_code": 1,
        }

    hash_anterior = sha256_of_dir(tests_path)

    for i in range(1, max_iterations + 1):
        print(f"[trap] Iteración {i}/{max_iterations}")
        time.sleep(delay)

        hash_actual = sha256_of_dir(tests_path)
        if hash_actual != hash_anterior:
            print("[trap]  Directorio de tests cambió externamente, re-evaluando...")
            hash_anterior = hash_actual

        result = run_sandbox(code_path, tests_path, tag=tag, _run=_run)

        if result.returncode == 0:
            print("[trap] ✓ Todos los tests pasaron")
            return {
                "success": True,
                "iterations": i,
                "final_output": result.stdout,
                "exit_code": 0,
            }

        print(f"[trap]  Tests fallaron (exit={result.returncode})")
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        if result.stderr:
            print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)

    print(f"[trap] ✗ Límite de {max_iterations} iteraciones alcanzado sin éxito")
    return {
        "success": False,
        "iterations": max_iterations,
        "final_output": result.stdout + "\n" + result.stderr,
        "exit_code": result.returncode,
    }


# ──────────────────────────────────────────────
# main — argparse
# ──────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada para ``docpact run``.

    Uso::

        docpact run <codigo> --tests <dir> --max-iterations N --build

    Args:
        argv: Argumentos de línea de comandos (None → usa sys.argv).

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    parser = argparse.ArgumentParser(
        prog="docpact run",
        description="Verificación dinámica en sandbox Docker",
    )
    parser.add_argument(
        "code",
        type=str,
        help="Ruta al archivo .py a probar",
    )
    parser.add_argument(
        "--tests",
        type=str,
        default="tests/",
        help="Directorio con tests pytest (default: tests/)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Máximo de iteraciones del trap loop (default: 10)",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Rebuild la imagen Docker antes de ejecutar",
    )

    args = parser.parse_args(argv)

    try:
        resultado = trap_loop(
            code=args.code,
            tests_dir=args.tests,
            max_iterations=args.max_iterations,
            build=args.build,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except NotADirectoryError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("[ERROR] Timeout ejecutando sandbox", file=sys.stderr)
        return 1

    if resultado["success"]:
        print(resultado["final_output"])
        return 0

    print(resultado["final_output"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
