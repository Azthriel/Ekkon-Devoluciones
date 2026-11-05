import datetime as dt

import pytest

from ekkon import planilla as P
from ekkon.sheets import Planilla, id_de_link

ENCABEZADOS = ['Fecha revisión', 'Fecha compra', 'Articulo', 'SKU', 'N° Venta', 'N° Venta para copiar',
               'Deposito origen', 'NdC', 'Transferencia', 'Deposito final', 'Costo del producto', 'Costo de envio',
               'Motivo', 'Condicion', 'Clasificacion', 'Reclamo', 'N° Mediación', 'Estado (1er reclamo)',
               'Segundo Reclamo', 'Estado (2do reclamo)', 'Monto Reintegrado', 'N° Movimiento',
               '¿Se reporto movimiento?', 'Notas']
HOY = dt.date(2026, 11, 4)


def fila(**kw):
    f = [None] * len(ENCABEZADOS)
    for k, v in kw.items():
        f[ENCABEZADOS.index(k)] = v
    return f


def hoja_ejemplo():
    return P.Hoja([
        ENCABEZADOS,
        fila(**{"Fecha revisión": P.serial(dt.date(2026, 8, 25)), "Articulo": "KOMMBERG MOTOHOYADORA (KB-MH52D)",
                "SKU": "RBXH0014", "N° Venta": "2000014464776957", "NdC": "Si", "Deposito final": "Podestá",
                "Clasificacion": "N", "Reclamo": "no"}),
        fila(**{"Fecha revisión": P.serial(dt.date(2026, 8, 25)), "SKU": "FPI-0060",
                "Articulo": "Sierra Circular 1400w Kb-sc1400", "N° Venta": 2000018082198230.0,
                "NdC": "Si", "Transferencia": "Realizada", "Clasificacion": "N"}),
        fila(**{"Fecha revisión": P.serial(dt.date(2026, 10, 1)), "SKU": "TSE-9785", "N° Venta": "2000014434008281",
                "Articulo": "Soldadora Inverter Kb-xs 150", "NdC": "Si", "Clasificacion": "B",
                "Reclamo": "si", "Estado (1er reclamo)": "Pendiente"}),
        fila(**{"Fecha revisión": P.serial(HOY), "SKU": "FXM-0029", "N° Venta": "2000018604612862",
                "Articulo": "Motor Kommberg Kb-mn65 6.5 Hp"}),
        [" ", None, None, None, ","],
    ])


def dev(venta, **kw):
    d = {"numero_venta": venta, "cargado_en": dt.datetime(2026, 11, 4, 15, tzinfo=dt.timezone.utc),
         "clasificacion": "N", "condicion": "buena", "motivo": "no lo quiere", "deposito_origen": "Podesta",
         "reclamo": False, "estado": "sin_reclamo"}
    d.update(kw)
    return d


def test_estructura_y_busqueda():
    h = hoja_ejemplo()
    assert h.ultima_con_venta() == 3          # ignora la fila basura del final
    assert h.buscar("2000014464776957") == 0
    assert h.buscar("2000018082198231") == 1  # celda numérica que perdió el último dígito
    assert h.buscar("2000099999999999") is None


def test_completa_solo_celdas_vacias():
    h = hoja_ejemplo()
    plan = P.planificar(h, [dev("2000018604612862")])
    escritas = dict(plan.celdas)
    assert not plan.filas_nuevas and not plan.conflictos
    assert escritas["G5"] == "Podesta" and escritas["O5"] == "N" and escritas["J5"] == "Podestá"
    assert escritas["N5"] == "buena" and escritas["M5"] == "no lo quiere" and escritas["P5"] == "no"
    assert "A5" not in escritas and "D5" not in escritas  # misma fecha / SKU ya cargado por él


def test_no_pisa_y_reporta_diferencias():
    h = hoja_ejemplo()
    plan = P.planificar(h, [dev("2000014464776957", clasificacion="B", condicion="Con uso")])
    cols = {c[1] for c in plan.conflictos}
    assert {"Clasificacion", "Deposito final"} <= cols
    assert all(not a1.startswith("O") for a1, _ in plan.celdas)


def test_reemplaza_pendiente_por_resultado():
    h = hoja_ejemplo()
    d = dev("2000014434008281", clasificacion="B", condicion="Con uso", reclamo=True, estado="cobertura",
            monto_reintegrado=81665.0, numero_movimiento="0293785f-191f-40b2-93a4-fe06003e9b22")
    escritas = dict(P.planificar(h, [d]).celdas)
    assert escritas["R4"] == "Cobertura"
    assert escritas["U4"] == 81665.0
    assert escritas["V4"] == "0293785f-191f-40b2-93a4-fe06003e9b22"


