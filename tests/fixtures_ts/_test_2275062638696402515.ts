/**
 * CONTRATO:
 *   input:
 *     usuario_id: number — ID del usuario a buscar
 *   output: User | null
 *   side_effects: ninguno
 *   rn:
 *     - RN-005: usuario debe existir en BD
 */
async function findUser(usuario_id: number): Promise<User | null> {
    return db.findUser(usuario_id);
}
