/**
 * CONTRATO:
 *   input:
 *     ids: number[] — lista de IDs
 *   output: Ticket[]
 *   side_effects: ninguno
 */
async function getTickets(ids: number[]): Promise<Ticket[]> {
    return await Ticket.findAll(ids);
}
