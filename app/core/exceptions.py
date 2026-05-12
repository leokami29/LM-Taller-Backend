class DomainError(Exception):
    """Error de reglas de negocio."""

    def __init__(self, message: str, code: str = "domain_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class InvalidOrderTransitionError(DomainError):
    def __init__(self, message: str = "Transición de estado no permitida") -> None:
        super().__init__(message, code="invalid_order_transition")


class InsufficientStockError(DomainError):
    def __init__(self, message: str = "Stock insuficiente") -> None:
        super().__init__(message, code="insufficient_stock")
