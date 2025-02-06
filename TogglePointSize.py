# -*- coding: utf-8 -*-

import FreeCAD
import FreeCADGui
from PySide import QtGui

doc = FreeCADGui.ActiveDocument
if doc is None:
    QtGui.QMessageBox.critical(None, "Error", "No active document found")
    raise RuntimeError("No active document found")

ps = 0
for obj in doc.TreeRootObjects:
    o = doc.getObject(obj.Name)
    if hasattr(o, 'PointSize'):
        ps = (9 if o.PointSize == 1 else 1) if ps == 0 else ps
        print(f"Setting PointSize of {obj.Name} to {ps}")
        o.PointSize = ps
