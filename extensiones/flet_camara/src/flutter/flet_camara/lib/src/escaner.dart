import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Control invisible: abre una pantalla con la cámara que lee códigos de barras y devuelve el primero que ve.
class EscanerControl extends StatefulWidget {
  final Control? parent;
  final Control control;
  final FletControlBackend backend;

  const EscanerControl(
      {super.key,
      required this.parent,
      required this.control,
      required this.backend});

  @override
  State<EscanerControl> createState() => _EscanerControlState();
}

class _EscanerControlState extends State<EscanerControl> {
  @override
  void initState() {
    super.initState();
    widget.control.onRemove.clear();
    widget.control.onRemove.add(_onRemove);
  }

  void _onRemove() {
    widget.backend.unsubscribeMethods(widget.control.id);
  }

  @override
  Widget build(BuildContext context) {
    () async {
      widget.backend.subscribeMethods(widget.control.id,
          (methodName, args) async {
        switch (methodName) {
          case "escanear":
            try {
              final codigo = await Navigator.of(context, rootNavigator: true)
                  .push<String>(MaterialPageRoute(
                      builder: (_) => const PantallaEscaner(),
                      fullscreenDialog: true));
              return codigo ?? "";
            } catch (e) {
              return "ERROR: $e";
            }
          case "analizar":
            // Lee el código de barras de una imagen (sirve para la prueba automática)
            final controller = MobileScannerController(autoStart: false);
            try {
              final captura = await controller.analyzeImage(args["ruta"] ?? "");
              final codigos = captura?.barcodes ?? [];
              return codigos.isEmpty ? "" : (codigos.first.rawValue ?? "");
            } catch (e) {
              return "ERROR: $e";
            } finally {
              await controller.dispose();
            }
        }
        return null;
      });
    }();
    return const SizedBox.shrink();
  }
}

class PantallaEscaner extends StatefulWidget {
  const PantallaEscaner({super.key});

  @override
  State<PantallaEscaner> createState() => _PantallaEscanerState();
}

class _PantallaEscanerState extends State<PantallaEscaner> {
  final MobileScannerController _controller = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      formats: const [
        BarcodeFormat.code128,
        BarcodeFormat.code39,
        BarcodeFormat.itf,
        BarcodeFormat.ean13,
        BarcodeFormat.qrCode,
        BarcodeFormat.dataMatrix
      ]);
  bool _listo = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text("Escanear etiqueta"),
        actions: [
          IconButton(
              icon: const Icon(Icons.flashlight_on),
              tooltip: "Linterna",
              onPressed: () => _controller.toggleTorch()),
        ],
      ),
      body: Stack(children: [
        MobileScanner(
          controller: _controller,
          onDetect: (captura) {
            if (_listo) return;
            for (final b in captura.barcodes) {
              final v = b.rawValue;
              if (v != null && v.trim().isNotEmpty) {
                _listo = true;
                Navigator.of(context).pop(v.trim());
                return;
              }
            }
          },
        ),
        Center(
          child: Container(
            width: 300,
            height: 150,
            decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 3),
                borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: EdgeInsets.all(28),
            child: Text("Apunte al código de barras de la etiqueta",
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    backgroundColor: Colors.black54)),
          ),
        ),
      ]),
    );
  }
}
