import warnings
from contextlib import contextmanager
from docpact.runtime.exceptions import ContractViolationError

@contextmanager
def sentinela_db(side_effects_permitidos: list[str], funcion: str = "desconocida", archivo: str = "", linea: int = 0, modo: str = "strict"):
    """Context manager para interceptar escrituras accidentales en la base de datos (Django)."""
    # Si Django no está disponible, no hacemos nada
    try:
        from django.db import connection
    except ImportError:
        yield
        return

    # Si la configuración de Django no está cargada, no hacemos nada
    try:
        from django.conf import settings
        if not settings.configured:
            yield
            return
    except Exception:
        yield
        return

    def execute_wrapper(execute, sql, params, many, context):
        sql_upper = sql.strip().upper()
        # Detección de operaciones de escritura DML/DDL
        is_write = any(sql_upper.startswith(cmd) for cmd in ('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'ALTER', 'CREATE', 'DROP'))
        # side_effects_permitidos puede tener la forma 'db_write' o
        # 'db_write (descripción parentizada)'. Extraer el prefijo
        # (parte antes de '(') para que el match sea por nombre canónico
        # y no por descripción completa.
        efectos_canonicos = {s.split("(", 1)[0].strip() for s in side_effects_permitidos}
        if is_write and "db_write" not in efectos_canonicos:
            # Omitir consultas a tablas internas del sistema para evitar falsos positivos
            tablas_internas = ('DJANGO_SESSION', 'AUTH_PERMISSION', 'DJANGO_CONTENT_TYPE', 'DJANGO_MIGRATIONS')
            if not any(t in sql_upper for t in tablas_internas):
                detalle = f"Se intentó ejecutar la consulta de escritura: {sql.strip()}"
                if modo == "warning":
                    mensaje = (
                        f"\n⚠️ ADVERTENCIA DE VIOLACIÓN DE CONTRATO DOCPACT (db_write)\n"
                        f"   Función: {funcion}\n"
                        f"   Archivo: {archivo}:{linea}\n"
                        f"   Detalle: {detalle}\n"
                    )
                    warnings.warn(mensaje, UserWarning, stacklevel=2)
                else:
                    raise ContractViolationError(
                        funcion=funcion,
                        archivo=archivo,
                        linea=linea,
                        efecto_violado="db_write",
                        detalle=detalle
                    )
        return execute(sql, params, many, context)

    with connection.execute_wrapper(execute_wrapper):
        yield


@contextmanager
def sentinela_disco(side_effects_permitidos: list[str], funcion: str = "desconocida", archivo: str = "", linea: int = 0, modo: str = "strict"):
    """Context manager para interceptar escrituras accidentales en el sistema de archivos (builtins.open)."""
    if "escribe_archivo" in side_effects_permitidos:
        yield
        return

    import builtins
    original_open = builtins.open

    efectos_canonicos = {s.split("(", 1)[0].strip() for s in side_effects_permitidos}

    def mocked_open(file, mode='r', *args, **kwargs):
        # Si se abre el archivo en modo escritura, append o creación
        if any(m in mode for m in ('w', 'a', 'x')):
            file_str = str(file)
            # Omitir archivos internos de cache o pruebas para no interrumpir el runner
            if not (".pytest_cache" in file_str or file_str.endswith(".pyc") or "test_db.sqlite3" in file_str):
                detalle = f"Se intentó abrir el archivo '{file}' para escritura con modo '{mode}'."
                if "escribe_archivo" not in efectos_canonicos:
                    if modo == "warning":
                        mensaje = (
                            f"\n⚠️ ADVERTENCIA DE VIOLACIÓN DE CONTRATO DOCPACT (escribe_archivo)\n"
                            f"   Función: {funcion}\n"
                            f"   Archivo: {archivo}:{linea}\n"
                            f"   Detalle: {detalle}\n"
                        )
                        warnings.warn(mensaje, UserWarning, stacklevel=2)
                    else:
                        raise ContractViolationError(
                            funcion=funcion,
                            archivo=archivo,
                            linea=linea,
                            efecto_violado="escribe_archivo",
                            detalle=detalle
                        )
        return original_open(file, mode, *args, **kwargs)

    import unittest.mock
    with unittest.mock.patch("builtins.open", new=mocked_open):
        yield


@contextmanager
def sentinela_email(side_effects_permitidos: list[str], funcion: str = "desconocida", archivo: str = "", linea: int = 0, modo: str = "strict"):
    """Context manager para interceptar envíos de correo no declarados (SMTP y Django Outbox)."""
    # Match por prefijo (parte antes de '(') para tolerar descripciones
    # parentizadas como 'email (envía notificación de resolución)'.
    efectos_canonicos = {s.split("(", 1)[0].strip() for s in side_effects_permitidos}
    if "email" in efectos_canonicos:
        yield
        return

    import smtplib
    original_sendmail = smtplib.SMTP.sendmail

    def mocked_sendmail(self, from_addr, to_addrs, msg, mail_options=(), rcpt_options=()):
        detalle = f"Se intentó enviar un correo electrónico vía smtplib a: {to_addrs}"
        if modo == "warning":
            mensaje = (
                f"\n⚠️ ADVERTENCIA DE VIOLACIÓN DE CONTRATO DOCPACT (email)\n"
                f"   Función: {funcion}\n"
                f"   Archivo: {archivo}:{linea}\n"
                f"   Detalle: {detalle}\n"
            )
            warnings.warn(mensaje, UserWarning, stacklevel=2)
        else:
            raise ContractViolationError(
                funcion=funcion,
                archivo=archivo,
                linea=linea,
                efecto_violado="email",
                detalle=detalle
            )

    import unittest.mock
    
    django_mail_available = False
    initial_outbox_len = 0
    try:
        from django.core import mail
        django_mail_available = True
        initial_outbox_len = len(getattr(mail, "outbox", []))
    except ImportError:
        pass

    with unittest.mock.patch("smtplib.SMTP.sendmail", new=mocked_sendmail):
        yield
        if django_mail_available:
            current_outbox = getattr(mail, "outbox", [])
            if len(current_outbox) > initial_outbox_len:
                violadores = current_outbox[initial_outbox_len:]
                del current_outbox[initial_outbox_len:]
                detalle = f"Se detectó el envío de {len(violadores)} correo(s) a través de Django Mail."
                if modo == "warning":
                    mensaje = (
                        f"\n⚠️ ADVERTENCIA DE VIOLACIÓN DE CONTRATO DOCPACT (email)\n"
                        f"   Función: {funcion}\n"
                        f"   Archivo: {archivo}:{linea}\n"
                        f"   Detalle: {detalle}\n"
                    )
                    warnings.warn(mensaje, UserWarning, stacklevel=2)
                else:
                    raise ContractViolationError(
                        funcion=funcion,
                        archivo=archivo,
                        linea=linea,
                        efecto_violado="email",
                        detalle=detalle
                    )
