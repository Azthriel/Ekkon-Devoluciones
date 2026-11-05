import datetime as dt
import io

from PIL import Image

from ekkon import settings
from ekkon.datos import armar_prompt, leer_respuesta_claude, validar_numero_venta
from ekkon.firebase import codificar, decodificar
from ekkon.fotos import comprimir
from ekkon.version import comparar


def test_ida_y_vuelta_firestore():
    ahora = dt.datetime(2026, 11, 3, 12, 30, tzinfo=dt.timezone.utc)
    valores = [None, True, 5, 2.5, "hola", b"\x00\x01", ahora, [1, "a"], {"x": {"y": 1}}]
    for v in valores:
        assert decodificar(codificar(v)) == v


def test_timestamp_con_nanosegundos():
    v = decodificar({"timestampValue": "2026-11-03T12:30:00.123456789Z"})
    assert v.year == 2026 and v.microsecond == 123456


def test_numero_venta():
    assert validar_numero_venta("2000 0123-4567 8901")[0] == "2000012345678901"
    n, err, aviso = validar_numero_venta("200001234567890")
    assert err is None and "15 dígitos" in aviso
    assert validar_numero_venta("")[1]
    assert validar_numero_venta("2000012345678901") == ("2000012345678901", None, None)


def test_respuesta_claude():
    texto = ("Mensaje: El producto volvió con la carcasa rayada y sin el cargador original.\n\n"
             "Porcentaje sugerido: 40%")
    mensaje, pct = leer_respuesta_claude(texto)
    assert pct == 40
    assert mensaje.startswith("El producto volvió")
    assert "%" not in mensaje


def test_prompt():
    p = armar_prompt({"numero_venta": "2000012345678901", "clasificacion": "B",
                      "descripcion": "Rayones"}, 3)
    assert "2000012345678901" in p and "Outlet" in p and "Fotos adjuntas: 3" in p


def test_compresion_entra_en_firestore():
    img = Image.effect_noise((4000, 3000), 120).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    data = comprimir(buf.getvalue())
    assert len(data) <= settings.FOTO_BYTES_MAXIMOS


def test_versiones():
    assert comparar("0.1.0", "0.2.0") == -1
    assert comparar("v1.0", "1.0.0") == 0
    assert comparar("1.10.0", "1.9.9") == 1


def test_guia_mercadolibre():
    from ekkon.datos import OPCION_OTRA_FALLA, guia_mercadolibre
    g = guia_mercadolibre({"reclamo": False})
    assert g["tipo"] == "sin_reclamo" and any("Llegó como esperaba" in p for p in g["pasos"])
    # El comprador dijo que no funciona y reclamamos por uso: "otra falla", no "llegó dañado"
    g = guia_mercadolibre({"reclamo": True, "motivo": "no funciona", "condicion": "Con uso",
                           "descripcion": "llegó usado, con aserrín"})
    assert g["opcion"] == OPCION_OTRA_FALLA and "NO elija" in g["nota"]
    g = guia_mercadolibre({"reclamo": True, "motivo": "no lo quiere", "condicion": "caja rota",
                           "descripcion": "caja rota"})
    assert g["opcion"] is None and any("consulte" in p for p in g["pasos"])


def test_importes_y_numeros_pegados():
    from ekkon.datos import importe, solo_digitos
    assert importe("$ 15.190,50") == 15190.50
    assert importe("15190,5") == 15190.5
    assert importe("81665.00") == 81665.0
    assert importe("15.190") == 15190.0
    assert importe("1.234.567") == 1234567.0
    assert importe("abc") is None
    assert solo_digitos(" 5562121277\n") == "5562121277"
