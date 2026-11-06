from ekkon import planilla as P
from ekkon import settings
from ekkon.datos import email_cancelaciones, lista_remito
from test_planilla import ENCABEZADOS, HOY, dev


def cancelacion(venta, lleva_nc=True, **kw):
    d = dev(venta, tipo="cancelacion", estado="cancelacion", clasificacion="N", condicion="buena",
            motivo="cancelado", reclamo=False, lleva_nc=lleva_nc, nc_realizada=False, deposito_final="Podestá",
            transferencia=settings.TRANSF_ESPERA_REMITO)
    d.update(kw)
    return d


def test_cancelacion_en_la_planilla():
    h = P.Hoja([ENCABEZADOS])
    plan = P.planificar(h, [cancelacion("2000000000000001"), cancelacion("2000000000000002", lleva_nc=False)],
                        hoy=HOY)
    a, b = (dict(zip(ENCABEZADOS, f)) for _, f in plan.filas_nuevas)
    assert a["NdC"] == "Si" and b["NdC"] == "No"
    for f in (a, b):
        assert f["Transferencia"] == "A la espera de remito" and f["Deposito final"] == "Podestá"
        assert (f["Motivo"], f["Condicion"], f["Clasificacion"], f["Reclamo"]) == ("cancelado", "buena", "N", "no")


def test_remito_hecho_pasa_a_realizada():
    filas = [ENCABEZADOS, [None] * len(ENCABEZADOS)]
    filas[1][ENCABEZADOS.index("N° Venta")] = "2000000000000001"
    filas[1][ENCABEZADOS.index("Transferencia")] = "A la espera de remito"
    filas[1][ENCABEZADOS.index("NdC")] = "Si"
    d = cancelacion("2000000000000001", remito_hecho=True, transferencia="Realizada")
    assert dict(P.planificar(P.Hoja(filas), [d], hoy=HOY).celdas)["I2"] == "Realizada"


def test_lista_remito_y_email():
    cs = [{"numero_venta": "1", "codigo_producto": "RLA-0045", "producto": "ASPIRADORA (KB-VC60LG)", "pedido": "PED-1"},
          {"numero_venta": "2", "codigo_producto": "FN1-0049", "producto": "PULVERIZADOR (KB-PVC10)", "pedido": "PED-2"},
          {"numero_venta": "3", "codigo_producto": "FN1-0049", "producto": "PULVERIZADOR (KB-PVC10)", "pedido": "PED-2"},
          {"numero_venta": "4", "codigo_producto": "X-1", "producto": "OTRO", "pedido": ""}]
    assert lista_remito(cs) == ("SKU | Producto | Cant.\nRLA-0045 | KB-VC60LG | 1\nFN1-0049 | KB-PVC10 | 2\n"
                                "X-1 | OTRO | 1")
    asunto, cuerpo = email_cancelaciones(cs)
    assert asunto == "Devoluciones Procourrier"
    assert cuerpo.splitlines()[:4] == [settings.EMAIL_CANCELACIONES_INTRO, "PED-1", "PED-2",
                                       "(sin pedido — venta 4)"]


def test_que_necesita_nc():
    assert settings.necesita_nc({"tipo": None})
    assert settings.necesita_nc({"tipo": "cancelacion", "lleva_nc": True})
    assert not settings.necesita_nc({"tipo": "cancelacion", "lleva_nc": False})
