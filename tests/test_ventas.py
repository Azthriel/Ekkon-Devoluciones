import datetime as dt

from ekkon import planilla as P
from ekkon import ventas as V

CSV = '''"Pedido: ID";"Venta ML#: Venta #";"ID Carrito";"Venta ML#: Fecha/Hora  Venta";"Venta ML#: Codigo de Producto";"Producto";"Sucursal";"Venta ML#: Cantidad";"Venta ML#: Precio Unitario"
"PED-1";"2000017796698832";"";"6/8/2026, 18:55";"FPF-0007";"KOMMBERG AFILADOR (KB-AFM65)";"Podestá";"1";"88606,56"
"PED-2";"2000018016486734";"2000014609910837";"19/8/2026, 13:09";"FPC-0024";"KOMMBERG CEPILLADORA (KB-CE650)";"Fulfillment";"1";"81171,80"
"PED-3";"2000017188543148";"2000013782033763";"1/7/2026, 00:27";"RSPF0060";"MASCARA (KB-MF25E)";"Podestá";"1";"21978,80"
"PED-3";"2000017188548602";"2000013782033763";"1/7/2026, 00:27";"FPA-0166";"AMOLADORA (KB-AM115)";"Boedo";"2";"44438,38"
"PED-4";"2000017188549999";"";"1/7/2026, 00:30";"FPA-0001";"OTRO";"General Paz";"1";"1000,00"


"Ventas ML para APP"
"Copyright (c) 2000-2026 salesforce.com, inc. Reservados todos los derechos."
"Generado por:  Dto Devoluciones  5/11/2026, 09:54"
'''.encode("utf-8-sig")


def cargar():
    return {v.venta: v for v in V.leer_csv(CSV)}


def test_lee_csv_de_salesforce():
    vs = V.leer_csv(CSV)
    assert len(vs) == 5                      # ignora las líneas finales de Salesforce
    assert vs[4].deposito == "GP"
    v = vs[0]
    assert (v.pedido, v.venta, v.carrito, v.fecha) == ("PED-1", "2000017796698832", "", dt.date(2026, 8, 6))
    assert v.precio == 88606.56 and v.deposito == "Podesta"
    assert vs[1].deposito == "Full" and vs[3].deposito == "LP" and vs[3].cantidad == 2


def test_partes_y_busqueda():
    todas = cargar()
    partes = V.armar_partes(todas)
    assert len(partes) == 100
    datos = {n: V.decodificar(V.codificar(p)) for n, p in partes.items()}

    class FS:
        def obtener(self, ruta):
            return {"datos": V.codificar(datos[ruta.split("/")[1]])}

    idx = V.Indice(FS())
    assert idx.buscar("2000017796698832").tipo == "venta"
    r = idx.buscar("2000014609910837")                     # carrito con una venta
    assert r.tipo == "carrito" and r.venta.venta == "2000018016486734"
    r = idx.buscar("2000013782033763")                     # carrito con dos ventas
    assert r.tipo == "carrito" and r.venta is None and len(r.opciones) == 2
    assert idx.buscar("2000099999999999").tipo == "no_encontrado"


def test_combinar_conserva_180_dias():
    viejas = {"1": V.Venta("1", "", "", dt.date(2026, 1, 1), "", "", "", 1, None)}
    todas = V.combinar(viejas, list(cargar().values()), hoy=dt.date(2026, 11, 5))
    assert "1" not in todas and len(todas) == 5


def test_planilla_se_completa_con_el_informe():
    from test_planilla import ENCABEZADOS, fila
    h = P.Hoja([ENCABEZADOS,
                fila(**{"N° Venta": "2000017796698832", "SKU": "FPF-0007"}),           # cargada a mano
                fila(**{"N° Venta": "2000014609910837"}),                             # tiene el carrito
                fila(**{"N° Venta": 2000017188543140.0})])                            # perdió el último dígito
    plan = P.planificar(h, [], cargar())
    escritas = dict(plan.celdas)
    assert escritas["B2"] == dt.date(2026, 8, 6)
    assert escritas["C2"] == "KOMMBERG AFILADOR (KB-AFM65)"
    assert escritas["G2"] == "Podesta" and "K2" not in escritas   # filas viejas: no se toca el costo
    assert "D2" not in escritas                                   # el SKU ya estaba
    assert escritas["D4"] == "RSPF0060"                           # encontrada por los primeros 15 dígitos
    assert plan.correcciones() == [("E3", "'2000018016486734")]
    assert not plan.conflictos


def test_devolucion_con_carrito_en_la_planilla_no_duplica_fila():
    from test_planilla import ENCABEZADOS, fila, dev
    h = P.Hoja([ENCABEZADOS, fila(**{"N° Venta": "2000014609910837"})])
    plan = P.planificar(h, [dev("2000018016486734", clasificacion="B", condicion="Con uso")], cargar())
    assert not plan.filas_nuevas
    assert plan.correcciones() == [("E2", "'2000018016486734")]
    escritas = dict(plan.celdas)
    assert escritas["O2"] == "B" and escritas["K2"] == 81171.80 and escritas["C2"] == "KOMMBERG CEPILLADORA (KB-CE650)"


def test_columna_pedido_opcional():
    from test_planilla import ENCABEZADOS
    h = P.Hoja([ENCABEZADOS + ["N° Pedido"], ["", None, None, None, "2000017796698832"] + [None] * 20])
    escritas = dict(P.planificar(h, [], cargar()).celdas)
    assert escritas["Y2"] == "PED-1"


def test_devolucion_vieja_cargada_con_carrito():
    from test_planilla import ENCABEZADOS, fila, dev
    h = P.Hoja([ENCABEZADOS, fila(**{"N° Venta": "2000014609910837", "Fecha revisión": P.serial(dt.date(2026, 11, 4))})])
    plan = P.planificar(h, [dev("2000014609910837", _id="2000014609910837")], cargar(), hoy=dt.date(2026, 11, 5))
    escritas = dict(plan.celdas)
    assert plan.correcciones() == [("E2", "'2000018016486734")]
    assert escritas["C2"] == "KOMMBERG CEPILLADORA (KB-CE650)" and escritas["G2"] == "Full"
    assert escritas["A2"] == dt.date(2026, 11, 5)
    # si no estaba en la planilla, la fila nueva lleva el Venta #
    h = P.Hoja([ENCABEZADOS])
    plan = P.planificar(h, [dev("2000014609910837")], cargar())
    assert plan.filas_nuevas[0][1][4] == "'2000018016486734"


def test_misma_venta_cargada_dos_veces_escribe_una_sola_fila():
    from test_planilla import ENCABEZADOS, dev
    h = P.Hoja([ENCABEZADOS])
    devs = [dev("2000014609910837", _id="2000014609910837"),      # cargada con el carrito
            dev("2000018016486734", _id="2000018016486734")]      # la misma, con el Venta #
    plan = P.planificar(h, devs, cargar())
    assert len(plan.filas_nuevas) == 1
    assert plan.duplicadas == [("2000018016486734", "2000018016486734", "2000014609910837")]


def test_avisa_ventas_repetidas_en_la_planilla():
    from test_planilla import ENCABEZADOS, fila
    h = P.Hoja([ENCABEZADOS, fila(**{"N° Venta": "2000019107329828"}), fila(**{"N° Venta": "'2000019107329828"}),
                fila(**{"N° Venta": "2000019107329000"})])
    assert P.planificar(h, []).repetidas_en_planilla == [("2000019107329828", [2, 3])]
