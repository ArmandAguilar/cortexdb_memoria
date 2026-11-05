"""Herramientas (Tools) de Google ADK para interactuar con CortexDB y procesar catálogos.

Estas herramientas son consumidas por el agente interactivo en ADK Web (interfaz web).
"""

import os
from pathlib import Path
from google import genai
from google.genai import types
from cortexdb_client import proto

from agent.models import Grafo, RenglonCatalogo
from agent.cortex import obtener_cliente_cortex, guardar_grafo_en_cortex
from agent.extractor import generar_id_conocimiento, validar_integridad_grafo
from agent.excel_reader import leer_archivo_catalogo


MODELO_EXTRACCION = os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")

REGLAS_EXTRACCION = """Extrae un grafo de conocimiento a partir de un renglón de catálogo de obra.

Reglas obligatorias:
1. Relaciones permitidas:
   - Partida contiene Concepto
   - Concepto se mide en Unidad
   - Concepto incluye Insumo
   - Concepto cumple Especificación (con propiedades: parametro, valor, unidad)

2. Criterios de limpieza:
   - Un Insumo debe ser un término conciso (ej. "acarreos", "cemento"), nunca una lista o frase con ";".
   - Omite el texto de relleno innecesario (ej. "todo lo necesario para su correcta ejecución").
   - Usa únicamente información presente en el texto proporcionado.
   - Usa nombres idénticos entre los nodos y los campos 'origen' y 'destino' de las relaciones.
"""


def _extraer_grafo_directo(partida: str, concepto: str, unidad: str) -> Grafo:
    """Invoca Gemini con salida estructurada para extraer el Grafo."""
    client_genai = genai.Client()
    texto_entrada = f"Partida: {partida}\nUnidad: {unidad}\nConcepto: {concepto}"

    response = client_genai.models.generate_content(
        model=MODELO_EXTRACCION,
        contents=texto_entrada,
        config=types.GenerateContentConfig(
            system_instruction=REGLAS_EXTRACCION,
            response_mime_type="application/json",
            response_schema=Grafo,
        )
    )

    if getattr(response, "parsed", None) and isinstance(response.parsed, Grafo):
        grafo = response.parsed
    else:
        grafo = Grafo.model_validate_json(response.text)

    validar_integridad_grafo(grafo)
    return grafo


def guardar_concepto_en_cortex(partida: str, concepto: str, unidad: str) -> str:
    """Extrae las entidades y relaciones de un concepto de obra y lo guarda en CortexDB.

    Úsalo cuando el usuario te proporcione los detalles de un concepto de obra o cuando
    quieras procesar un renglón individual.

    Args:
        partida: Capítulo o sección de la obra (ej. 'Estructura', 'Albañilería').
        concepto: Descripción detallada del trabajo o insumos.
        unidad: Unidad de medida (ej. 'M3', 'KG', 'M2', 'PZA').
    """
    texto_limpio = " ".join(concepto.split())
    sid = generar_id_conocimiento(texto_limpio)

    try:
        grafo = _extraer_grafo_directo(partida, texto_limpio, unidad)
    except Exception as e:
        return f"❌ Error al extraer el grafo con Gemini: {e}"

    try:
        with obtener_cliente_cortex() as client:
            guardar_grafo_en_cortex(
                client=client,
                id_conocimiento=sid,
                texto_concepto=texto_limpio,
                grafo=grafo
            )
    except Exception as e:
        return (
            f"❌ Error al conectar o guardar en CortexDB: {e}\n"
            f"Asegúrate de que 'cortexdb-grpc -token \"\"' esté ejecutándose en tu terminal."
        )

    resumen_nodos = ", ".join(f"[{n.tipo}] {n.nombre}" for n in grafo.nodos[:6])
    if len(grafo.nodos) > 6:
        resumen_nodos += f" ... (+{len(grafo.nodos)-6} más)"

    return (
        f"✅ **Concepto guardado con éxito en CortexDB**\n\n"
        f"- **ID:** `{sid}`\n"
        f"- **Partida:** {partida} ({unidad})\n"
        f"- **Nodos extraídos ({len(grafo.nodos)}):** {resumen_nodos}\n"
        f"- **Relaciones ({len(grafo.relaciones)}):** Conexiones de inclusión, medición y especificación registradas."
    )


