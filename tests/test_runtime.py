import pytest
from unittest.mock import MagicMock
import sys
import os

from docpact.runtime.exceptions import ContractViolationError
from docpact.runtime.sentinels import sentinela_db, sentinela_disco, sentinela_email

def test_contract_violation_error():
    err = ContractViolationError("mi_func", "archivo.py", 42, "db_write", "Intento de escritura")
    assert err.funcion == "mi_func"
    assert err.archivo == "archivo.py"
    assert err.linea == 42
    assert err.efecto_violado == "db_write"
    assert "mi_func" in str(err)
    assert "archivo.py:42" in str(err)


def test_sentinela_disco_bloquea_escritura():
    # Sin el sentinela o si está permitido, abre para escritura sin problemas
    # Pero con sentinela y sin permiso:
    with pytest.raises(ContractViolationError) as exc_info:
        with sentinela_disco(side_effects_permitidos=[]):
            with open("/tmp/archivo_prueba.txt", "w") as f:
                f.write("hola")
                
    assert exc_info.value.efecto_violado == "escribe_archivo"
    assert "archivo_prueba.txt" in exc_info.value.detalle

    # Si declaramos escribe_archivo en permitidos, no debe fallar
    path = "/tmp/test_sentinela_disco.txt"
    try:
        with sentinela_disco(side_effects_permitidos=["escribe_archivo"]):
            with open(path, "w") as f:
                f.write("permitido")
        assert os.path.exists(path)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_sentinela_email_bloquea_smtp():
    with pytest.raises(ContractViolationError) as exc_info:
        with sentinela_email(side_effects_permitidos=[]):
            import smtplib
            smtp = smtplib.SMTP()
            smtp.sendmail("remitente@test.com", "destinatario@test.com", "msg")
            
    assert exc_info.value.efecto_violado == "email"
    assert "destinatario@test.com" in exc_info.value.detalle


def test_sentinela_db_simulado():
    # Mockear django para probar la intercepción de queries sin Django real instalado en docpact
    connection_mock = MagicMock()
    connection_mock.execute_wrapper = MagicMock()
    
    django_db_mock = MagicMock()
    django_db_mock.connection = connection_mock
    sys.modules['django'] = MagicMock()
    sys.modules['django.db'] = django_db_mock
    sys.modules['django.conf'] = MagicMock()
    sys.modules['django.conf'].settings = MagicMock(configured=True)

    try:
        with sentinela_db(side_effects_permitidos=[]):
            pass
            
        assert connection_mock.execute_wrapper.called
        wrapper = connection_mock.execute_wrapper.call_args[0][0]
        
        # Permitir SELECT
        execute_mock = MagicMock()
        wrapper(execute_mock, "SELECT * FROM soporte_ticket", [], False, {})
        assert execute_mock.called

        # Bloquear INSERT
        execute_mock.reset_mock()
        with pytest.raises(ContractViolationError):
            wrapper(execute_mock, "INSERT INTO soporte_ticket VALUES (1)", [], False, {})
            
        # Permitir INSERT si db_write está en los permitidos
        with sentinela_db(side_effects_permitidos=["db_write"]):
            pass
        wrapper_allow = connection_mock.execute_wrapper.call_args[0][0]
        wrapper_allow(execute_mock, "INSERT INTO soporte_ticket VALUES (1)", [], False, {})
        assert execute_mock.called
        
    finally:
        sys.modules.pop('django', None)
        sys.modules.pop('django.db', None)
        sys.modules.pop('django.conf', None)


def test_sentinelas_modo_warning(tmp_path):
    import warnings
    
    # 1. Disco en modo warning
    test_file = tmp_path / "test_warning_disco.txt"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with sentinela_disco(side_effects_permitidos=[], modo="warning"):
            with open(test_file, "w") as f:
                f.write("test warning")
        
        assert len(w) >= 1
        assert any("ADVERTENCIA DE VIOLACIÓN DE CONTRATO" in str(warn.message) for warn in w)
        assert any("escribe_archivo" in str(warn.message) for warn in w)

    # 2. Email en modo warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with sentinela_email(side_effects_permitidos=[], modo="warning"):
            import smtplib
            smtp = smtplib.SMTP()
            try:
                smtp.sendmail("remitente@test.com", "destinatario@test.com", "msg")
            except Exception:
                pass
        
        assert len(w) >= 1
        assert any("ADVERTENCIA DE VIOLACIÓN DE CONTRATO" in str(warn.message) for warn in w)
        assert any("email" in str(warn.message) for warn in w)

