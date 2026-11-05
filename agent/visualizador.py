"""Visualizador gráfico interactivo para CortexDB.

Lee los nodos y relaciones desde la base de datos SQLite de CortexDB
y genera un archivo HTML interactivo con 'vis-network' (nodos de colores,
física de grafos, buscador y panel de propiedades).
"""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import webbrowser

# Paleta de colores para cada tipo de nodo
COLORES_POR_TIPO = {
    "Partida": {"bg": "#3B82F6", "border": "#1D4ED8", "font": "#FFFFFF"},       # Azul
    "Concepto": {"bg": "#10B981", "border": "#047857", "font": "#FFFFFF"},      # Verde
    "Insumo": {"bg": "#F59E0B", "border": "#D97706", "font": "#000000"},        # Ámbar
    "Unidad": {"bg": "#64748B", "border": "#334155", "font": "#FFFFFF"},        # Gris
    "Especificación": {"bg": "#8B5CF6", "border": "#6D28D9", "font": "#FFFFFF"},# Púrpura
    "DEFAULT": {"bg": "#94A3B8", "border": "#475569", "font": "#FFFFFF"}
}


def encontrar_db_cortex(ruta_personalizada: str | None = None) -> Path:
    """Localiza la base de datos SQLite de CortexDB."""
    if ruta_personalizada and Path(ruta_personalizada).exists():
        return Path(ruta_personalizada)

    # 1. Probar en el directorio actual
    local = Path("cortexdb.db")
    if local.exists():
        return local

    # 2. Probar en ~/.cortexdb/cortexdb.db (ubicación por defecto)
    por_defecto = Path.home() / ".cortexdb" / "cortexdb.db"
    if por_defecto.exists():
        return por_defecto

    # Si no existe aún ninguna, devolver la ruta por defecto
    return por_defecto


def extraer_datos_grafo(ruta_db: Path) -> tuple[list[dict], list[dict]]:
    """Consulta los nodos y aristas desde la base SQLite de CortexDB."""
    if not ruta_db.exists():
        raise FileNotFoundError(
            f"No se encontró la base de datos en: {ruta_db}.\n"
            f"Asegúrate de que 'cortexdb-grpc' haya iniciado y guardado al menos un concepto."
        )

    conn = sqlite3.connect(ruta_db)
    cursor = conn.cursor()

    # Verificar si existen las tablas del grafo
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes'")
    if not cursor.fetchone():
        conn.close()
        return [], []

    # 1. Obtener nodos
    cursor.execute("SELECT id, node_type, properties, content FROM graph_nodes")
    nodos_raw = cursor.fetchall()

    nodos = []
    for id_nodo, tipo, props_json, contenido in nodos_raw:
        tipo_nodo = tipo or "Concepto"
        colores = COLORES_POR_TIPO.get(tipo_nodo, COLORES_POR_TIPO["DEFAULT"])

        props_dict = {}
        if props_json:
            try:
                props_dict = json.loads(props_json)
            except Exception:
                props_dict = {"raw": props_json}

        nodos.append({
            "id": id_nodo,
            "label": id_nodo,
            "group": tipo_nodo,
            "title": f"Tipo: {tipo_nodo}\nContenido: {contenido or ''}",
            "color": {
                "background": colores["bg"],
                "border": colores["border"],
                "highlight": {"background": "#F43F5E", "border": "#BE123C"}
            },
            "font": {"color": colores["font"], "size": 14},
            "properties": props_dict,
            "content": contenido or ""
        })

    # 2. Obtener aristas (relaciones)
    cursor.execute("SELECT from_node_id, to_node_id, edge_type, weight FROM graph_edges")
    aristas_raw = cursor.fetchall()

    aristas = []
    for desde, hacia, tipo_arista, peso in aristas_raw:
        aristas.append({
            "from": desde,
            "to": hacia,
            "label": tipo_arista or "",
            "arrows": "to",
            "font": {"size": 11, "align": "middle", "color": "#475569"},
            "color": {"color": "#94A3B8", "highlight": "#F43F5E"}
        })

    conn.close()
    return nodos, aristas


def generar_html_grafo(nodos: list[dict], aristas: list[dict], archivo_salida: str = "grafo.html") -> Path:
    """Genera una página web interactiva con vis-network para visualizar el grafo."""
    nodos_json = json.dumps(nodos, ensure_ascii=False)
    aristas_json = json.dumps(aristas, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Visualizador de Grafos - CortexDB</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            height: 100vh;
            background: #0f172a;
            color: #f8fafc;
            overflow: hidden;
        }}
        #sidebar {{
            width: 320px;
            background: #1e293b;
            border-right: 1px solid #334155;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            z-index: 10;
        }}
        h2 {{ font-size: 1.2rem; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
        .badge {{ font-size: 0.75rem; background: #0284c7; color: white; padding: 2px 8px; border-radius: 9999px; }}
        .controls {{ display: flex; flex-direction: column; gap: 8px; }}
        input[type="text"] {{
            width: 100%;
            padding: 8px 12px;
            background: #0f172a;
            border: 1px solid #475569;
            border-radius: 6px;
            color: #f8fafc;
        }}
        .legend {{ display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }}
        .color-dot {{ width: 14px; height: 14px; border-radius: 50%; display: inline-block; }}
        #details {{
            margin-top: auto;
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 12px;
            max-height: 250px;
            overflow-y: auto;
            font-size: 0.85rem;
        }}
        #network {{
            flex: 1;
            height: 100%;
            background: #090d16;
        }}
    </style>