def procesar_archivo_catalogo(ruta_archivo: str) -> str:
    """Lee un archivo Excel (.xlsx/.xls) o CSV de catálogo de obra, extrae sus grafos y los guarda en CortexDB.

    Úsalo cuando el usuario te proporcione la ruta a un archivo de catálogo o solicite
    procesar una hoja de cálculo completa.

    Args:
        ruta_archivo: Ruta local al archivo (ej. 'catalogo_ejemplo.csv' o '/ruta/a/archivo.xlsx').
    """
    try:
        renglones = leer_archivo_catalogo(ruta_archivo)
    except Exception as e:
        return f"❌ Error al leer el archivo '{ruta_archivo}': {e}"

    if not renglones:
        return f"⚠️ El archivo '{ruta_archivo}' no contiene renglones válidos para procesar."

    exitosos = 0
    errores = []

    try:
        client = obtener_cliente_cortex()
    except Exception as e:
        return f"❌ No se pudo conectar a CortexDB: {e}. (Revisa que cortexdb-grpc esté corriendo)."

    try:
        for idx, item in enumerate(renglones, start=1):
            texto_limpio = " ".join(item.concepto.split())
            sid = generar_id_conocimiento(texto_limpio)
            try:
                grafo = _extraer_grafo_directo(item.partida, texto_limpio, item.unidad)
                guardar_grafo_en_cortex(client, sid, texto_limpio, grafo)
                exitosos += 1
            except Exception as e:
                errores.append(f"Fila {idx} ({texto_limpio[:30]}...): {e}")
    finally:
        client.close()

    resultado = [
        f"📊 **Resumen del procesamiento del archivo:** `{Path(ruta_archivo).name}`",
        f"- **Total de renglones procesados con éxito:** {exitosos}/{len(renglones)}",
    ]

    if errores:
        resultado.append(f"\n⚠️ **Errores encontrados ({len(errores)}):**")
        for err in errores[:5]:
            resultado.append(f"  - {err}")
        if len(errores) > 5:
            resultado.append(f"  - ... y {len(errores)-5} más.")

    return "\n".join(resultado)


def _buscar_relaciones_grafo(termino: str, limite: int = 15) -> list[str]:
    """Busca conexiones directas en graph_edges y graph_nodes en la base SQLite local."""
    from agent.visualizador import encontrar_db_cortex
    import sqlite3
    try:
        ruta_db = encontrar_db_cortex()
        if not ruta_db.exists():
            return []
        conn = sqlite3.connect(ruta_db)
        cursor = conn.cursor()
        patron = f"%{termino.strip()}%"
        cursor.execute(
            """
            SELECT e.from_node_id, e.edge_type, e.to_node_id
            FROM graph_edges e
            WHERE e.from_node_id LIKE ? OR e.to_node_id LIKE ? OR e.edge_type LIKE ?
            LIMIT ?
            """,
            (patron, patron, patron, limite)
        )
        filas = cursor.fetchall()
        conn.close()
        return [f"`{desde}` --[{tipo}]--> `{hacia}`" for desde, tipo, hacia in filas]
    except Exception:
        return []


