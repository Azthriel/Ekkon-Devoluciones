import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';
import 'package:image_picker/image_picker.dart';

/// Control invisible: abre la cámara del celular y devuelve la ruta de la foto.
class CamaraControl extends StatefulWidget {
  final Control? parent;
  final Control control;
  final FletControlBackend backend;

  const CamaraControl(
      {super.key,
      required this.parent,
      required this.control,
      required this.backend});

  @override
  State<CamaraControl> createState() => _CamaraControlState();
}

class _CamaraControlState extends State<CamaraControl> {
  final ImagePicker _picker = ImagePicker();

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
          case "tomar_foto":
            try {
              final lado = double.tryParse(args["max"] ?? "") ?? 2000;
              final foto = await _picker.pickImage(
                  source: ImageSource.camera,
                  maxWidth: lado,
                  maxHeight: lado,
                  imageQuality: 85);
              return foto?.path ?? "";
            } catch (e) {
              return "ERROR: $e";
            }
        }
        return null;
      });
    }();
    return const SizedBox.shrink();
  }
}
