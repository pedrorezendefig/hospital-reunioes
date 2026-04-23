"""Helpers para parsing de query params HTTP."""


def parse_csv_param(value: str | None) -> list[str] | None:
    """Converte parâmetro CSV (ex: 'TI,Cirurgia') em lista. Retorna None se vazio."""
    if not value or not value.strip():
        return None
    return [v.strip() for v in value.split(",") if v.strip()]
