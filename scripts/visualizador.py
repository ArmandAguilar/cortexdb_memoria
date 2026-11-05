"""Módulo visualizador de grafos para CortexDB.

Genera una página web interactiva (HTML) usando la librería 'vis-network'.
Permite explorar visualmente los nodos (Partidas, Conceptos, Insumos,
Especificaciones y Unidades) y sus relaciones con física de movimiento,
buscador y panel de propiedades.
"""

import json
from pathlib import Path
import webbrowser

# ==============================================================================
# Paleta de colores para cada tipo de entidad
# ==============================================================================
COLORES_POR_TIPO = {
    "Partida": {"bg": "#3B82F6", "border": "#1D4ED8", "font": "#FFFFFF"},       # Azul
    "Concepto": {"bg": "#10B981", "border": "#047857", "font": "#FFFFFF"},      # Verde
    "Insumo": {"bg": "#F59E0B", "border": "#D97706", "font": "#000000"},        # Ámbar
    "Unidad": {"bg": "#64748B", "border": "#334155", "font": "#FFFFFF"},        # Gris
    "Especificación": {"bg": "#8B5CF6", "border": "#6D28D9", "font": "#FFFFFF"},# Púrpura
    "DEFAULT": {"bg": "#94A3B8", "border": "#475569", "font": "#FFFFFF"}
}


def generar_archivo_visualizador(
    nodos: list[dict],
    relaciones: list[dict],
    nombre_archivo: str = "grafo_resultado.html"
) -> Path:
    """Genera un archivo HTML interactivo con vis-network a partir de listas de nodos y relaciones.

    Args:
        nodos: Lista de diccionarios con formato:
               {'id': '...', 'label': '...', 'group': 'Tipo', 'properties': {...}}
        relaciones: Lista de diccionarios con formato:
               {'from': 'origen', 'to': 'destino', 'label': 'tipo_relacion'}
        nombre_archivo: Nombre o ruta del archivo HTML que se creará.

    Returns:
        Path del archivo HTML generado.
    """
    # 1. Adaptar los nodos al formato que espera vis-network
    nodos_vis = []
    for n in nodos:
        tipo = n.get("group", "DEFAULT")
        colores = COLORES_POR_TIPO.get(tipo, COLORES_POR_TIPO["DEFAULT"])
        nodos_vis.append({
            "id": n["id"],
            "label": n.get("label", n["id"]),
            "group": tipo,
            "color": {
                "background": colores["bg"],
                "border": colores["border"],
                "highlight": {"background": "#F43F5E", "border": "#BE123C"}
            },
            "font": {"color": colores["font"], "size": 14},
            "properties": n.get("properties", {})
        })

    # 2. Adaptar las relaciones (aristas) con flechas rotuladas
    aristas_vis = []
    for r in relaciones:
        aristas_vis.append({
            "from": r["from"],
            "to": r["to"],
            "label": r.get("label", ""),
            "arrows": "to",
            "font": {"size": 11, "align": "middle", "color": "#94a3b8"},
            "color": {"color": "#64748B", "highlight": "#F43F5E"}
        })

    nodos_json = json.dumps(nodos_vis, ensure_ascii=False)
    aristas_json = json.dumps(aristas_vis, ensure_ascii=False)

    # 3. Plantilla HTML completa con vis-network incrustado
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Visualizador de Grafo Procesado - CortexDB</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
        input[type="text"] {{
            width: 100%;
            padding: 8px 12px;
            background: #0f172a;
            border: 1px solid #475569;
            border-radius: 6px;
            color: #f8fafc;
        }}
        .legend {{ display: flex; flex-direction: column; gap: 6px; }}
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
        <h2>🌐 Grafo CortexDB <span class="badge">{len(nodos_vis)} nodos</span></h2>
        
        <input type="text" placeholder="🔍 Buscar nodo..." oninput="buscarNodo(this.value)">

        <div class="legend">
            <strong>Entidades procesadas:</strong>
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
            nodes: {{ shape: 'dot', size: 20, shadow: true }},
            edges: {{
                width: 1.5,
                smooth: {{ type: 'continuous' }},
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }}
            }},
            physics: {{
                stabilization: false,
                barnesHut: {{ gravitationalConstant: -2500, springConstant: 0.04, springLength: 95 }}
            }},
            interaction: {{ hover: true, navigationButtons: true }}
        }};

        const network = new vis.Network(container, data, options);

        network.on("click", function (params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodes.get(nodeId);
                let html = '<strong>' + node.label + '</strong><br>';
                html += '<span style="color: #94a3b8">Tipo:</span> ' + node.group + '<br><br>';
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
                network.focus(found.id, {{ scale: 1.2, animation: {{ duration: 500 }} }});
                network.selectNodes([found.id]);
            }}
        }}
    </script>
</body>
</html>"""

    destino = Path(nombre_archivo).resolve()
    destino.write_text(html, encoding="utf-8")
    return destino


def abrir_en_navegador(ruta_html: Path | str) -> None:
    """Abre el archivo HTML generado en el navegador predeterminado del sistema."""
    p = Path(ruta_html).resolve()
    if p.exists():
        webbrowser.open(f"file://{p}")

