import datetime as dt

from ekkon import datos as D


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
    monkeypatch.setattr(D, "SIN_CONSULTAR", dt.timedelta(seconds=-1))
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
