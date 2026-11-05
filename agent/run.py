"""Script principal de ejecución (Pipeline de Catálogo a Grafo en CortexDB).

Flujo paso a paso:
1. Carga las variables de entorno (.env).
2. Conecta con el servidor gRPC de CortexDB.
3. Inicializa el Runner de Google ADK con el agente extractor.
4. Itera sobre los renglones de obra (ej. Concreto, Acero).
5. Extrae el Grafo estructurado con Gemini.
6. Valida la integridad de nodos y relaciones.
7. Guarda el grafo en CortexDB.
"""

import asyncio
import os
from pathlib import Path

from google.adk.runners import InMemoryRunner

from agent.cortex import obtener_cliente_cortex, guardar_grafo_en_cortex
from agent.extractor import extraer_grafo, generar_id_conocimiento, crear_agente_extractor
from agent.models import RenglonCatalogo


def cargar_env():
    """Carga variables desde .env sin requerir librerías externas adicionales."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


# Datos de prueba reales de un catálogo de obra civil
RENGLONES_EJEMPLO = [
    RenglonCatalogo(
        partida="Estructura",
        unidad="M3",
        concepto=(
            "Concreto premezclado f'c=250 kg/cm2, agregado máximo de 19 mm, "
            "incluye: vaciado, vibrado, curado y pruebas de laboratorio. "
            "Insumos: agua, cemento, grava, arena."
        )
    ),
    RenglonCatalogo(
        partida="Estructura",
        unidad="KG",
        concepto=(
            "Suministro y colocación de acero de refuerzo No. 4 (1/2 pulgada), f'y=4200 kg/cm2, "
            "incluye: alambre recocido, traslapes, ganchos, silletas y desperdicios."
        )
    )
]


async def procesar_renglones():
    cargar_env()

    # 1. Verificar credencial de Google
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "tu_google_api_key_aqui":
        print("❌ Error: Debes configurar una GOOGLE_API_KEY válida en el archivo .env")
        return

    # 2. Conectar a CortexDB
    print("🔌 Conectando a CortexDB...")
    try:
        cliente_cortex = obtener_cliente_cortex()
    except Exception as e:
        print(f"❌ Error al inicializar cliente CortexDB: {e}")
        return

    # 3. Inicializar el Runner de Google ADK con el agente extractor
    agente_extractor = crear_agente_extractor()
    runner = InMemoryRunner(agent=agente_extractor, app_name="catalogo_obra")

    print(f"\n🚀 Iniciando procesamiento de {len(RENGLONES_EJEMPLO)} conceptos de catálogo...\n")

    # 4. Procesar cada renglón
    for idx, item in enumerate(RENGLONES_EJEMPLO, start=1):
        texto_limpio = " ".join(item.concepto.split())
        sid = generar_id_conocimiento(texto_limpio)

        print(f"[{idx}/{len(RENGLONES_EJEMPLO)}] Procesando partida: '{item.partida}' | ID: {sid}")
        print(f"   Texto: {texto_limpio[:70]}...")

        # 5. Extraer el grafo usando Google ADK
        try:
            grafo = await extraer_grafo(
                runner=runner,
                session_id=sid,
                partida=item.partida,
                concepto=texto_limpio,
                unidad=item.unidad
            )
            print(f"   ✅ Grafo extraído: {len(grafo.nodos)} nodos, {len(grafo.relaciones)} relaciones")
        except Exception as e:
            print(f"   ⚠️  Error en extracción del concepto: {e}")
            continue

        # 6. Guardar en CortexDB
        try:
            respuesta = guardar_grafo_en_cortex(
                client=cliente_cortex,
                id_conocimiento=sid,
                texto_concepto=texto_limpio,
                grafo=grafo
            )
            print(f"   💾 Guardado en CortexDB con éxito (Knowledge ID: {sid})")
        except Exception as e:
            print(f"   ❌ Error al guardar en CortexDB: {e}")
            print("      (Asegúrate de que 'cortexdb-grpc -token \"\"' esté ejecutándose)")

        print("-" * 60)

    # 7. Cerrar la conexión con CortexDB
    cliente_cortex.close()
    print("\n✨ Proceso completado.")


if __name__ == "__main__":
    asyncio.run(procesar_renglones())
