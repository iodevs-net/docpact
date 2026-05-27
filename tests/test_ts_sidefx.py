"""Tests del verificador de side effects para TypeScript."""

from docpact.checker.ts_sidefx import check_side_effects_ts


# ── api.* ───────────────────────────────────────────────────────────────────


def test_api_post_detectado():
    """api.post() debe ser detectado como side effect."""
    codigo = """
async function crearUsuario(data: UserInput): Promise<User> {
    const res = await api.post("/users", data);
    return res.data;
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_api_get_detectado():
    """api.get() debe ser detectado."""
    codigo = """
function fetchUsers(): Promise<User[]> {
    return api.get("/users").then(r => r.data);
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_api_put_detectado():
    """api.put() debe ser detectado."""
    codigo = "api.put('/users/1', data);"
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_api_delete_detectado():
    """api.delete() debe ser detectado."""
    codigo = "api.delete('/users/1');"
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


# ── axios.* ─────────────────────────────────────────────────────────────────


def test_axios_post_detectado():
    """axios.post() debe ser detectado."""
    codigo = """
export async function submitOrder(items: CartItem[]) {
    const { data } = await axios.post("/orders", { items });
    return data;
}
"""
    errs = check_side_effects_ts(codigo, ["ninguno"])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_axios_get_detectado():
    """axios.get() debe ser detectado."""
    errs = check_side_effects_ts("axios.get('/api/data')", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_axios_put_detectado():
    """axios.put() debe ser detectado."""
    errs = check_side_effects_ts("axios.put('/api/data', body)", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_axios_delete_detectado():
    """axios.delete() debe ser detectado."""
    errs = check_side_effects_ts("axios.delete('/api/data/1')", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


# ── client.* ────────────────────────────────────────────────────────────────


def test_client_post_detectado():
    """client.post() debe ser detectado."""
    errs = check_side_effects_ts("client.post('/rpc/action')", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_client_put_detectado():
    """client.put() debe ser detectado."""
    errs = check_side_effects_ts("client.put('/rpc/update')", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_client_delete_detectado():
    """client.delete() debe ser detectado."""
    errs = check_side_effects_ts("client.delete('/rpc/remove')", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


# ── fetch ───────────────────────────────────────────────────────────────────


def test_fetch_detectado():
    """fetch() debe ser detectado."""
    codigo = """
async function loadProfile(id: string): Promise<Profile> {
    const res = await fetch(`/api/profiles/${id}`);
    return res.json();
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_fetch_with_options():
    """fetch(url, options) debe ser detectado."""
    errs = check_side_effects_ts("fetch('/api/data', { method: 'POST' })", [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_fetch_no_false_positive():
    """Identificadores que contienen 'fetch' no deben activarse."""
    errs = check_side_effects_ts("myFetch('/api/data')", ["ninguno"])
    assert errs == []


# ── .create / .save / .update / .delete ────────────────────────────────────


def test_dot_create_detectado():
    """.create() debe ser detectado."""
    codigo = """
async function addUser(data: NewUser) {
    return await db.user.create({ data });
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_dot_save_detectado():
    """.save() debe ser detectado."""
    codigo = "await entity.save();"
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_dot_update_detectado():
    """.update() debe ser detectado."""
    codigo = "await prisma.user.update({ where: { id }, data: input });"
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_dot_delete_detectado():
    """.delete() debe ser detectado."""
    codigo = "await prisma.user.delete({ where: { id } });"
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


# ── mutate ──────────────────────────────────────────────────────────────────


def test_mutate_detectado():
    """mutate() debe ser detectado."""
    codigo = """
function handleSubmit() {
    mutate({ name: "test" });
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]


def test_mutate_no_false_positive():
    """'mutation' como palabra no debe activar el patrón."""
    errs = check_side_effects_ts("const result = mutation;", [])
    assert errs == []


# ─── Caso consistente: declaró y hay llamadas ───────────────────────────────


def test_consistente_con_llamadas():
    """Declaró side effects y hay llamadas reales → sin errores."""
    codigo = "await api.post('/orders', items);"
    errs = check_side_effects_ts(codigo, ["llamadas a API externa"])
    assert errs == []


# ─── Caso consistente: ninguno y sin llamadas ───────────────────────────────


def test_consistente_ninguno_sin_llamadas():
    """Declaró ninguno y no hay llamadas → sin errores."""
    codigo = """
function formatName(user: User): string {
    return `${user.firstName} ${user.lastName}`;
}
"""
    errs = check_side_effects_ts(codigo, ["ninguno"])
    assert errs == []


def test_vacio_sin_llamadas():
    """Lista vacía de declarados y sin llamadas → sin errores."""
    codigo = "const x = 42;"
    errs = check_side_effects_ts(codigo, [])
    assert errs == []


# ─── Caso inconsistente: declaró pero no hay llamadas ───────────────────────


def test_declaro_sin_llamadas():
    """Declaró side effects pero el código no tiene llamadas → error."""
    codigo = """
function getGreeting(name: string): string {
    return `Hello, ${name}!`;
}
"""
    errs = check_side_effects_ts(codigo, ["llamadas a API externa"])
    assert errs == ["Declaro side effects pero no se detectaron llamadas"]


def test_declaro_multiples_sin_llamadas():
    """Múltiples declaraciones, ninguna llamada real → error."""
    codigo = "const x = 1;"
    errs = check_side_effects_ts(
        codigo, ["llamadas a API", "escritura en BD"],
    )
    assert errs == ["Declaro side effects pero no se detectaron llamadas"]


# ─── Múltiples llamadas en el mismo código ──────────────────────────────────


def test_multiples_llamadas_distintas():
    """Varias llamadas de diferentes tipos en una misma función."""
    codigo = """
async function processOrder(orderId: string) {
    await api.get(`/orders/${orderId}`);
    await axios.post("/payments", { orderId });
    await prisma.order.update({ where: { id: orderId }, data: { status: "paid" } });
}
"""
    errs = check_side_effects_ts(codigo, [])
    assert errs == ["Se detectaron llamadas API pero side_effects: ninguno"]
