class ContractViolationError(AssertionError):
    """Se lanza cuando un contrato de docpact es violado en tiempo de ejecución (runtime)."""

    def __init__(self, funcion: str, archivo: str, linea: int, efecto_violado: str, detalle: str):
        self.funcion = funcion
        self.archivo = archivo
        self.linea = linea
        self.efecto_violado = efecto_violado
        self.detalle = detalle
        mensaje = (
            f"\n❌ VIOLACIÓN DE CONTRATO DOCPACT DETECTADA\n"
            f"   Función: {funcion}\n"
            f"   Archivo: {archivo}:{linea}\n"
            f"   Efecto Violado: {efecto_violado}\n"
            f"   Detalle: {detalle}\n"
        )
        super().__init__(mensaje)
