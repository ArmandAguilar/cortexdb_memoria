"""Módulo de integración con CortexDB mediante gRPC.

Se encarga de:
1. Conectar con el servidor gRPC de CortexDB (cortexdb-grpc).
2. Transformar el Grafo (Pydantic) a los mensajes Protobuf que espera CortexDB.
3. Guardar el conocimiento, entidades y relaciones en la base de datos.
"""

import os
from typing import Optional
from cortexdb_client import CortexClient, proto
from agent.models import Grafo


def obtener_cliente_cortex(
    direccion: Optional[str] = None,
    token: Optional[str] = None
) -> CortexClient:
    """Crea una conexión gRPC con CortexDB.
    
    Toma los valores por defecto desde variables de entorno si no se especifican.
    """
    addr = direccion or os.getenv("CORTEXDB_ADDR", "127.0.0.1:47821")
    tok = token if token is not None else os.getenv("CORTEXDB_GRPC_TOKEN", "")
    
    # Si el token es cadena vacía, se pasa None para deshabilitar auth de Bearer
    token_auth = tok if tok else None
    
    return CortexClient.connect(addr, token=token_auth)


def guardar_grafo_en_cortex(
    client: CortexClient,
    id_conocimiento: str,
    texto_concepto: str,
    grafo: Grafo
) -> proto.SaveKnowledgeResponse:
    """Convierte un Grafo validado a formato Protobuf y lo guarda en CortexDB.

    Args:
        client: Cliente gRPC activo de CortexDB.
        id_conocimiento: Identificador único y determinista (hash SHA-1).
        texto_concepto: Texto original del concepto de obra.
        grafo: Estructura de nodos y relaciones validada con Pydantic.

    Returns:
        SaveKnowledgeResponse con el resultado de la inserción.
    """
    # 1. Convertir los nodos de Pydantic a ToolEntityInput de Protobuf
    entidades_proto = [
        proto.ToolEntityInput(
            id=nodo.nombre,
            name=nodo.nombre,
            type=nodo.tipo,
            metadata={p.clave: p.valor for p in nodo.propiedades}
        )
        for nodo in grafo.nodos
    ]

    # 2. Convertir las relaciones a ToolRelationInput de Protobuf
    # NOTA PARA JR: En Python, 'from' es una palabra reservada del lenguaje.
    # Por eso usamos desempaquetado de diccionario: **{"from": r.origen, ...}
    relaciones_proto = [
        proto.ToolRelationInput(
            **{
                "from": rel.origen,
                "to": rel.destino,
                "type": rel.tipo
            }
        )
        for rel in grafo.relaciones
    ]

    # 3. Construir la solicitud SaveKnowledgeRequest
    solicitud = proto.SaveKnowledgeRequest(
        knowledge_id=id_conocimiento,
        content=texto_concepto,
        entities=entidades_proto,
        relations=relaciones_proto
    )

    # 4. Enviar al servicio KnowledgeService de CortexDB
    respuesta = client.knowledge.SaveKnowledge(solicitud)
    return respuesta

