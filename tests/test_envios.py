import datetime as dt
import json
import zlib

from ekkon import envios_idx as E

CSV = '''"Devolucion: ID Devolucion";"ID Envio";"ID Venta/Carrito";"ID Reclamo";"Titulo Publicacion";"Codigo de Producto";"Cantidad en Devolucion";"Fecha de Creacion";"Estado Devolucion";"Costo Envio Vendedor";"Costo Envio"
"DEV-09037";"48577583673";"2000015643879993";"5615375516";"Equipo Pistola Para Pintar";"FPQ-0035";"1";"19/11/2026, 15:47";"devolucion entregada";"10490,00";"10490,00"
"DEV-08008";"47883207665";"2000014720455377";"5568094276";"Limpiadora A Vapor";"RLV-0012";"2";"29/8/2026, 10:25";"devolucion entregada";"15440,00";"15440,00"


"Devoluciones para APP"
"Generado por:  Dto Devoluciones  26/11/2026, 09:47"
'''.encode("utf-8")


class FS:
    def __init__(self):
        self.docs = {}

    def obtener(self, ruta):
        return self.docs.get(ruta)

    def guardar(self, ruta, datos):
        self.docs[ruta] = datos


def test_lee_informe_y_busca_por_envio_venta_reclamo_y_dev():
    d = E.leer_csv(CSV)
    assert set(d) == {"48577583673", "47883207665"}
    e = d["48577583673"]
    assert e["venta"] == "2000015643879993" and e["sku"] == "FPQ-0035" and e["fecha"] == "2026-11-19"
    assert e["costo_envio"] == 10490.0 and d["47883207665"]["cantidad"] == 2
    assert E.es_envio("48577583673") and not E.es_envio("2000015643879993")
    fs = FS()
    idx = E.IndiceEnvios(fs)
    meta = idx.importar(d, "yo", hoy=dt.date(2026, 11, 26))
    assert meta["envios_total"] == 2
    assert idx.buscar(" 48577583673 ")[0]["devolucion"] == "DEV-09037"
    assert idx.buscar("2000015643879993")[0]["envio"] == "48577583673"
    assert idx.buscar("5615375516")[0]["envio"] == "48577583673"
    assert idx.buscar("dev-09037")[0]["envio"] == "48577583673"
    assert idx.buscar("123") == []
    # Se conservan 180 días
    E.IndiceEnvios(fs).importar({}, "yo", hoy=dt.date(2027, 3, 10))
    datos = json.loads(zlib.decompress(fs.docs[E.DOC]["datos"]).decode())
    assert set(datos) == {"48577583673"}
