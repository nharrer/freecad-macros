# -*- coding: utf-8 -*-

import os
import time

import debugpy
import FreeCAD
import FreeCADGui
import Mesh
import MeshPart
import MeshPartGui
import Part
import PartGui
from PySide import QtGui

widths = [15, 20, 30, 40]

exports = [
    {"object": "Cut001", "filename": "Tray{width}_Hex_Start.stl"},
    {"object": "Cut004", "filename": "Tray{width}_Hex_Middle.stl"},
    {"object": "Cut006", "filename": "Tray{width}_Hex_End.stl"},
    {"object": "Cut007", "filename": "Tray{width}_Hex_Single.stl"},
    {"object": "Cut", "filename": "Tray{width}_Solid_Start.stl"},
    {"object": "Cut003", "filename": "Tray{width}_Solid_Middle.stl"},
    {"object": "Cut005", "filename": "Tray{width}_Solid_End.stl"},
    {"object": "Link010", "filename": "Tray{width}_Solid_Single.stl"},
]

print("Starting STL export")

doc = FreeCAD.ActiveDocument

# get current width
var_set = doc.getObject("VarSet")
compWidth = var_set.Base_CompartmentWidth
current_width = compWidth.Value

for width in widths:
    if width != current_width:
        print(f"Setting compartment width to {width}")
        time.sleep(0.2)
        QtGui.QApplication.processEvents()
        var_set.Base_CompartmentWidth = width
        QtGui.QApplication.processEvents()
        doc.recompute()
        QtGui.QApplication.processEvents()
        current_width = width

    for export in exports:
        objectname = export.get("object")
        filename = export.get("filename")
        filename = filename.format(width=width)
        dir = os.path.dirname(doc.FileName)
        path = os.path.join(dir, filename)

        print(f"Exporting {objectname} to {os.path.basename(path)}")
        QtGui.QApplication.processEvents()

        mesh = doc.addObject("Mesh::Feature", "Mesh")
        part = doc.getObject(objectname)
        shape = Part.getShape(part, "")
        mesh.Mesh = MeshPart.meshFromShape(
            Shape=shape,
            LinearDeflection=0.01,
            AngularDeflection=0.0174533,
            Relative=False,
        )

        Mesh.export([mesh], path)
        doc.removeObject(mesh.Name)
        doc.recompute()

print("STL export Done")
