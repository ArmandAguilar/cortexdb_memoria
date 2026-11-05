"""Modelos de datos y esquemas Pydantic para el grafo de conocimiento.

Estos esquemas tienen dos funciones principales:
1. Obligan al LLM de Gemini a responder exactamente en este formato estructurado (output_schema).
2. Validan que los tipos de nodos y verbos de relación sean únicamente los permitidos.
"""

from typing import Literal
from pydantic import BaseModel, Field


class Propiedad(BaseModel):
    """Representa un atributo o detalle de un nodo (par clave-valor).
    
    Ejemplo: clave="resistencia", valor="250 kg/cm2"
    """
    clave: str = Field(description="Nombre del atributo o parámetro")
    valor: str = Field(description="Valor del atributo")


class Nodo(BaseModel):
    """Representa una entidad o concepto dentro del grafo."""
    nombre: str = Field(description="Nombre único del nodo, sirve como identificador")
    tipo: Literal["Partida", "Concepto", "Unidad", "Insumo", "Especificación"] = Field(
        description="Categoría a la que pertenece la entidad"
    )
    propiedades: list[Propiedad] = Field(
        default_factory=list,
        description="Lista de propiedades adicionales del nodo"
    )


class Relacion(BaseModel):
    """Representa una conexión dirigida entre dos nodos (Origen -> Destino)."""
    origen: str = Field(description="Nombre del nodo de inicio")
    tipo: Literal["contiene", "se mide en", "incluye", "cumple"] = Field(
        description="Verbo o relación permitida entre los nodos"
    )
    destino: str = Field(description="Nombre del nodo de destino")


class Grafo(BaseModel):
    """Estructura completa que devuelve el LLM con todas las entidades y conexiones."""
    nodos: list[Nodo] = Field(description="Lista de todos los nodos identificados")
    relaciones: list[Relacion] = Field(description="Lista de todas las relaciones entre nodos")


class RenglonCatalogo(BaseModel):
    """Representa una fila o renglón de entrada de un catálogo de obra."""
    partida: str
    concepto: str
    unidad: str

