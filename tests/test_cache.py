import datetime as dt

from ekkon import cache as C, datos as D


class FS:
    def __init__(self):
        self.docs = {}
        self.consultas = []

    def consultar(self, coleccion, orden=(), filtros=(), limite=None):
        filtros = list(filtros)
        self.consultas.append(filtros)
        salida = list(self.docs.values())
        for campo, op, valor in filtros:
            assert op == "GREATER_THAN"
            salida = [d for d in salida if d.get(campo) and d[campo] > valor]
        return [dict(d) for d in salida]

    def actualizar(self, ruta, campos, debe_existir=True):
        doc_id = ruta.split("/")[-1]
        self.docs[doc_id].update(campos)
        return dict(self.docs[doc_id])


def _doc(n, minutos):
    t = dt.datetime(2026, 11, 12, 12, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=minutos)
    return {"_id": n, "numero_venta": n, "cargado_en": t, "actualizado_en": t}


def test_cache_lee_todo_una_vez_y_despues_solo_lo_que_cambio(tmp_path, monkeypatch):
    fs = FS()
    for i in range(5):
        fs.docs[str(i)] = _doc(str(i), i)
    archivo = tmp_path / "cache.json"
    devs = D.Devoluciones(fs, archivo)
    assert [d["_id"] for d in devs.todas()] == ["4", "3", "2", "1", "0"]
    assert fs.consultas == [[]] and archivo.exists()
    # Dentro de los 20 segundos no vuelve a consultar
    devs.todas()
    assert len(fs.consultas) == 1
    # Otro equipo agrega una: la próxima consulta pide solo las cambiadas desde la última (con margen)
    monkeypatch.setattr(C, "SIN_CONSULTAR", dt.timedelta(seconds=-1))
    fs.docs["9"] = _doc("9", 60)
    assert devs.todas()[0]["_id"] == "9"
    assert fs.consultas[-1][0][0] == "actualizado_en"
    # Al reabrir el programa usa el archivo: no vuelve a leer todo
    fs2_consultas = len(fs.consultas)
    devs2 = D.Devoluciones(fs, archivo)
    assert len(devs2.todas()) == 6 and len(fs.consultas) == fs2_consultas + 1
    assert fs.consultas[-1] != []
    # Lo que actualiza este equipo queda en la caché sin releer
    devs2.actualizar("0", {"estado": "cobertura"})
    assert next(d for d in devs2.todas() if d["_id"] == "0")["estado"] == "cobertura"


def test_csv_de_quien_cargo_cada_devolucion():
    t = lambda d: dt.datetime(2026, 11, d, 15, tzinfo=dt.timezone.utc)   # noqa: E731
    devs = [{"numero_venta": "1", "cargado_por": "alan@x.com", "cargado_en": t(3), "clasificacion": "N",
             "estado": "sin_reclamo"},
            {"numero_venta": "2", "cargado_por": "jose@x.com", "cargado_en": t(4), "tipo": "cancelacion"},
            {"numero_venta": "3", "cargado_por": "alan@x.com", "cargado_en": t(5)},
            {"numero_venta": "4", "cargado_por": "alan@x.com", "cargado_en": dt.datetime(2026, 10, 30, 15,
                                                                                         tzinfo=dt.timezone.utc)},
            {"numero_venta": "5", "cargado_por": "Planilla", "cargado_en": t(6)}]
    texto, totales = D.csv_por_usuario(devs, dt.date(2026, 11, 1), dt.date(2026, 11, 30),
                                       {"Alan@x.com": "Alan", "jose@x.com": "José"})
    assert totales == {"Alan": 2, "José": 1, "Planilla": 1}
    lineas = texto.strip().split("\r\n")
    assert lineas[0].startswith("Fecha de carga;Cargó;Venta #") and len(lineas) == 5
    assert lineas[1] == "03/11/2026;Alan;1;Devolución;N;;;;;Sin reclamo"
    assert ";José;2;Cancelación;" in lineas[2]
