"""Reparaciones del service (las carga José): datos, planilla "Reparaciones" y vínculo con devoluciones.

En la planilla de reparaciones el programa es la fuente: lo que se carga en la app se escribe en la
planilla (pisa el valor anterior de esa celda). Una celda vacía en la app nunca borra la planilla.
"""
from __future__ import annotations

import datetime as dt
import re

from . import settings
from .os_idx import clave_os
from .planilla import (Hoja, Plan, fecha_de_serial, letra_columna, modelo, normalizar, para_escribir,
                       vacia)

COL = "reparaciones"

# Encabezados de la planilla de Reparaciones
R_FECHA_REV = "Fecha de revisión"
R_FECHA_REP = "Fecha de reparación"
R_NUMERO = "N° Venta/OS"
R_PRODUCTO = "Producto"
R_SKU = "SKU"
R_ESTADO = "Estado actual"
R_CAUSA = "Causa"
R_A_REALIZAR = "Reparación a Realizar"
R_HECHO = "Que se hizo"
R_REPARADO = "¿Reparado?"
R_REPUESTO = "¿Se requirió repuesto?"
R_ORIGEN = "¿De donde se obtuvo?"
R_FINAL = "Estado final"
R_HORAS = "Horas aproximadas"
R_NOTAS = "Notas adicionales"

CAMPOS = [  # (campo en la app, columna de la planilla)
    ("fecha_revision", R_FECHA_REV), ("fecha_reparacion", R_FECHA_REP), ("numero", R_NUMERO),
    ("producto", R_PRODUCTO), ("sku", R_SKU), ("estados", R_ESTADO), ("causa", R_CAUSA),
    ("a_realizar", R_A_REALIZAR), ("que_se_hizo", R_HECHO), ("reparado", R_REPARADO),
    ("repuesto", R_REPUESTO), ("origen_repuesto", R_ORIGEN), ("estado_final", R_FINAL),
    ("horas", R_HORAS), ("notas", R_NOTAS),
]


# ---------------------------------------------------------------- claves

def es_venta(numero: str) -> bool:
    d = re.sub(r"\D", "", numero or "")
    return len(d) == 16 and d.startswith("2")


def clave(numero) -> str:
    """Clave para comparar: Venta # de 16 dígitos tal cual; OS sin ceros adelante."""
    d = re.sub(r"\D", "", str(numero or "") if not isinstance(numero, float) else str(int(numero)))
    if len(d) == 16 and d.startswith("2"):
        return d
    return clave_os(numero)


def doc_id(numero) -> str:
    k = clave(numero)
    return ("V" if es_venta(k) else "OS") + k if k else ""


