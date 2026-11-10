import 'package:flet/flet.dart';

import 'camara.dart';

CreateControlFactory createControl = (CreateControlArgs args) {
  switch (args.control.type) {
    case "ekkon_camara":
      return CamaraControl(
          parent: args.parent, control: args.control, backend: args.backend);
    default:
      return null;
  }
};

void ensureInitialized() {
  // nada que inicializar
}
