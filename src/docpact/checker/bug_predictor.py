"""Predictor de bugs basado en AST.

Detecta patrones comunes de bugs en Python usando análisis de AST.
Inspirado en pylint, flake8, y SonarQube pero lightweight.

Patrones detectados:
- Mutable default arguments
- Bare/broad except
- open() sin context manager
- Variables sin usar
- Redefinición de argumentos
- SQL injection (f-strings/%-formatting en execute())
- Path traversal (f-string/concatenación en open/os.path.join/Path)
- Hardcoded secrets (password/secret/token/key como string literal)
- Unsafe deserialization (yaml.load sin Loader seguro)
- Late binding closures en loops
- Global mutation
- Blocking calls en async
- Unawaited coroutines
- eval/exec
- pickle.load inseguro
- subprocess shell=True
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import re


# ── Security patterns ──
_SQL_KEYWORDS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "EXEC", "EXECUTE", "UNION"})
_SECRET_RE = re.compile(r"(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|auth[_-]?token|session[_-]?key)", re.IGNORECASE)
_SAFE_YAML_LOADERS = {"SafeLoader", "FullLoader", "CSafeLoader", "CLoader"}


@dataclass
class BugPredicho:
    """Un bug potencial detectado por análisis estático."""

    tipo: str
    severidad: str  # error, warning, info
    mensaje: str
    sugerencia: str
    archivo: str
    linea: int
    funcion: str
    metrica: str | None = None
    valor: float | None = None

# ── Checkers individuales ──


def _check_mutable_defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta argumentos mutables como defaults (def f(x=[]))."""
    bugs = []
    for default in node.args.defaults:
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            bugs.append(BugPredicho(
                tipo="mutable_default",
                severidad="warning",
                mensaje=f"Argumento default mutable en '{node.name}'",
                sugerencia="Usar None como default y crear la mutable dentro de la función",
                archivo="",
                linea=node.lineno,
                funcion=node.name,
            ))
    for default in node.args.kw_defaults:
        if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
            bugs.append(BugPredicho(
                tipo="mutable_default",
                severidad="warning",
                mensaje=f"Keyword argument default mutable en '{node.name}'",
                sugerencia="Usar None como default y crear la mutable dentro de la función",
                archivo="",
                linea=node.lineno,
                funcion=node.name,
            ))
    return bugs