def buscar_en_cortexdb(consulta: str, limite: int = 5) -> str:
    """Busca conceptos, entidades y relaciones almacenadas en CortexDB.

    Úsalo cuando el usuario haga preguntas sobre qué información, materiales, insumos
    o partidas se encuentran guardadas en la base de datos de grafos.

    Args:
        consulta: Término de búsqueda o pregunta (ej. 'concreto', 'acero', 'mortero', 'acabados').
        limite: Número máximo de resultados a devolver (por defecto 5).
    """
    respuesta = None
    try:
        with obtener_cliente_cortex() as client:
            solicitud = proto.SearchKnowledgeRequest(
                query=consulta,
                top_k=limite
            )
            respuesta = client.knowledge.SearchKnowledge(solicitud)
    except Exception as e:
        # Si falla gRPC, aún intentamos buscar en SQLite local
        pass

    relaciones_grafo = _buscar_relaciones_grafo(consulta)
    tiene_hits = respuesta is not None and bool(respuesta.results)

    if not tiene_hits and not relaciones_grafo:
        return f"ℹ️ No se encontraron resultados en CortexDB para la consulta: '{consulta}'."

    lineas = [f"🔍 **Resultados encontrados en CortexDB para:** *{consulta}*\n"]

    if relaciones_grafo:
        lineas.append("🕸️ **Relaciones directas encontradas en el Grafo:**")
        for rel in relaciones_grafo:
            lineas.append(f"   - {rel}")
        lineas.append("")

    if tiene_hits and respuesta:
        lineas.append("📄 **Conceptos coincidentes (Knowledge):**")
        for idx, hit in enumerate(respuesta.results, start=1):
            texto_snippet = getattr(hit, "snippet", "") or getattr(hit, "content", "") or getattr(hit, "title", "") or "Sin texto disponible"
            lineas.append(f"**{idx}. ID:** `{hit.knowledge_id}` (Similitud: {hit.score:.2f})")
            lineas.append(f"   - **Contenido:** {texto_snippet}")
            if hit.entities:
                lineas.append(f"   - **Entidades vinculadas:** {', '.join(hit.entities)}")
            lineas.append("")

    return "\n".join(lineas)


def verificar_estado_cortexdb() -> str:
    """Verifica si el servidor CortexDB (cortexdb-grpc) está activo y respondiendo."""
    try:
        with obtener_cliente_cortex() as client:
            # Intento de búsqueda trivial para comprobar que el socket y gRPC responden
            client.knowledge.SearchKnowledge(proto.SearchKnowledgeRequest(query="ping", top_k=1))
        return "🟢 **CortexDB está activo y respondiendo correctamente en el puerto 47821.**"
    except Exception as e:
        return (
            f"🔴 **CortexDB no responde:** {e}\n\n"
            f"Para iniciarlo en tu terminal ejecuta:\n"
            f"```bash\n"
            f"~/go/bin/cortexdb-grpc -token \"\"\n"
            f"```"
        )



def generar_visualizacion_grafo(salida_html: str = "grafo.html") -> str:
    """Genera un archivo HTML interactivo con la visualización completa de los nodos y relaciones en CortexDB.

    Úsalo cuando el usuario te pida ver el grafo de forma gráfica, visual o en el navegador.

    Args:
        salida_html: Nombre del archivo HTML a generar (por defecto 'grafo.html').
    """
    from agent.visualizador import encontrar_db_cortex, extraer_datos_grafo, generar_html_grafo
    try:
        ruta_db = encontrar_db_cortex()
        nodos, aristas = extraer_datos_grafo(ruta_db)
        if not nodos:
            return "⚠️ No hay nodos guardados en CortexDB para graficar todavía. Procesa primero algunos conceptos."

        path_salida = generar_html_grafo(nodos, aristas, salida_html)
        return (
            f"🌐 **¡Visualización gráfica generada con éxito!**\n\n"
            f"- **Total de nodos:** {len(nodos)}\n"
            f"- **Total de relaciones:** {len(aristas)}\n"
            f"- **Archivo generado:** `{path_salida}`\n\n"
            f"Para abrirlo en tu navegador en macOS ejecuta:\n"
            f"```bash\n"
            f"open {salida_html}\n"
            f"```"
        )
    except Exception as e:
        return f"❌ Error al generar la visualización gráfica: {e}"
