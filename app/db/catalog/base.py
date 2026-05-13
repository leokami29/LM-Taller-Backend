from sqlalchemy.orm import DeclarativeBase


class CatalogBase(DeclarativeBase):
    """Metadatos ORM exclusivos del catálogo (separados del esquema de taller)."""
