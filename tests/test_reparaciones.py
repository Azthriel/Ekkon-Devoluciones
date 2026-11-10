import datetime as dt

from ekkon import os_idx as O
from ekkon import planilla as P
from ekkon import reparaciones as R
from test_planilla import ENCABEZADOS, HOY, dev, fila

ENC_REP = ["Fecha de revisión", "Fecha de reparación", "N° Venta/OS", "Producto", "SKU", "Estado actual", "Causa",
           "Reparación a Realizar", "Que se hizo", "¿Reparado?", "¿Se requirió repuesto?", "¿De donde se obtuvo?",
           "Estado final", "Horas aproximadas", "Notas adicionales"]

OS_CSV = '''"Orden de Servicio: Orden";"Producto: Denominación";"Producto: Código / SKU";"Fecha ingreso";"Fecha Reparación";"Fecha Presupuesto";"Descripción del cliente";"Informe técnico";"Observaciones Adicionales";"Tipo de servicio"
"000463";"KOMMBERG MULTIFUNCION (KB-5.1BL20)";"FPD-0181";"29/8/2026";"";"";"NO FUNCIONA
SOLO EQUIPO";"PLACA QUEMADA";"";"Garantía"
"000538";"KOMMBERG CEPILLADORA GARLOPA 1500W (KB-CG8N)";"FEE-0011";"26/9/2026";"";"";"";"";"";"Reparación"


"OS para APP"
"Copyright (c) 2000-2026 salesforce.com"
'''.encode("utf-8-sig")


def frep(**kw):
    f = [None] * len(ENC_REP)
    for k, v in kw.items():
        f[ENC_REP.index(k)] = v
    return f


def test_lee_informe_de_os():
    d = O.leer_csv(OS_CSV)
    assert set(d) == {"463", "538"}
    assert d["463"]["sku"] == "FPD-0181" and d["463"]["fecha"] == "2026-08-29" and "SOLO EQUIPO" in d["463"]["cliente"]


def test_claves():
    assert R.clave("000463") == "463" and R.clave("538 ") == "538" and R.clave(463.0) == "463"
    assert R.clave("2000018710417116") == "2000018710417116"
    assert R.doc_id("463") == "OS463" and R.doc_id("2000018710417116") == "V2000018710417116"


def test_importar_desde_la_planilla():
    h = R.leer_hoja([ENC_REP,
                     frep(**{"N° Venta/OS": "463", "Estado actual": "Reparada, Enviado a GP",
                             "Fecha de revisión": P.serial(dt.date(2026, 10, 28)), "Horas aproximadas": 0.6}),
                     frep(**{"N° Venta/OS": "538 ", "Producto": "FEE-0011 KOMMBERG CEPILLADORA",
                             "Estado actual": "Para revisar"}),
                     frep(**{"N° Venta/OS": "-"})])
    reps = R.desde_hoja(h, set(), O.leer_csv(OS_CSV), lambda n: None)
    assert [r["numero"] for r in reps] == ["463", "538"]
    a, b = reps
    assert a["estados"] == ["Reparada", "Enviado a GP"] and a["fecha_revision"] == "2026-10-28" and a["horas"] == 0.6
    assert a["producto"] == "KOMMBERG MULTIFUNCION (KB-5.1BL20)" and a["sku"] == "FPD-0181"
    assert b["producto"] == "KOMMBERG CEPILLADORA GARLOPA 1500W (KB-CG8N)"   # "SKU NOMBRE" -> nombre del informe
    # Al sincronizar, se completan producto y SKU en la planilla sin tocar lo demás
    plan = R.planificar(h, reps)
    escritas = dict(plan.celdas)
    assert escritas["D2"] == a["producto"] and escritas["E2"] == "FPD-0181" and escritas["E3"] == "FEE-0011"
    assert not plan.filas_nuevas and "F2" not in escritas and "A2" not in escritas and "N2" not in escritas


def test_la_app_manda_en_la_planilla_de_reparaciones():
    h = R.leer_hoja([ENC_REP, frep(**{"N° Venta/OS": "463", "Estado actual": "Para revisar"})])
    r = {"numero": "463", "estados": ["Reparada"], "reparado": "Si", "estado_final": "GP",
         "fecha_revision": "2026-11-01", "fecha_reparacion": "2026-11-10", "que_se_hizo": "Cambio de placa"}
    e = dict(R.planificar(h, [r]).celdas)
    assert e["F2"] == "Reparada" and e["J2"] == "Si" and e["M2"] == "GP" and e["B2"] == dt.date(2026, 11, 10)
    nueva = R.planificar(R.leer_hoja([ENC_REP]), [r]).filas_nuevas[0][1]
    assert nueva[2] == "463" and nueva[5] == "Reparada"


def test_fechas_automaticas():
    r = R.completar_fechas({"estados": ["Para revisar"]}, hoy=dt.date(2026, 11, 10))
    assert r["fecha_revision"] == "2026-11-10" and "fecha_reparacion" not in r
    r = R.completar_fechas({**r, "estados": ["Reparada"]}, hoy=dt.date(2026, 11, 12))
    assert r["fecha_revision"] == "2026-11-10" and r["fecha_reparacion"] == "2026-11-12"


def test_reparacion_terminada_en_la_planilla_de_devoluciones():
    venta = "2000018604612862"
    r = {"numero": venta, "estados": ["Finalizado"], "reparado": "Si", "estado_final": "Outlet B",
         "fecha_reparacion": "2026-11-10", "que_se_hizo": "Cambio de placa de control."}
    d = dev(venta, clasificacion="Service", condicion="Service")
    cambios = R.cambios_para_devolucion(d, r)
    assert cambios["clasificacion"] == "B" and cambios["clasificacion_original"] == "Service"
    assert cambios["nota_reparacion"] == "Reparación 10/11/2026: Cambio de placa de control. Estado final: Outlet B"
    d.update(cambios)
    h = P.Hoja([ENCABEZADOS, fila(**{"N° Venta": venta, "Clasificacion": "Service", "Deposito final": "Service Podesta",
                                    "Notas": "Revisar cable"})])
    plan = P.planificar(h, [d], hoy=HOY)
    escritas = dict(plan.celdas)
    assert escritas["O2"] == "B"                                     # clasificación nueva
    assert escritas["X2"] == "Revisar cable | " + cambios["nota_reparacion"]   # nota agregada, sin borrar
    assert "J2" not in escritas and not plan.conflictos              # el depósito final no se toca
    # Una vez agregada la nota, no se repite
    filas = [h.encabezados] + [list(x) for x in h.filas]
    filas[1][ENCABEZADOS.index("Notas")] = escritas["X2"]
    filas[1][ENCABEZADOS.index("Clasificacion")] = "B"
    segunda = dict(P.planificar(P.Hoja(filas), [d], hoy=HOY).celdas)
    assert "X2" not in segunda and "O2" not in segunda


def test_estado_final_gp_solo_agrega_nota():
    r = {"numero": "2000018604612862", "estados": ["Finalizado"], "reparado": "Si", "estado_final": "GP"}
    cambios = R.cambios_para_devolucion({"clasificacion": "Service"}, r)
    assert "clasificacion" not in cambios and "nota_reparacion" in cambios
    assert R.cambios_para_devolucion({}, {"numero": "1", "estados": ["Para reparar"]}) == {}