def test_fila_nueva():
    h = hoja_ejemplo()
    plan = P.planificar(h, [dev("2000018700000001", codigo_producto="ABC-0001")])
    assert plan.fila_modelo == 5
    numero, valores = plan.filas_nuevas[0]
    assert numero == 6
    assert valores[ENCABEZADOS.index("N° Venta")] == "'2000018700000001"
    assert valores[ENCABEZADOS.index("N° Venta para copiar")] == "=\"'\"&E6"
    assert valores[ENCABEZADOS.index("Fecha revisión")] == P.serial(HOY)
    assert valores[ENCABEZADOS.index("SKU")] == "ABC-0001"


def test_pendientes_y_email_transferencia():
    h = P.Hoja([ENCABEZADOS,
                fila(**{"N° Venta": "2000000000000001", "SKU": "RLA-0045", "Articulo": "Aspiradora (KB-VC60LG)",
                        "Transferencia": "A la espera de movimiento", "Deposito final": "Podestá",
                        "Clasificacion": "N"}),
                fila(**{"N° Venta": "2000000000000002", "SKU": "FN1-0049", "Articulo": "Pulverizador (KB-PVC10)",
                        "Transferencia": "A la espera de movimiento ", "Clasificacion": "N"}),
                fila(**{"N° Venta": "2000000000000003", "SKU": "FN1-0049", "Articulo": "Pulverizador (KB-PVC10)",
                        "Transferencia": "a la espera de movimiento", "Deposito final": "Podestá"}),
                fila(**{"N° Venta": "2000000000000004", "SKU": "XXX-1", "Transferencia": "Email enviado",
                        "NdC": "Si", "Deposito final": "Podestá"}),
                fila(**{"N° Venta": "2000000000000005", "SKU": "XXX-2", "NdC": "Si", "Deposito final": "Podestá"})])
    items = P.pendientes(h)
    assert [i.venta[-1] for i in items] == ["1", "2", "3"]       # solo "A la espera de movimiento"
    assert items[1].destino == "Podestá"                          # sin Deposito final: se deduce de la N
    asunto, cuerpo = P.email_transferencia(items)
    assert asunto == "Solicitud de transferencia - Service Podestá a Podestá"
    assert "Origen: Service Podestá\nDestino: Podestá" in cuerpo
    assert "RLA-0045 | KB-VC60LG | 1" in cuerpo and "FN1-0049 | KB-PVC10 | 2" in cuerpo


def test_email_con_varios_destinos():
    a = P.ItemEmail(1, "1", "S1", "KB-A", "N", "Podestá", None)
    b = P.ItemEmail(2, "2", "S2", "KB-B", "Scrap", "Scrap", None)
    asunto, cuerpo = P.email_transferencia([a, b])
    assert asunto == "Solicitud de transferencia - Service Podestá"
    assert cuerpo.count("Origen: Service Podestá") == 2
    assert "Destino: Scrap" in cuerpo


def test_abc_quedan_en_service_podesta():
    h = hoja_ejemplo()
    plan = P.planificar(h, [dev("2000018604612862", clasificacion="B", condicion="Con uso")])
    assert dict(plan.celdas)["J5"] == "Service Podesta"


def test_sin_deposito_no_escribe_origen():
    h = hoja_ejemplo()
    d = dev("2000018604612862")
    del d["deposito_origen"]
    assert "G5" not in dict(P.planificar(h, [d]).celdas)


@pytest.mark.parametrize("titulo,esperado", [
    ("KOMMBERG MOTOHOYADORA 2T 52CC MANUBRIO DOBLE (KB-MH52D)", "KB-MH52D"),
    ("Sierra Circular Kommberg 1400w Disco 7 PuLG Kb-sc1400", "KB-SC1400"),
    ("Producto sin modelo", "Producto sin modelo"),
])
def test_modelo(titulo, esperado):
    assert P.modelo(titulo) == esperado


def test_link_planilla():
    assert id_de_link("https://docs.google.com/spreadsheets/d/1AbC_def-GHIjklMNOpqrSTUvwxYZ0123456/edit#gid=0") \
        == "1AbC_def-GHIjklMNOpqrSTUvwxYZ0123456"
    assert id_de_link("cualquier cosa") == ""


