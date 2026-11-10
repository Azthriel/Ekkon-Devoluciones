# Ekkon Devoluciones

Programa de Windows para cargar y gestionar las devoluciones de Mercado Libre.

## Qué hace

- Inicio de sesión con Firebase y perfiles **Administrador** y **Carga**.
- Bloqueo de usuarios desde la sección *Usuarios* (o desde la consola de Firebase). Un usuario bloqueado
  queda afuera aunque tenga el programa abierto o una versión vieja: las reglas de Firestore le niegan los datos.
- Carga de devoluciones: número de venta (con control de dígitos y duplicados), vencimiento, clasificación,
  problema del comprador, estado del producto y fotos.
- **Armar reclamo**: copia los datos al portapapeles, abre el proyecto de Claude y la carpeta con las fotos.
  La respuesta se pega con *Pegar respuesta de Claude*, que separa el mensaje (máx. 320) del porcentaje.
- Listado, detalle con fotos, *Pendientes* y registro del resultado (cobertura, monto y N° de movimiento).
- Bloqueo de versiones viejas desde *Ajustes* (versión mínima permitida).
- **Planilla (0.2)**: *Sincronizar planilla* completa la planilla de Google Sheets con una cuenta de servicio.
  Solo completa celdas vacías y agrega ventas nuevas; nunca pisa lo escrito a mano (salvo *Pendiente* → resultado).
- **Informe de ventas (0.3)**: en *Ajustes* se importa el CSV "Ventas ML para APP" de Virtual Seller. Se guarda en
  Firestore repartido en 100 documentos (`ventas_idx`), se conservan 180 días. Con eso la carga convierte el ID Carrito
  en Venta #, muestra el producto y completa el SKU; y la sincronización completa fecha de compra, artículo, SKU,
  depósito de origen (Sucursal) y costo, y detecta filas con el ID Carrito en "N° Venta".
- **Detalle de la venta**: link automático al detalle de la venta en ML (usa el ID Carrito si la venta es parte de un carrito) y botón *Costo de envío* que se escribe en la planilla.
- **Cancelaciones (0.5)**: se cargan por Venta # o ID Carrito (datos del informe), con "lleva NC" sí/no. Vuelven como N, buena,
  sin reclamo, a Podestá, con Transferencia "A la espera de remito" hasta marcar el remito interno hecho ("Realizada").
  Arma la lista SKU | Producto | Cant. para el remito de Canva y el email con los pedidos para Carolina.
- **Reparaciones (0.6)**: perfil *Service* (carga devoluciones y reparaciones). Se busca el producto por N° de OS (informe
  "OS para APP" importado en *Ajustes*) o por Venta #. La app es la fuente de la planilla de Reparaciones; las reparaciones
  terminadas de devoluciones agregan una nota y cambian la clasificación (Outlet B→B, Outlet C→C, Scrap/Repuesto→Scrap).
- **Celular Android (0.7)**: `EkkonDevoluciones.apk` (mismo código, compilado con `flet build apk`). Pantallas adaptadas
  (barra de secciones abajo, listas en tarjetas), fotos desde la galería y "Armar reclamo" con la app de Claude.
  Planillas, emails, usuarios y ajustes quedan en la PC. El .apk se firma con `android/ekkon.jks` (siempre la misma
  clave, para que cada versión se instale encima de la anterior).
- **Importar de la planilla (0.8)**: en *Devoluciones* (administrador, PC) trae al programa las filas que están solo en la
  planilla (marcadas como importadas; para ellas manda la planilla). La columna opcional "N° Pedido" se completa con
  el informe de ventas.
- **Emails**: arma la solicitud de transferencia con las filas que tienen Transferencia = "A la espera de
  movimiento". Origen siempre Service Podestá (ahí entra la unidad al hacer la NC); destino según "Deposito final".
  Incluye *Abrir en Gmail* y *Marcar como enviado*.

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

## Probar en Linux (Ubuntu)

```bash
git clone https://github.com/Azthriel/Ekkon-Devoluciones.git && cd Ekkon-Devoluciones
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Si al abrir aparece un error de `libmpv.so.1`:
`sudo apt install libmpv2 && sudo ln -s /usr/lib/x86_64-linux-gnu/libmpv.so.2 /usr/lib/x86_64-linux-gnu/libmpv.so.1`

## Desarrollo

```bash
pip install -r requirements.txt
python main.py
python -m pytest tests
```
