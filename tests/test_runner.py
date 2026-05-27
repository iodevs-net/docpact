"""Tests del runner/sandbox de docpact."""

from docpact.runner import sha256_of_dir


def test_sha256_of_dir_con_tmp_path(tmp_path):
    """sha256_of_dir debe retornar hash de 64 caracteres."""
    (tmp_path / "test.py").write_text("x = 1")
    h = sha256_of_dir(tmp_path)
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_sha256_deterministico(tmp_path):
    """Mismo contenido debe producir mismo hash."""
    (tmp_path / "a.py").write_text("x = 1")
    h1 = sha256_of_dir(tmp_path)
    h2 = sha256_of_dir(tmp_path)
    assert h1 == h2


def test_sha256_cambia_con_contenido(tmp_path):
    """Hash debe cambiar si el contenido cambia."""
    (tmp_path / "f.py").write_text("x = 1")
    h1 = sha256_of_dir(tmp_path)
    (tmp_path / "f.py").write_text("x = 2")
    h2 = sha256_of_dir(tmp_path)
    assert h1 != h2


def test_sha256_rechaza_archivo(tmp_path):
    """sha256_of_dir con archivo debe lanzar NotADirectoryError."""
    f = tmp_path / "no_dir"
    f.write_text("contenido")
    import pytest
    with pytest.raises(NotADirectoryError):
        sha256_of_dir(f)


def test_sha256_rechaza_sin_existir(tmp_path):
    """sha256_of_dir con ruta inexistente debe lanzar NotADirectoryError."""
    import pytest
    with pytest.raises(NotADirectoryError):
        sha256_of_dir(tmp_path / "no_existe")


def test_run_sandbox_existe():
    """run_sandbox debe ser una función importable."""
    from docpact.runner import run_sandbox
    assert callable(run_sandbox)


def test_trap_loop_existe():
    """trap_loop debe ser una función importable."""
    from docpact.runner import trap_loop
    assert callable(trap_loop)


def test_build_sandbox_existe():
    """build_sandbox debe ser una función importable."""
    from docpact.runner import build_sandbox
    assert callable(build_sandbox)
