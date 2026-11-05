import os
from typing import Literal
from pydantic import BaseModel

class Prop(BaseModel):
    clave: str
    valor: str

class Nodo(BaseModel):
    nombre: str
    tipo: Literal["Partida", "Concepto", "Unidad", "Insumo", "Especificación"]
    propiedades: list[Prop] = []

class Relacion(BaseModel):
    origen: str
    tipo: Literal["contiene", "se mide en", "incluye", "cumple"]
    destino: str

class Grafo(BaseModel):
    nodos: list[Nodo]
    relaciones: list[Relacion]