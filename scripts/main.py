"""Script principal para procesar catálogos de obra y construir grafos en CortexDB.

Paso a paso del flujo:
1. Pide al usuario la ruta del archivo Excel (.xlsx / .xls) o CSV con la muestra.
2. Solicita confirmación al usuario para continuar.
3. Lee los conceptos del archivo identificado.
4. Conecta con el servidor CortexDB (gRPC).
5. Extrae el Grafo de Conocimiento de cada concepto usando Gemini y Google ADK.
6. Valida la integridad referencial (que no existan relaciones huérfanas).
7. Guarda los nodos y relaciones en CortexDB.
8. Genera un archivo HTML interactivo ('grafo_resultado.html') para visualizar
   todos los nodos y relaciones procesados en el navegador.
"""

import os
import sys
import hashlib
import asyncio
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
# Agregamos la raíz del proyecto para importar dependencias del proyecto
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
if str(DIRECTORIO_RAIZ) not in sys.path:
    sys.path.append(str(DIRECTORIO_RAIZ))
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from cortexdb_client import CortexClient, proto
from schemas_nodos import Grafo
from visualizador import generar_archivo_visualizador, abrir_en_navegador

load_dotenv(DIRECTORIO_RAIZ / ".env")

# ==============================================================================
# 1. Configuración de Entorno e Instrucciones del Agente
# ==============================================================================

INSTRUCCION_EXTRACCION_GRAFO = """Extrae un grafo de un renglón de catálogo de obra.
Relaciones permitidas: Partida contiene Concepto; Concepto se mide en Unidad;
Concepto incluye Insumo; Concepto cumple Especificación (propiedades: parametro, valor, unidad).
Un Insumo es un solo elemento ("acarreos"), nunca una frase con ";". Omite el relleno
("todo lo necesario para su correcta ejecución"). Usa solo el texto dado y nombres idénticos en nodos y relaciones."""


# ==============================================================================
# 2. Funciones de Lectura de Archivos (Excel y CSV)
# ==============================================================================

def resolver_ruta_archivo(ruta_str: str) -> Path:
    """Busca el archivo ya sea en la ruta dada, en la carpeta actual o en la raíz."""
    p = Path(ruta_str)
    if p.exists():
        return p
    # Probar en la carpeta de este script
    p_local = Path(__file__).resolve().parent / ruta_str
    if p_local.exists():
        return p_local
    # Probar en la raíz del proyecto
    p_raiz = DIRECTORIO_RAIZ / ruta_str
    if p_raiz.exists():
        return p_raiz
    return p


def leer_archivo_muestra(ruta: Path) -> list[dict]:
    """Lee un Excel o CSV y devuelve filas con las llaves 'partida', 'concepto' y 'unidad'."""
    if ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
    else:
        df = pd.read_excel(ruta)

    df = df.rename(columns=lambda col: str(col).strip().lower())
    return (
        df[["partida", "concepto", "unidad"]]
        .dropna(subset="concepto")
        .drop_duplicates(subset="concepto")
        .fillna({"partida": "General", "unidad": "PZA"})
        .astype(str)
        .to_dict("records")
    )


# ==============================================================================
# 3. Conexión a CortexDB y Extracción con Google ADK
# ==============================================================================

def conectar_cortexdb() -> CortexClient:
    """Crea una conexión con CortexDB gRPC usando los valores de entorno o los por defecto."""
    direccion = os.getenv("CORTEXDB_ADDR", "127.0.0.1:47821")
    token = os.getenv("CORTEXDB_GRPC_TOKEN", "")
    token_auth = token if token else None
    return CortexClient.connect(direccion, token=token_auth)