def _check_bare_except(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta except sin tipo específico (except: pass)."""
    bugs = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Try):
            continue
        for handler in child.handlers:
            if handler.type is None:
                bugs.append(BugPredicho(
                    tipo="bare_except",
                    severidad="warning",
                    mensaje="Except sin tipo captura SystemExit y KeyboardInterrupt",
                    sugerencia="Usar 'except Exception:' o un tipo específico",
                    archivo="",
                    linea=handler.lineno,
                    funcion=node.name,
                ))
            elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                # Verificar si tiene re-raise
                has_reraise = any(
                    isinstance(n, ast.Raise) and n.exc is None
                    for n in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
                )
                if not has_reraise:
                    bugs.append(BugPredicho(
                        tipo="broad_except",
                        severidad="info",
                        mensaje="Captura 'Exception' demasiado general",
                        sugerencia="Capturar un tipo más específico de excepción",
                        archivo="",
                        linea=handler.lineno,
                        funcion=node.name,
                    ))
    return bugs


def _check_resource_leaks(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta open() sin context manager (with statement)."""
    bugs = []

    class LeakVisitor(ast.NodeVisitor):
        def __init__(self):
            self.in_with_depth = 0

        def visit_With(self, w: ast.With) -> None:
            self.in_with_depth += 1
            self.generic_visit(w)
            self.in_with_depth -= 1

        def visit_Call(self, c: ast.Call) -> None:
            if self.in_with_depth == 0 and _is_open_call(c):
                bugs.append(BugPredicho(
                    tipo="resource_leak",
                    severidad="warning",
                    mensaje="open() sin context manager — risk de resource leak",
                    sugerencia="Usar: with open(...) as f:",
                    archivo="",
                    linea=c.lineno,
                    funcion=node.name,
                ))
            self.generic_visit(c)

    LeakVisitor().visit(node)
    return bugs


def _check_unused_variables(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta variables asignadas pero nunca usadas."""
    defined: dict[str, ast.Name] = {}
    used: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                used.add(child.id)
            elif isinstance(child.ctx, ast.Store):
                if child.id not in defined:
                    defined[child.id] = child

    bugs = []
    for name, name_node in defined.items():
        if name not in used and not name.startswith("_"):
            bugs.append(BugPredicho(
                tipo="unused_variable",
                severidad="info",
                mensaje=f"Variable '{name}' asignada pero nunca usada",
                sugerencia=f"Eliminar '{name}' o prefijar con _ si es intencional",
                archivo="",
                linea=name_node.lineno,
                funcion=node.name,
            ))
    return bugs


def _check_redefined_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta argumentos redefinidos en loops."""
    arg_names = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
    bugs = []

    for child in ast.walk(node):
        if isinstance(child, ast.For) and isinstance(child.target, ast.Name):
            if child.target.id in arg_names:
                bugs.append(BugPredicho(
                    tipo="redefined_arg",
                    severidad="warning",
                    mensaje=f"Argumento '{child.target.id}' redefinido en loop",
                    sugerencia=f"Usar un nombre diferente para la variable del loop",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
    return bugs

def _check_late_binding_closure(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta lambdas/funciones anidadas dentro de loops que referencian la variable del loop."""
    bugs: list[BugPredicho] = []

    for child in ast.walk(node):
        # Solo For tiene target; While no tiene variable de loop explícita
        if isinstance(child, ast.For):
            loop_vars: set[str] = set()
            if isinstance(child.target, ast.Name):
                loop_vars.add(child.target.id)
            elif isinstance(child.target, (ast.Tuple, ast.List)):
                for elt in child.target.elts:
                    if isinstance(elt, ast.Name):
                        loop_vars.add(elt.id)
        else:
            continue
        if not loop_vars:
            continue
        # Buscar lambdas y funciones anidadas en el cuerpo del loop
        for sub in ast.walk(child):
            if isinstance(sub, ast.Lambda):
                # Recolectar nombres usados en el lambda
                used = {
                    n.id for n in ast.walk(sub)
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                }
                captured = loop_vars & used
                if captured:
                    bugs.append(BugPredicho(
                        tipo="late_binding_closure",
                        severidad="warning",
                        mensaje=f"Lambda en loop captura variable '{captured.pop()}' — late binding",
                        sugerencia="Usar argumento default: lambda x=x: x para capturar el valor actual",
                        archivo="",
                        linea=sub.lineno,
                        funcion=node.name,
                    ))
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
                used = {
                    n.id for n in ast.walk(sub)
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                }
                captured = loop_vars & used
                if captured:
                    bugs.append(BugPredicho(
                        tipo="late_binding_closure",
                        severidad="warning",
                        mensaje=f"Función anidada en loop captura variable '{captured.pop()}' — late binding",
                        sugerencia="Pasar la variable como argumento o usar default: def f(x=x)",
                        archivo="",
                        linea=sub.lineno,
                        funcion=node.name,
                    ))
    return bugs


def _check_global_mutation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta uso de 'global' dentro de funciones."""
    bugs: list[BugPredicho] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Global):
            for name in child.names:
                bugs.append(BugPredicho(
                    tipo="global_mutation",
                    severidad="warning",
                    mensaje=f"Uso de 'global {name}' — mutación de estado compartido",
                    sugerencia="Retornar el valor o usar una clase/objeto para encapsular estado",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
    return bugs


_BLOCKING_CALLS = frozenset({
    "time.sleep", "os.system", "os.popen",
    "requests.get", "requests.post", "requests.put",
    "requests.delete", "requests.patch", "requests.head",
    "requests.request",
})


def _check_blocking_in_async(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta llamadas bloqueantes dentro de funciones async."""
    if not isinstance(node, ast.AsyncFunctionDef):
        return []

    bugs: list[BugPredicho] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        # time.sleep(...) / os.system(...) etc.
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            call_key = f"{func.value.id}.{func.attr}"
            if call_key in _BLOCKING_CALLS:
                bugs.append(BugPredicho(
                    tipo="blocking_in_async",
                    severidad="warning",
                    mensaje=f"Llamada bloqueante '{call_key}()' en función async '{node.name}'",
                    sugerencia="Usar asyncio.sleep() o envolver en asyncio.to_thread()",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
        # open(...) directo
        if _is_open_call(child):
            # Verificar que NO esté dentro de asyncio.to_thread
            # Buscamos ancestros para ver si hay to_thread envolviendo
            # Como ast.walk no da ancestros, buscamos en el padre
            bugs.append(BugPredicho(
                tipo="blocking_in_async",
                severidad="warning",
                mensaje=f"open() bloqueante en función async '{node.name}'",
                sugerencia="Usar aiofiles.open() o envolver en asyncio.to_thread()",
                archivo="",
                linea=child.lineno,
                funcion=node.name,
            ))
    return bugs


_ASYNC_KNOWN = frozenset({
    "asyncio.sleep", "asyncio.gather", "asyncio.wait",
    "asyncio.create_task", "asyncio.wait_for",
})


def _check_unawaited_coroutine(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta llamadas a funciones async conocidas sin await."""
    if not isinstance(node, ast.AsyncFunctionDef):
        return []

    bugs: list[BugPredicho] = []

    class UnawaitedVisitor(ast.NodeVisitor):
        def __init__(self):
            self.in_await = False

        def visit_Await(self, a: ast.Await) -> None:
            self.in_await = True
            self.generic_visit(a)
            self.in_await = False

        def visit_Call(self, c: ast.Call) -> None:
            if self.in_await:
                self.generic_visit(c)
                return
            func = c.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                call_key = f"{func.value.id}.{func.attr}"
                if call_key in _ASYNC_KNOWN:
                    bugs.append(BugPredicho(
                        tipo="unawaited_coroutine",
                        severidad="error",
                        mensaje=f"Coroutine '{call_key}()' no se espera con await",
                        sugerencia="Agregar 'await' antes de la llamada",
                        archivo="",
                        linea=c.lineno,
                        funcion=node.name,
                    ))
            self.generic_visit(c)

    UnawaitedVisitor().visit(node)
    return bugs


def _check_eval_exec(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta llamadas a eval() o exec()."""
    bugs: list[BugPredicho] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
            bugs.append(BugPredicho(
                tipo="eval_exec",
                severidad="error",
                mensaje=f"Uso de {func.id}() — riesgo de inyección de código",
                sugerencia=f"Evitar {func.id}(); usar alternativas seguras como ast.literal_eval() o importlib",
                archivo="",
                linea=child.lineno,
                funcion=node.name,
            ))
    return bugs


def _check_pickle_load(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta pickle.load/pickle.loads — riesgo de deserialización insegura."""
    bugs: list[BugPredicho] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr in ("load", "loads"):
            # pickle.load(f) o pickle.loads(data)
            if isinstance(func.value, ast.Name) and func.value.id == "pickle":
                bugs.append(BugPredicho(
                    tipo="pickle_load",
                    severidad="error",
                    mensaje=f"pickle.{func.attr}() ejecuta código arbitrario — riesgo de seguridad",
                    sugerencia="Usar formato seguro como json o validar datos antes de deserializar",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
    return bugs


def _check_shell_true(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta subprocess.* con shell=True — riesgo de inyección de comandos."""
    bugs: list[BugPredicho] = []
    subprocess_funcs = {"run", "call", "check_call", "check_output", "Popen"}

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        is_subprocess = False
        if isinstance(func, ast.Attribute) and func.attr in subprocess_funcs:
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                is_subprocess = True
        if not is_subprocess:
            continue
        # Buscar keyword shell=True
        for kw in child.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                bugs.append(BugPredicho(
                    tipo="shell_injection",
                    severidad="error",
                    mensaje=f"subprocess.{func.attr}(shell=True) — riesgo de inyección de comandos",
                    sugerencia="Pasar lista de argumentos en lugar de string, y shell=False",
                    archivo="",
                    linea=child.lineno,
                    funcion=node.name,
                ))
    return bugs
# ── Complexity metrics (SonarSource cognitive complexity) ──

_NESTING_TYPES = (ast.If, ast.For, ast.While, ast.Try, ast.With)


def _calcular_cognitive_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Calculate SonarSource cognitive complexity with nesting penalty.

    Each if/for/while/elif: +1.
    Each nesting level inside if/for/while/try/with adds +1 penalty.
    elif is handled at same nesting as its parent if (no extra penalty).
    """
    complexity = 0

    def _walk(n: ast.AST, nesting: int) -> None:
        nonlocal complexity
        if isinstance(n, ast.If):
            complexity += 1 + nesting
            for stmt in n.body:
                _walk(stmt, nesting + 1)
            # elif chain: same nesting as parent if
            if len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If):
                _walk(n.orelse[0], nesting)
            else:
                for stmt in n.orelse:
                    _walk(stmt, nesting + 1)
        elif isinstance(n, ast.For):
            complexity += 1 + nesting
            for stmt in n.body:
                _walk(stmt, nesting + 1)
            for stmt in n.orelse:
                _walk(stmt, nesting + 1)
        elif isinstance(n, ast.While):
            complexity += 1 + nesting
            for stmt in n.body:
                _walk(stmt, nesting + 1)
            for stmt in n.orelse:
                _walk(stmt, nesting + 1)
        elif isinstance(n, ast.Try):
            for stmt in n.body:
                _walk(stmt, nesting + 1)
            for handler in n.handlers:
                for stmt in handler.body:
                    _walk(stmt, nesting + 1)
            for stmt in n.orelse:
                _walk(stmt, nesting + 1)
            for stmt in n.finalbody:
                _walk(stmt, nesting + 1)
        elif isinstance(n, ast.With):
            for stmt in n.body:
                _walk(stmt, nesting + 1)
        else:
            for child in ast.iter_child_nodes(n):
                _walk(child, nesting)

    for stmt in node.body:
        _walk(stmt, 0)
    return complexity


def _calcular_method_length(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count total lines of code in function (including def line)."""
    if node.end_lineno is not None:
        return node.end_lineno - node.lineno + 1
    # Fallback: count body nodes
    if not node.body:
        return 1
    last = max(getattr(n, "end_lineno", n.lineno) for n in node.body)
    return last - node.lineno + 1


def _max_nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """Calculate maximum nesting depth for if/for/while/try/with."""
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTING_TYPES):
            child_d = _max_nesting_depth(child, depth + 1)
            if child_d > max_d:
                max_d = child_d
        else:
            child_d = _max_nesting_depth(child, depth)
            if child_d > max_d:
                max_d = child_d
    return max_d


def _check_high_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Flag functions with cognitive complexity > 15."""
    cc = _calcular_cognitive_complexity(node)
    if cc <= 15:
        return []
    return [BugPredicho(
        tipo="high_complexity",
        severidad="warning",
        mensaje=f"Complejidad cognitiva {cc} en '{node.name}' (umbral: 15)",
        sugerencia="Simplificar la lógica: extraer funciones auxiliares, reducir nesting",
        archivo="",
        linea=node.lineno,
        funcion=node.name,
        metrica="cognitive_complexity",
        valor=float(cc),
    )]


def _check_long_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Flag functions > 30 LOC."""
    length = _calcular_method_length(node)
    if length <= 30:
        return []
    return [BugPredicho(
        tipo="long_method",
        severidad="warning",
        mensaje=f"Función '{node.name}' tiene {length} líneas (umbral: 30)",
        sugerencia="Dividir en funciones más pequeñas con responsabilidad única",
        archivo="",
        linea=node.lineno,
        funcion=node.name,
        metrica="loc",
        valor=float(length),
    )]


def _check_deep_nesting(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Flag nesting depth > 3."""
    depth = _max_nesting_depth(node)
    if depth <= 3:
        return []
    return [BugPredicho(
        tipo="deep_nesting",
        severidad="warning",
        mensaje=f"Nesting depth {depth} en '{node.name}' (umbral: 3)",
        sugerencia="Extraer bloques anidados a funciones auxiliares o usar early returns",
        archivo="",
        linea=node.lineno,
        funcion=node.name,
        metrica="nesting_depth",
        valor=float(depth),
    )]



# ── Security checkers ──


def _check_sql_injection(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta SQL keywords en f-strings o %-formatting pasados a cursor.execute()."""
    bugs: list[BugPredicho] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            func = call.func
            # Match *.execute(...)
            if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
                self.generic_visit(call)
                return
            if not call.args:
                self.generic_visit(call)
                return
            arg0 = call.args[0]
            # f-string (JoinedStr)
            if isinstance(arg0, ast.JoinedStr):
                if _fstring_has_sql_keyword(arg0):
                    bugs.append(BugPredicho(
                        tipo="sql_injection",
                        severidad="critical",
                        mensaje="SQL injection: f-string con keyword SQL en execute()",
                        sugerencia="Usar parámetros nomposados: cursor.execute(\"SELECT ... WHERE x=%s\", [value])",
                        archivo="",
                        linea=call.lineno,
                        funcion=node.name,
                    ))
            # %-formatting: "..." % (...)
            elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Mod):
                text = _extract_string_literal(arg0.left)
                if text and any(kw in text.upper() for kw in _SQL_KEYWORDS):
                    bugs.append(BugPredicho(
                        tipo="sql_injection",
                        severidad="critical",
                        mensaje="SQL injection: %-formatting con keyword SQL en execute()",
                        sugerencia="Usar parámetros nomposados: cursor.execute(\"... WHERE x=%s\", [value])",
                        archivo="",
                        linea=call.lineno,
                        funcion=node.name,
                    ))
            self.generic_visit(call)

    _Visitor().visit(node)
    return bugs


def _fstring_has_sql_keyword(node: ast.JoinedStr) -> bool:
    """Verifica si un f-string contiene literales con keywords SQL."""
    for val in node.values:
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            if any(kw in val.value.upper() for kw in _SQL_KEYWORDS):
                return True
    return False


def _extract_string_literal(node: ast.expr) -> str | None:
    """Extrae el string de un Constant o JoinedStr (solo partes literales)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
        return " ".join(parts) if parts else None
    return None


def _check_path_traversal(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta open()/os.path.join()/Path() con f-string o concatenación."""
    bugs: list[BugPredicho] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            func = call.func
            is_target = False
            # open(...) / Path(...)
            if isinstance(func, ast.Name) and func.id in ("open", "Path"):
                is_target = True
            # os.path.join(...)
            elif isinstance(func, ast.Attribute) and func.attr == "join":
                if isinstance(func.value, ast.Attribute) and func.value.attr == "path":
                    if isinstance(func.value.value, ast.Name) and func.value.value.id == "os":
                        is_target = True
            if is_target and call.args:
                arg0 = call.args[0]
                if isinstance(arg0, ast.JoinedStr):
                    bugs.append(BugPredicho(
                        tipo="path_traversal",
                        severidad="critical",
                        mensaje="Path traversal: f-string como ruta en llamada segura",
                        sugerencia="Validar y sanitizar la ruta; usar os.path.realpath() + verificación de prefijo",
                        archivo="",
                        linea=call.lineno,
                        funcion=node.name,
                    ))
                elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Add):
                    bugs.append(BugPredicho(
                        tipo="path_traversal",
                        severidad="critical",
                        mensaje="Path traversal: concatenación de strings como ruta",
                        sugerencia="Validar y sanitizar la ruta; usar os.path.realpath() + verificación de prefijo",
                        archivo="",
                        linea=call.lineno,
                        funcion=node.name,
                    ))
            self.generic_visit(call)

    _Visitor().visit(node)
    return bugs


def _check_hardcoded_secrets(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta string literals asignados a variables con nombres de secretos."""
    bugs: list[BugPredicho] = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        if not isinstance(child.value, ast.Constant) or not isinstance(child.value.value, str):
            continue
        for target in child.targets:
            names: list[str] = []
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, ast.Attribute):
                names.append(target.attr)
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        names.append(elt.id)
            for name in names:
                if _SECRET_RE.search(name):
                    bugs.append(BugPredicho(
                        tipo="hardcoded_secret",
                        severidad="critical",
                        mensaje=f"Secreto hardcodeado en variable '{name}'",
                        sugerencia="Usar variables de entorno, secrets manager, o vault para secretos",
                        archivo="",
                        linea=child.lineno,
                        funcion=node.name,
                    ))
                    break  # un match por asignación basta
    return bugs


def _check_unsafe_deserialization(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Detecta yaml.load() sin Loader seguro."""
    bugs: list[BugPredicho] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            func = call.func
            # yaml.load(...)
            if isinstance(func, ast.Attribute) and func.attr == "load":
                if isinstance(func.value, ast.Name) and func.value.id == "yaml":
                    has_safe_loader = False
                    # Check positional Loader arg (2nd arg)
                    if len(call.args) >= 2:
                        has_safe_loader = _is_safe_yaml_loader(call.args[1])
                    # Check keyword Loader arg
                    for kw in call.keywords:
                        if kw.arg == "Loader":
                            has_safe_loader = _is_safe_yaml_loader(kw.value)
                            break
                    if not has_safe_loader:
                        bugs.append(BugPredicho(
                            tipo="unsafe_deserialization",
                            severidad="critical",
                            mensaje="yaml.load() sin Loader seguro — permite ejecución arbitraria de código",
                            sugerencia="Usar yaml.safe_load() o yaml.load(data, Loader=yaml.SafeLoader)",
                            archivo="",
                            linea=call.lineno,
                            funcion=node.name,
                        ))
            self.generic_visit(call)

    _Visitor().visit(node)
    return bugs


def _is_safe_yaml_loader(node: ast.expr) -> bool:
    """Verifica si un nodo AST referencia un Loader seguro de PyYAML."""
    if isinstance(node, ast.Attribute):
        return node.attr in _SAFE_YAML_LOADERS
    if isinstance(node, ast.Name):
        return node.id in _SAFE_YAML_LOADERS
    return False


def _is_open_call(call: ast.Call) -> bool:
    """Verifica si un Call es open() o io.open()."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "open":
        if isinstance(func.value, ast.Name) and func.value.id in ("io", "_io"):
            return True
    return False


# ── Dispatcher principal ──


def predecir_bugs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[BugPredicho]:
    """Ejecuta todos los checks de predicción de bugs en una función.

    Returns:
        Lista de bugs potenciales detectados
    """
    bugs = []
    bugs.extend(_check_mutable_defaults(node))
    bugs.extend(_check_bare_except(node))
    bugs.extend(_check_resource_leaks(node))
    bugs.extend(_check_unused_variables(node))
    bugs.extend(_check_redefined_args(node))
    bugs.extend(_check_late_binding_closure(node))
    bugs.extend(_check_global_mutation(node))
    bugs.extend(_check_blocking_in_async(node))
    bugs.extend(_check_unawaited_coroutine(node))
    bugs.extend(_check_eval_exec(node))
    bugs.extend(_check_pickle_load(node))
    bugs.extend(_check_shell_true(node))
    bugs.extend(_check_high_complexity(node))
    bugs.extend(_check_long_method(node))
    bugs.extend(_check_deep_nesting(node))
    bugs.extend(_check_sql_injection(node))
    bugs.extend(_check_path_traversal(node))
    bugs.extend(_check_hardcoded_secrets(node))
    bugs.extend(_check_unsafe_deserialization(node))
    return bugs


def predecir_bugs_archivo(archivo_path: str) -> list[BugPredicho]:
    """Analiza un archivo completo y retorna todos los bugs potenciales."""
    import ast as ast_module

    try:
        with open(archivo_path, "r", encoding="utf-8") as f:
            contenido = f.read()
        tree = ast_module.parse(contenido)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return []

    bugs = []
    for node in ast_module.walk(tree):
        if isinstance(node, (ast_module.FunctionDef, ast_module.AsyncFunctionDef)):
            func_bugs = predecir_bugs(node)
            for b in func_bugs:
                b.archivo = archivo_path
            bugs.extend(func_bugs)

    return bugs


def escanear_proyecto(raiz: str) -> dict:
    """Escanea un proyecto completo buscando bugs potenciales."""
    from pathlib import Path

    bugs_totales = []
    archivos_escaneados = 0
    por_tipo = {}
    por_severidad = {"error": 0, "warning": 0, "info": 0}

    for archivo in Path(raiz).rglob("*.py"):
        if any(p.startswith(".") or p in ("__pycache__", "venv", ".venv", "node_modules", "tests")
               for p in archivo.parts):
            continue
        if archivo.name.startswith("test_") or archivo.name == "conftest.py":
            continue

        bugs = predecir_bugs_archivo(str(archivo))
        bugs_totales.extend(bugs)
        archivos_escaneados += 1

    for b in bugs_totales:
        por_tipo.setdefault(b.tipo, []).append(b)
        por_severidad.setdefault(b.severidad, 0)
        por_severidad[b.severidad] += 1

    return {
        "archivos_escaneados": archivos_escaneados,
        "total_bugs": len(bugs_totales),
        "por_severidad": por_severidad,
        "por_tipo": {k: len(v) for k, v in por_tipo.items()},
        "bugs": [
            {
                "tipo": b.tipo,
                "severidad": b.severidad,
                "mensaje": b.mensaje,
                "sugerencia": b.sugerencia,
                "archivo": b.archivo,
                "linea": b.linea,
                "funcion": b.funcion,
                "metrica": b.metrica,
                "valor": b.valor,
            }
            for b in bugs_totales[:50]  # Top 50
        ],
    }