</head>
<body>
    <div id="sidebar">
        <h2>🌐 CortexDB Grafo <span class="badge" id="node-count">{len(nodos)} nodos</span></h2>
        
        <div class="controls">
            <input type="text" id="search-box" placeholder="🔍 Buscar nodo..." oninput="buscarNodo(this.value)">
        </div>

        <div class="legend">
            <strong>Leyenda de Entidades:</strong>
            <div class="legend-item"><span class="color-dot" style="background: #3B82F6"></span> Partida</div>
            <div class="legend-item"><span class="color-dot" style="background: #10B981"></span> Concepto</div>
            <div class="legend-item"><span class="color-dot" style="background: #F59E0B"></span> Insumo</div>
            <div class="legend-item"><span class="color-dot" style="background: #8B5CF6"></span> Especificación</div>
            <div class="legend-item"><span class="color-dot" style="background: #64748B"></span> Unidad</div>
        </div>

        <div id="details">
            <em>Haz clic en un nodo para ver sus propiedades y relaciones.</em>
        </div>
    </div>

    <div id="network"></div>

    <script type="text/javascript">
        const rawNodes = {nodos_json};
        const rawEdges = {aristas_json};

        const nodes = new vis.DataSet(rawNodes);
        const edges = new vis.DataSet(rawEdges);

        const container = document.getElementById('network');
        const data = {{ nodes: nodes, edges: edges }};
        const options = {{
            nodes: {{
                shape: 'dot',
                size: 20,
                shadow: true
            }},
            edges: {{
                width: 1.5,
                smooth: {{ type: 'continuous' }},
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }}
            }},
            physics: {{
                stabilization: false,
                barnesHut: {{
                    gravitationalConstant: -3000,
                    springConstant: 0.04,
                    springLength: 95
                }}
            }},
            interaction: {{
                hover: true,
                navigationButtons: true,
                keyboard: true
            }}
        }};

        const network = new vis.Network(container, data, options);

        network.on("click", function (params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodes.get(nodeId);
                let html = '<strong>' + node.label + '</strong><br>';
                html += '<span style="color: #94a3b8">Tipo:</span> ' + node.group + '<br><br>';
                if (node.content) {{
                    html += '<span style="color: #94a3b8">Contenido:</span><br>' + node.content + '<br><br>';
                }}
                if (node.properties && Object.keys(node.properties).length > 0) {{
                    html += '<span style="color: #94a3b8">Propiedades:</span><pre style="margin-top:4px">' + JSON.stringify(node.properties, null, 2) + '</pre>';
                }}
                document.getElementById('details').innerHTML = html;
            }}
        }});

        function buscarNodo(val) {{
            if (!val) return;
            const q = val.toLowerCase();
            const found = rawNodes.find(n => n.label.toLowerCase().includes(q));
            if (found) {{
                network.focus(found.id, {{
                    scale: 1.2,
                    animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }}
                }});
                network.selectNodes([found.id]);
            }}
        }}
    </script>
</body>
</html>"""

    destino = Path(archivo_salida).resolve()
    destino.write_text(html, encoding="utf-8")
    return destino


def main():
    parser = argparse.ArgumentParser(description="Visualiza el grafo de CortexDB en tu navegador.")
    parser.add_argument("--db", type=str, help="Ruta al archivo SQLite de CortexDB", default=None)
    parser.add_argument("--output", type=str, help="Nombre del archivo HTML de salida", default="grafo.html")
    parser.add_argument("--no-open", action="store_true", help="No abrir automáticamente en el navegador")

    args = parser.parse_args()

    ruta_db = encontrar_db_cortex(args.db)
    print(f"📂 Leyendo base de datos de CortexDB desde: {ruta_db}")

    try:
        nodos, aristas = extraer_datos_grafo(ruta_db)
    except Exception as e:
        print(f"❌ Error al consultar la base de datos: {e}")
        return

    if not nodos:
        print("⚠️ No se encontraron nodos aún en CortexDB. Procesa primero algunos conceptos o archivos de catálogo.")
        return

    salida = generar_html_grafo(nodos, aristas, args.output)
    print(f"✨ ¡Grafo generado con éxito en: {salida}")
    print(f"   - Total de nodos: {len(nodos)}")
    print(f"   - Total de relaciones: {len(aristas)}")

    if not args.no_open:
        print("🌐 Abriendo en tu navegador predeterminado...")
        webbrowser.open(f"file://{salida}")


if __name__ == "__main__":
    main()

