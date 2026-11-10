#!/bin/bash
# Prueba del .apk en el emulador: abre la app, intenta un login inválido y deja capturas en el log (base64).
set -x
PAQ=com.ekkon.ekkondevoluciones
adb install -r build/apk/app-release.apk || exit 1
adb logcat -c
adb shell monkey -p $PAQ -c android.intent.category.LAUNCHER 1
sleep 60
captura() {
  adb exec-out screencap -p > "$1.png"
  python3 -c "
from PIL import Image; import base64, io, sys
im = Image.open('$1.png').convert('RGB'); im.thumbnail((360, 800))
b = io.BytesIO(); im.save(b, 'JPEG', quality=70)
print('CAPTURA_$1_INICIO'); print(base64.b64encode(b.getvalue()).decode()); print('CAPTURA_$1_FIN')"
}
captura login
adb shell input text "prueba@ekkon.test"
adb shell input keyevent 66
sleep 2
adb shell input text "x1234567"
adb shell input keyevent 66
sleep 15
captura error
echo "LOGCAT_INICIO"
adb logcat -d | grep -iE "python|flet|flutter|serious|Traceback|EKKON|AndroidRuntime|FATAL" | tail -300
echo "LOGCAT_FIN"
pidof_app=$(adb shell pidof $PAQ)
echo "PID_APP=$pidof_app"
[ -n "$pidof_app" ]
