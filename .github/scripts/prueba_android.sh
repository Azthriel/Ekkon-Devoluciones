#!/bin/bash
# Prueba del .apk en el emulador: abre la app (versión de prueba con la pantalla "PROBAR CAMARA"),
# saca una foto con la cámara emulada y deja capturas en el log (base64).
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
captura inicio
adb shell input tap 540 900
sleep 12
captura camara
# Diálogos de la app de cámara la primera vez (ubicación, etc.): se aceptan con Enter/tab
adb shell input keyevent 27
sleep 6
captura disparo
adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 && adb shell cat /sdcard/ui.xml | tr '>' '>\n' | grep -oE 'resource-id="[^"]*"|content-desc="[^"]*"|text="[^"]+"|bounds="[^"]*"' | head -80
# Botón de confirmar de la cámara (Camera2: done_button / shutter)
for id in com.android.camera2:id/done_button com.android.camera:id/btn_done com.android.camera2:id/shutter_button; do
  b=$(adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; adb shell cat /sdcard/ui.xml | grep -oE "resource-id=\"$id\"[^>]*bounds=\"\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]\"" | grep -oE '\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]' | head -1)
  if [ -n "$b" ]; then
    read x1 y1 x2 y2 <<<$(echo $b | tr '[],' '   ')
    adb shell input tap $(( (x1+x2)/2 )) $(( (y1+y2)/2 ))
    sleep 6
    captura "tap_${id##*/}"
  fi
done
sleep 5
captura final
echo "LOGCAT_INICIO"
adb logcat -d | grep -iE "python|flet|flutter|image_picker|Traceback|EKKON|AndroidRuntime|FATAL" | tail -150
echo "LOGCAT_FIN"
pidof_app=$(adb shell pidof $PAQ)
echo "PID_APP=$pidof_app"
[ -n "$pidof_app" ]
