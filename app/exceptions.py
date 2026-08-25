class DomainError(Exception):
    """Erro previsível de regra de negócio."""


class InsufficientStockError(DomainError):
    """Solicitação de venda excede o estoque disponível."""


class ProductNotFoundError(DomainError):
    """Produto informado não existe ou não está disponível."""