class Respuesta:
    def __init__(self, data):
        self._d, self.status_code, self.content = data, 200, b"x"

    def json(self):
        return self._d


class SesionFalsa:
    def __init__(self, filas):
        self.filas, self.pedidos = filas, []

    def request(self, metodo, url, **kw):
        self.pedidos.append((metodo, url, kw))
        if "/values/" in url and metodo == "GET":
            return Respuesta({"values": self.filas})
        if metodo == "GET":
            return Respuesta({"sheets": [{"properties": {"sheetId": 7, "title": "Devoluciones",
                                                         "gridProperties": {"rowCount": 5}}}]})
        return Respuesta({})


def test_cliente_aplica_plan():
    h = hoja_ejemplo()
    filas = [h.encabezados] + h.filas
    sesion = SesionFalsa(filas)
    p = Planilla("ID123", sesion=sesion)
    hoja = p.leer()
    plan = P.planificar(hoja, [dev("2000018700000001"), dev("2000018604612862")])
    p.aplicar(plan, hoja)
    posts = [kw["json"] for m, u, kw in sesion.pedidos if m == "POST"]
    pedidos_formato = posts[0]["requests"]
    assert pedidos_formato[0]["appendDimension"]["sheetId"] == 7   # agrega filas a la grilla
    assert {r["copyPaste"]["pasteType"] for r in pedidos_formato[1:]} == {"PASTE_FORMAT", "PASTE_DATA_VALIDATION"}
    assert posts[1]["data"][0]["range"] == "'Devoluciones'!A6:X6"
    assert posts[1]["valueInputOption"] == "USER_ENTERED"
    assert any(d["range"] == "'Devoluciones'!G5" for d in posts[2]["data"])


@pytest.mark.parametrize("clasif,transf,final", [
    ("N", "A la espera de movimiento", "Podestá"),
    ("Scrap", "A la espera de movimiento", "Scrap"),
    ("Service", "Realizada", "Service Podesta"),
    ("A", "Realizada", "Service Podesta"),
    ("B", "Realizada", "Service Podesta"),
    ("E", "Realizada", "Service Podesta"),
])
def test_reglas_al_marcar_nc(clasif, transf, final):
    from ekkon import settings
    assert settings.transferencia_al_hacer_nc(clasif) == transf
    h = hoja_ejemplo()
    d = dev("2000018604612862", clasificacion=clasif, nc_realizada=True,
            transferencia=transf, deposito_final=settings.DEPOSITO_FINAL[clasif])
    escritas = dict(P.planificar(h, [d]).celdas)
    assert escritas["H5"] == "Si" and escritas["I5"] == transf and escritas["J5"] == final


def test_transferencia_cambiada_en_planilla_no_es_diferencia():
    h = hoja_ejemplo()   # fila 3: Transferencia "Realizada"
    d = dev("2000018082198231", nc_realizada=True, transferencia="A la espera de movimiento")
    plan = P.planificar(h, [d])
    assert not any(c[1] == "Transferencia" for c in plan.conflictos)
    assert "I3" not in dict(plan.celdas)


def test_reemplaza_service_interno():
    h = P.Hoja([ENCABEZADOS, fila(**{"N° Venta": "2000000000000009", "Clasificacion": "Service Interno",
                                    "Condicion": "Service Interno"})])
    d = dev("2000000000000009", clasificacion="Service", condicion="Service")
    escritas = dict(P.planificar(h, [d]).celdas)
    assert escritas["O2"] == "Service" and escritas["N2"] == "Service"


def test_enviados_para_marcar_realizada():
    h = P.Hoja([ENCABEZADOS,
                fila(**{"N° Venta": "2000000000000001", "Transferencia": "Email enviado", "Deposito final": "Podestá",
                        "Fecha revisión": P.serial(dt.date(2026, 10, 1))}),
                fila(**{"N° Venta": "2000000000000002", "Transferencia": "Email enviado", "Deposito final": "Scrap",
                        "Fecha revisión": P.serial(dt.date(2026, 11, 1))}),
                fila(**{"N° Venta": "2000000000000003", "Transferencia": "Email enviado",
                        "Deposito final": "Service Podesta"}),
                fila(**{"N° Venta": "2000000000000004", "Transferencia": "Realizada", "Deposito final": "Podestá"})])
    assert [i.venta[-1] for i in P.enviados(h)] == ["2", "1"]