def coincide(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # Venta guardada como número en la planilla: pierde el último dígito
    return len(a) == len(b) == 16 and a[:15] == b[:15] and a.endswith("0")


def leer_hoja(filas: list[list]) -> Hoja:
    return Hoja(filas, clave=R_NUMERO, requeridas=(R_NUMERO, R_ESTADO), leer_clave=clave, coincide=coincide)


# ---------------------------------------------------------------- reglas

def finalizada(r: dict) -> bool:
    """Terminada: tiene estado final y se marcó si quedó reparada o está "Finalizado"."""
    return bool(r.get("estado_final")) and (r.get("reparado") in ("Si", "No") or "Finalizado" in (r.get("estados") or []))


def completar_fechas(r: dict, hoy: dt.date | None = None) -> dict:
    hoy = hoy or dt.date.today()
    r = dict(r)
    if not r.get("fecha_revision"):
        r["fecha_revision"] = hoy.isoformat()
    estados = r.get("estados") or []
    if not r.get("fecha_reparacion") and (r.get("reparado") == "Si" or "Reparada" in estados
                                          or "Finalizado" in estados):
        r["fecha_reparacion"] = hoy.isoformat()
    return r


def nota_devolucion(r: dict) -> str:
    """Nota para la columna Notas de la planilla de devoluciones cuando la reparación termina."""
    fecha = r.get("fecha_reparacion") or r.get("fecha_revision") or ""
    if fecha:
        a, m, d = fecha.split("-")
        fecha = f"{d}/{m}/{a}"
    hecho = (r.get("que_se_hizo") or "").strip().rstrip(".")
    partes = [f"Reparación {fecha}".strip()]
    if r.get("reparado") == "No":
        partes[0] += " (no se pudo reparar)"
    texto = partes[0] + (f": {hecho}" if hecho else "")
    if r.get("estado_final"):
        texto += f". Estado final: {r['estado_final']}"
    return texto


def clasificacion_final(r: dict) -> str | None:
    return settings.CLASIF_POR_ESTADO_FINAL.get(r.get("estado_final") or "")


def cambios_para_devolucion(dev: dict, r: dict) -> dict:
    """Qué hay que actualizar en la devolución vinculada: solo la nota y la clasificación."""
    if not finalizada(r):
        return {}
    cambios: dict = {}
    nota = nota_devolucion(r)
    if dev.get("nota_reparacion") != nota:
        cambios["nota_reparacion"] = nota
    nueva = clasificacion_final(r)
    if nueva and dev.get("clasificacion") != nueva:
        original = dev.get("clasificacion_original") or dev.get("clasificacion")
        cambios["clasificacion"] = nueva
        cambios["clasificacion_original"] = original
        # El depósito final de la planilla no cambia: queda el que correspondía a la clasificación original
        cambios["deposito_final"] = dev.get("deposito_final") or settings.DEPOSITO_FINAL.get(original or "", "")
    return cambios


# ---------------------------------------------------------------- planilla de reparaciones

def _celda(campo: str, valor):
    if valor in (None, "", []):
        return None
    if campo in ("fecha_revision", "fecha_reparacion"):
        return dt.date.fromisoformat(valor)
    if campo == "estados":
        return ", ".join(valor)
    if campo == "numero":
        return para_escribir("N° Venta", valor) if es_venta(valor) else str(valor)
    return valor


def _iguales(actual, nuevo, campo: str) -> bool:
    if campo in ("fecha_revision", "fecha_reparacion"):
        return isinstance(nuevo, dt.date) and (fecha_de_serial(actual) == nuevo)
    if campo == "numero":
        return clave(actual) == clave(nuevo.lstrip("'"))
    if campo == "horas":
        try:
            return abs(float(str(actual).replace(",", ".")) - float(nuevo)) < 0.001
        except (TypeError, ValueError):
            return False
    if campo == "estados":
        partes = lambda t: sorted(normalizar(x) for x in str(t or "").split(",") if x.strip())  # noqa: E731
        return partes(actual) == partes(nuevo)
    return normalizar(actual) == normalizar(nuevo)


def planificar(hoja: Hoja, reparaciones: list[dict]) -> Plan:
    plan = Plan()
    ultima = hoja.ultima_con_venta()
    plan.fila_modelo = hoja.numero_fila(ultima) if ultima >= 0 else None
    siguiente = hoja.numero_fila(ultima + 1)
    ancho = len(hoja.encabezados)
    for r in sorted(reparaciones, key=lambda x: (x.get("fecha_revision") or "", x.get("numero") or "")):
        k = clave(r.get("numero"))
        if not k:
            continue
        fila0 = hoja.buscar(k)
        valores = {col: _celda(campo, r.get(campo)) for campo, col in CAMPOS}
        if fila0 is None:
            nueva = [None] * ancho
            for col, val in valores.items():
                i = hoja.indice(col)
                if i is not None and val is not None:
                    nueva[i] = val
                elif i is None and val is not None:
                    plan.sin_columna.add(col)
            plan.filas_nuevas.append((siguiente, nueva))
            siguiente += 1
            continue
        numero = hoja.numero_fila(fila0)
        for campo, col in CAMPOS:
            val = valores[col]
            i = hoja.indice(col)
            if val is None or campo == "numero":
                continue
            if i is None:
                plan.sin_columna.add(col)
                continue
            if not _iguales(hoja.valor(fila0, col), val, campo):
                plan.celdas.append((f"{letra_columna(i)}{numero}", val))
                plan.actualizadas.add(k)
    return plan


def desde_hoja(hoja: Hoja, existentes: set[str], os_idx: dict, buscar_venta) -> list[dict]:
    """Filas de la planilla que todavía no están en la app, listas para guardar (con producto y SKU)."""
    salida = []
    for i in range(len(hoja.filas)):
        k = hoja.clave_de(i)
        if not k or doc_id(k) in existentes:
            continue
        crudo = str(hoja.valor(i, R_NUMERO) or "").strip()
        r: dict = {"numero": k if es_venta(k) else crudo.lstrip("'").strip() or k}
        for campo, col in CAMPOS:
            if campo == "numero":
                continue
            v = hoja.valor(i, col)
            if vacia(v):
                continue
            if campo in ("fecha_revision", "fecha_reparacion"):
                f = fecha_de_serial(v)
                if f:
                    r[campo] = f.isoformat()
            elif campo == "estados":
                r[campo] = [x.strip() for x in str(v).split(",") if x.strip()]
            elif campo == "horas":
                try:
                    r[campo] = float(str(v).replace(",", "."))
                except ValueError:
                    pass
            else:
                r[campo] = str(v).strip()
        completar_producto(r, os_idx, buscar_venta)
        salida.append(r)
    return salida


def completar_producto(r: dict, os_idx: dict, buscar_venta) -> dict:
    """Completa producto y SKU desde el informe de OS o el de ventas (si faltan).

    buscar_venta(numero) -> ventas.Venta | None (acepta Venta # o ID Carrito).
    """
    k = clave(r.get("numero"))
    info_os = os_idx.get(k) if not es_venta(k) else None
    venta = buscar_venta(k) if es_venta(k) and buscar_venta else None
    producto, sku = "", ""
    if info_os:
        producto, sku = info_os.get("producto", ""), info_os.get("sku", "")
    elif venta:
        producto, sku = venta.producto, venta.codigo
    if producto and not r.get("producto"):
        r["producto"] = producto
    # Si el producto de la planilla venía como "SKU NOMBRE", se deja el nombre del informe
    elif producto and sku and str(r.get("producto", "")).startswith(sku):
        r["producto"] = producto
    if sku and not r.get("sku"):
        r["sku"] = sku
    return r


def modelo_corto(r: dict) -> str:
    return modelo(r.get("producto") or "")


# ---------------------------------------------------------------- repositorio

class Reparaciones:
    def __init__(self, fs):
        self.fs = fs

    def listar(self) -> list[dict]:
        return self.fs.listar(COL)

    def obtener(self, numero) -> dict | None:
        i = doc_id(numero)
        return self.fs.obtener(f"{COL}/{i}") if i else None

    def guardar(self, r: dict, usuario: dict, nueva: bool) -> dict:
        ahora = dt.datetime.now(dt.timezone.utc)
        datos = {k: v for k, v in r.items() if not k.startswith("_")}
        datos["actualizado_en"] = ahora
        datos["actualizado_por"] = usuario.get("email", "")
        if nueva:
            datos.setdefault("creado_en", ahora)
            datos.setdefault("creado_por", usuario.get("email", ""))
        return self.fs.guardar(f"{COL}/{doc_id(r['numero'])}", datos)

    def borrar(self, numero) -> None:
        self.fs.borrar(f"{COL}/{doc_id(numero)}")
