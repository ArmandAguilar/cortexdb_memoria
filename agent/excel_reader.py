"""Módulo para lectura de archivos de catálogo de obra (Excel y CSV).

Soporta formatos:
- .csv (usando la librería estándar de Python)
- .xlsx / .xls (usando openpyxl si está instalado)

Normaliza automáticamente los nombres de columnas para ser tolerante a variaciones
como 'Partida', 'PARTIDA', 'Descripción', 'Concepto', 'Unidad', etc.
"""

import csv
import os
import unicodedata
from pathlib import Path
from agent.models import RenglonCatalogo


def _normalizar_texto(texto: str) -> str:
    """Elimina acentos y convierte a minúsculas para comparaciones robustas."""
    if not texto:
        return ""
    texto_sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )
    return texto_sin_acentos.strip().lower()


def _identificar_columnas(encabezados: list[str]) -> tuple[int | None, int | None, int | None]:
    """Identifica los índices de las columnas: partida, concepto y unidad."""
    idx_partida = None
    idx_concepto = None
    idx_unidad = None

    alias_partida = {"partida", "partidas", "capitulo", "rubro", "seccion"}
    alias_concepto = {"concepto", "conceptos", "descripcion", "detalle", "texto"}
    alias_unidad = {"unidad", "unidades", "ud", "um", "u.m.", "medida"}

    for idx, h in enumerate(encabezados):
        norm = _normalizar_texto(h)
        if norm in alias_partida and idx_partida is None:
            idx_partida = idx
        elif norm in alias_concepto and idx_concepto is None:
            idx_concepto = idx
        elif norm in alias_unidad and idx_unidad is None:
            idx_unidad = idx

    return idx_partida, idx_concepto, idx_unidad


def leer_catalogo_csv(ruta: Path) -> list[RenglonCatalogo]:
    """Lee un archivo CSV delimitado por comas o punto y coma."""
    renglones: list[RenglonCatalogo] = []
    
    with open(ruta, mode="r", encoding="utf-8-sig") as f:
        # Detectar el delimitador (, o ;)
        muestra = f.read(2048)
        f.seek(0)
        delimitador = ";" if ";" in muestra and muestra.count(";") > muestra.count(",") else ","
        
        lector = csv.reader(f, delimiter=delimitador)
        try:
            encabezados = next(lector)
        except StopIteration:
            return []

        idx_partida, idx_concepto, idx_unidad = _identificar_columnas(encabezados)

        if idx_concepto is None:
            raise ValueError(
                f"El archivo CSV debe tener una columna 'concepto' o 'descripcion'. "
                f"Encabezados encontrados: {encabezados}"
            )

        for fila in lector:
            if not fila or not any(fila):
                continue
            
            partida = fila[idx_partida].strip() if idx_partida is not None and idx_partida < len(fila) else "General"
            concepto = fila[idx_concepto].strip() if idx_concepto < len(fila) else ""
            unidad = fila[idx_unidad].strip() if idx_unidad is not None and idx_unidad < len(fila) else "PZA"

            if concepto:
                renglones.append(RenglonCatalogo(partida=partida, concepto=concepto, unidad=unidad))

    return renglones


def leer_catalogo_excel(ruta: Path) -> list[RenglonCatalogo]:
    """Lee un archivo Excel (.xlsx / .xls). Requiere openpyxl."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError(
            "Para leer archivos Excel (.xlsx), se requiere 'openpyxl'. "
            "Instálalo con: 'uv add openpyxl' o utiliza un archivo en formato CSV."
        )

    wb = openpyxl.load_workbook(ruta, data_only=True)
    hoja = wb.active
    renglones: list[RenglonCatalogo] = []

    filas = list(hoja.iter_rows(values_only=True))
    if not filas:
        return []

    encabezados = [str(col) if col is not None else "" for col in filas[0]]
    idx_partida, idx_concepto, idx_unidad = _identificar_columnas(encabezados)

    if idx_concepto is None:
        raise ValueError(
            f"El archivo Excel debe tener una columna 'concepto' o 'descripcion'. "
            f"Encabezados encontrados: {encabezados}"
        )

    for fila in filas[1:]:
        if not fila or not any(fila):
            continue
        
        partida = str(fila[idx_partida]).strip() if idx_partida is not None and idx_partida < len(fila) and fila[idx_partida] is not None else "General"
        concepto = str(fila[idx_concepto]).strip() if idx_concepto < len(fila) and fila[idx_concepto] is not None else ""
        unidad = str(fila[idx_unidad]).strip() if idx_unidad is not None and idx_unidad < len(fila) and fila[idx_unidad] is not None else "PZA"

        if concepto:
            renglones.append(RenglonCatalogo(partida=partida, concepto=concepto, unidad=unidad))

    return renglones


def leer_archivo_catalogo(ruta_archivo: str | Path) -> list[RenglonCatalogo]:
    """Punto de entrada general para leer catálogo desde archivo (CSV o Excel)."""
    p = Path(ruta_archivo)
    if not p.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_archivo}")

    sufijo = p.suffix.lower()
    if sufijo == ".csv":
        return leer_catalogo_csv(p)
    elif sufijo in {".xlsx", ".xls"}:
        return leer_catalogo_excel(p)
    else:
        # Intentar como CSV por defecto si no tiene extensión conocida
        try:
            return leer_catalogo_csv(p)
        except Exception:
            raise ValueError(f"Formato no soportado: '{sufijo}'. Usa .xlsx o .csv")