async def extraer_llm(runner: InMemoryRunner, sid: str, partida: str, concepto: str, unidad: str) -> Grafo:
    """Envía un concepto al modelo Gemini con ADK y valida que el Grafo sea íntegro."""
    # 1. Sesión nueva: un concepto no contamina el contexto del siguiente
    await runner.session_service.create_session(app_name="catalogo", user_id="armand", session_id=sid)

    # 2. Formato del mensaje para el modelo
    msg = types.Content(
        role="user",
        parts=[types.Part(text=f"Partida: {partida}\nUnidad: {unidad}\nConcepto: {concepto}")]
    )

    grafo: Grafo | None = None

    # 3. Ejecuta el agente y escucha sus eventos
    async for ev in runner.run_async(user_id="armand", session_id=sid, new_message=msg):
        if ev.is_final_response():
            # La respuesta final es el JSON y Pydantic lo valida
            grafo = Grafo.model_validate_json(ev.content.parts[0].text)

    if grafo is None:
        raise RuntimeError("El modelo no devolvió ninguna respuesta estructurada.")

    # 4. Validar integridad referencial (no permitir relaciones huérfanas)
    nombres_existentes = {n.nombre for n in grafo.nodos}
    huerfanas = [r for r in grafo.relaciones if r.origen not in nombres_existentes or r.destino not in nombres_existentes]
    if huerfanas:
        raise ValueError(f"Relación rota sin nodo existente: {huerfanas[0]}")

    return grafo


# ==============================================================================
# 4. Función Principal (Flujo Interactivo)
# ==============================================================================

def guardar(client, sid, concepto, g):
    # 'from' es palabra reservada en Python, por eso va como **{"from": ...}
    client.knowledge.SaveKnowledge(proto.SaveKnowledgeRequest(
        knowledge_id=sid,
        content=concepto,
        entities=[proto.ToolEntityInput(id=n.nombre, name=n.nombre, type=n.tipo,
                                        metadata={p.clave: p.valor for p in n.propiedades})
                  for n in g.nodos],
        relations=[proto.ToolRelationInput(**{"from": r.origen, "to": r.destino, "type": r.tipo})
                   for r in g.relaciones],
    ))


async def main():
    if os.getenv("GOOGLE_API_KEY") in (None, "", "tu_google_api_key_aqui"):
        sys.exit("❌ Configura GOOGLE_API_KEY en el archivo .env")

    ruta = resolver_ruta_archivo(input("👉 Archivo (.xlsx, .xls o .csv): ").strip())
    if not ruta.is_file():
        sys.exit(f"❌ No se encontró: {ruta}")
    if input(f"¿Procesar {ruta.resolve()}? (s/n): ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
        sys.exit("🚫 Operación cancelada")

    items = leer_archivo_muestra(ruta)
    client = conectar_cortexdb()
    modelo = os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.5-flash")
    agente = LlmAgent(name="extractor_grafo", model=modelo,
                      instruction=INSTRUCCION_EXTRACCION_GRAFO, output_schema=Grafo)
    runner = InMemoryRunner(agent=agente, app_name="catalogo")

    nodos, relaciones, exitosos = {}, [], 0
    for i, item in enumerate(items, start=1):
        concepto = " ".join(item["concepto"].split())
        sid = hashlib.sha1(concepto.encode()).hexdigest()[:12]
        print(f"[{i}/{len(items)}] {item['partida']} | {concepto[:65]}...")
        try:
            g = await extraer_llm(runner, sid, item["partida"], concepto, item["unidad"])
            guardar(client, sid, concepto, g)
            exitosos += 1
        except Exception as e:
            print(f"   ⚠️ {e}")
            continue
        nodos |= {n.nombre: {"id": n.nombre, "label": n.nombre, "group": n.tipo,
                             "properties": {p.clave: p.valor for p in n.propiedades}} for n in g.nodos}
        relaciones += [{"from": r.origen, "to": r.destino, "label": r.tipo} for r in g.relaciones]
    client.close()

    html = generar_archivo_visualizador(list(nodos.values()), relaciones, "grafo_resultado.html")
    print(f"✔ {exitosos}/{len(items)} conceptos, {len(nodos)} nodos, {len(relaciones)} relaciones: {html.resolve()}")
    abrir_en_navegador(html)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        sys.exit(f"❌ {e}")
