"""Lógica de extracción y validación de grafos con Google ADK.

Contiene:
1. Generación de IDs estables e idempotentes (SHA-1).
2. Ejecución asíncrona del agente mediante InMemoryRunner.
3. Validación de integridad referencial para evitar relaciones huérfanas.
"""

import hashlib
import os
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from agent.models import Grafo


def crear_agente_extractor() -> LlmAgent:
    """Crea una instancia especializada en extracción estructurada (Grafo JSON)."""
    from agent.tools import REGLAS_EXTRACCION, MODELO_EXTRACCION
    return LlmAgent(
        name="extractor_estructurado",
        model=MODELO_EXTRACCION,
        instruction=REGLAS_EXTRACCION,
        output_schema=Grafo
    )



def generar_id_conocimiento(texto: str, longitud: int = 12) -> str:
    """Genera un ID determinista a partir del texto del concepto.
    
    Esto asegura que el mismo concepto siempre tenga el mismo ID en CortexDB,
    evitando duplicar información.
    """
    texto_normalizado = " ".join(texto.split())
    return hashlib.sha1(texto_normalizado.encode("utf-8")).hexdigest()[:longitud]


def validar_integridad_grafo(grafo: Grafo) -> None:
    """Verifica que no existan relaciones hacia nodos inexistentes (relaciones huérfanas).

    Raises:
        ValueError: Si alguna relación apunta a un nodo que no está en la lista de nodos.
    """
    nombres_existentes = {nodo.nombre for nodo in grafo.nodos}
    
    for rel in grafo.relaciones:
        if rel.origen not in nombres_existentes:
            raise ValueError(f"Relación inválida: El nodo origen '{rel.origen}' no existe en los nodos.")
        if rel.destino not in nombres_existentes:
            raise ValueError(f"Relación inválida: El nodo destino '{rel.destino}' no existe en los nodos.")


async def extraer_grafo(
    runner: InMemoryRunner,
    session_id: str,
    partida: str,
    concepto: str,
    unidad: str,
    user_id: str = "armand",
    app_name: str = "catalogo"
) -> Grafo:
    """Ejecuta el agente de ADK para extraer entidades y relaciones de un renglón.

    Args:
        runner: Ejecutor de ADK (InMemoryRunner).
        session_id: ID único de la sesión (aísla el contexto de cada renglón).
        partida: Nombre del capítulo o partida (ej. 'Estructura').
        concepto: Descripción detallada del trabajo a realizar.
        unidad: Unidad de medida (ej. 'M3', 'KG').
        user_id: Identificador del usuario para la sesión.
        app_name: Nombre de la aplicación en el runner.

    Returns:
        Grafo validado con Pydantic y sin relaciones rotas.
    """
    # 1. Crear una sesión nueva para que un concepto no contamine el contexto del siguiente
    await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id
    )

    # 2. Formatear los datos del renglón en el formato de mensaje de Google GenAI
    texto_entrada = f"Partida: {partida}\nUnidad: {unidad}\nConcepto: {concepto}"
    mensaje = types.Content(
        role="user",
        parts=[types.Part(text=texto_entrada)]
    )

    grafo_extraido: Grafo | None = None

    # 3. Ejecutar el agente de forma asíncrona y escuchar los eventos
    async for evento in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=mensaje
    ):
        if evento.is_final_response():
            # Obtener el texto JSON devuelto por Gemini y validarlo con Pydantic
            texto_json = evento.content.parts[0].text
            grafo_extraido = Grafo.model_validate_json(texto_json)

    if grafo_extraido is None:
        raise RuntimeError("El agente no devolvió ninguna respuesta final.")

    # 4. Validar que ninguna relación quede huérfana
    validar_integridad_grafo(grafo_extraido)

    return grafo_extraido

