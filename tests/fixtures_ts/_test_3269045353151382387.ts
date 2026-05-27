// CONTRATO:
//   output: void
//   side_effects: escribe en DB, envía email, actualiza caché
function processOrder(): void {
    db.save();
    email.send();
    cache.update();
}
