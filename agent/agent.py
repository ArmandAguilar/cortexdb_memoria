"""Definición del agente principal interactivo en Google ADK.

Este agente está diseñado para ejecutarse con la interfaz gráfica de ADK Web:
    uv run adk web agent

Permite interactuar en el chat para:
1. Recibir listas de conceptos en texto y procesarlos hacia CortexDB.
2. Procesar archivos de catálogo en Excel (.xlsx/.xls) o CSV.
3. Consultar y explorar los grafos ya guardados en CortexDB.
4. Verificar el estado de salud de la conexión con CortexDB.
"""

import os
from google.adk.agents import LlmAgent
from agent.tools import (
    guardar_concepto_en_cortex,
    procesar_archivo_catalogo,
    buscar_en_cortexdb,
    verificar_estado_cortexdb,
    generar_visualizacion_grafo,
)

MODELO = os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")

INSTRUCCIONES_AGENTE = """Eres un asistente experto en ingeniería de costos, catálogos de obra civil y grafos de conocimiento para CortexDB.

Tu misión es transformar conceptos de obra en grafos de conocimiento estructurados (nodos y relaciones de partidas, conceptos, unidades, insumos y especificaciones) y almacenarlos en CortexDB.

Instrucciones de operación:
1. Si el usuario te da una lista de conceptos en el chat:
   - Identifica la partida, concepto y unidad de cada elemento.
   - Llama a `guardar_concepto_en_cortex` para procesar y persistir cada renglón.
   
2. Si el usuario te indica un archivo Excel o CSV (ej. 'catalogo_ejemplo.csv' o 'catalogo.xlsx'):
   - Llama a la herramienta `procesar_archivo_catalogo` indicando la ruta del archivo.
   
3. Si el usuario te hace preguntas sobre qué información, materiales o insumos están guardados:
   - Utiliza la herramienta `buscar_en_cortexdb` para consultar el grafo y responde con base en los resultados.
   
4. Si el usuario pregunta por el estado del servidor o la base de datos:
   - Llama a `verificar_estado_cortexdb`.

5. Si el usuario te pide ver o graficar el conocimiento de forma visual:
   - Llama a `generar_visualizacion_grafo`.

Responde siempre de manera concisa, estructurada y en español con formato Markdown.
"""

# root_agent es el punto de entrada que 'adk web' carga automáticamente
root_agent = LlmAgent(
    name="cortexdb_agent",
    model=MODELO,
    instruction=INSTRUCCIONES_AGENTE,
    tools=[
        guardar_concepto_en_cortex,
        procesar_archivo_catalogo,
        buscar_en_cortexdb,
        verificar_estado_cortexdb,
        generar_visualizacion_grafo,
    ],
)
