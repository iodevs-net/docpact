// CONTRATO:
//   input:
//     msg: string — mensaje a loguear
//   output: void
//   side_effects: escribe en archivo de log
function logMessage(msg: string): void {
    fs.writeFileSync('/tmp/log', msg);
}
