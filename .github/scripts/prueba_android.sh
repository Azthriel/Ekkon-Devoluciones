#!/bin/bash
# Prueba del .apk en el emulador (versión de prueba con la pantalla de cámara y escáner).
# Deja capturas en el log (base64) y el resultado de cada prueba.
set -x
PAQ=com.ekkon.ekkondevoluciones
adb install -r build/apk/app-release.apk || exit 1
adb logcat -c
adb shell monkey -p $PAQ -c android.intent.category.LAUNCHER 1
sleep 60
captura() {
  adb exec-out screencap -p > "$1.png"
  python3 -c "
from PIL import Image; import base64, io
im = Image.open('$1.png').convert('RGB'); im.thumbnail((360, 800))
b = io.BytesIO(); im.save(b, 'JPEG', quality=70)
print('CAPTURA_$1_INICIO'); print(base64.b64encode(b.getvalue()).decode()); print('CAPTURA_$1_FIN')"
}
# Toca el elemento con ese resource-id o texto, si está en pantalla
tocar() {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  b=$(adb shell cat /sdcard/ui.xml | grep -oE "(resource-id=\"$1\"|text=\"$1\")[^>]*bounds=\"\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]\"" \
      | grep -oE '\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]' | head -1)
  if [ -n "$b" ]; then
    read x1 y1 x2 y2 <<<$(echo $b | tr '[],' '   ')
    adb shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 ))
    return 0
  fi
  return 1
}
permiso() {
  tocar "com.android.permissioncontroller:id/permission_allow_foreground_only_button" \
    || tocar "com.android.permissioncontroller:id/permission_allow_button" || true
}
captura inicio

# 1) Cámara para fotos (image_picker)
adb shell input tap 540 380
sleep 8
permiso
sleep 6
captura camara
adb shell input keyevent 27
sleep 6
for id in com.android.camera2:id/done_button com.android.camera:id/btn_done; do tocar "$id" && break; done
sleep 8
captura foto

# 2) Lectura de un código de barras generado (mobile_scanner.analyzeImage)
adb shell input tap 540 1320
sleep 15
captura lectura

# 3) Escáner en vivo: abre la cámara (pide permiso si hace falta) y se cierra con "atrás"
adb shell input tap 540 1950
sleep 8
permiso
sleep 8
captura escaner
adb shell input keyevent 4
sleep 6
captura final

echo "LOGCAT_INICIO"
adb logcat -d | grep -iE "python|flet|flutter|image_picker|mobile_scanner|mlkit|Traceback|EKKON|AndroidRuntime|FATAL" | tail -150
echo "LOGCAT_FIN"
pidof_app=$(adb shell pidof $PAQ)
echo "PID_APP=$pidof_app"
[ -n "$pidof_app" ]
