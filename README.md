# Ekkon Devoluciones

Programa de Windows para cargar y gestionar las devoluciones de Mercado Libre.

## Qué hace (versión 0.1)

- Inicio de sesión con Firebase y perfiles **Administrador** y **Carga**.
- Bloqueo de usuarios desde la sección *Usuarios* (o desde la consola de Firebase). Un usuario bloqueado
  queda afuera aunque tenga el programa abierto o una versión vieja: las reglas de Firestore le niegan los datos.
- Carga de devoluciones: número de venta (con control de dígitos y duplicados), vencimiento, clasificación,
  problema del comprador, estado del producto y fotos.
- **Armar reclamo**: copia los datos al portapapeles, abre el proyecto de Claude y la carpeta con las fotos.
  La respuesta se pega con *Pegar respuesta de Claude*, que separa el mensaje (máx. 320) del porcentaje.
- Listado, detalle con fotos, *Pendientes* y registro del resultado (cobertura, monto y N° de movimiento).
- Bloqueo de versiones viejas desde *Ajustes* (versión mínima permitida).

Todo funciona en el plan gratuito de Firebase (Spark): Auth + Firestore. Las fotos se comprimen
(≤ 850 KB) y se guardan dentro de Firestore, porque Cloud Storage exige el plan Blaze desde febrero de 2026.

## Descargar

Releases → `EkkonDevoluciones.exe`. Cada tag `vX.Y.Z` publica un release nuevo desde GitHub Actions.

## Configuración inicial de Firebase (una sola vez)

1. **Authentication** → Comenzar → habilitar *Correo electrónico/contraseña*.
2. **Firestore Database** → Crear base de datos (modo producción, región `southamerica-east1`).
3. **Firestore → Reglas**: pegar el contenido de `firestore.rules` y publicar.
4. **Authentication → Usuarios → Agregar usuario**: crear su propia cuenta.
5. **Firestore → Datos**: crear la colección `usuarios`, con ID de documento = UID de su cuenta, y los campos
   `activo` (boolean, true), `rol` (string, `admin`), `nombre` (string), `email` (string).
   Desde ahí, el resto de los usuarios se crea desde el programa.

## Desarrollo

```bash
pip install -r requirements.txt
python main.py
python -m pytest tests
```
