VERSION = "0.4.0"


def comparar(a: str, b: str) -> int:
    """Devuelve -1, 0 o 1 comparando versiones tipo 1.2.3."""
    def partes(v):
        return [int(x) for x in (v or "0").strip().lstrip("v").split(".") if x.isdigit()]
    pa, pb = partes(a), partes(b)
    largo = max(len(pa), len(pb))
    pa += [0] * (largo - len(pa))
    pb += [0] * (largo - len(pb))
    return (pa > pb) - (pa < pb)
