# -*- coding: utf-8 -*-

import os

import FreeCAD
import FreeCADGui
import Mesh
import MeshPart
import Part
from PySide import QtGui

export_settings = [
    ["High", (0.01, 0.1)],
    ["Med", (0.05, 0.3)],
    ["Low", (0.05, 1)],
]

def export():
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("No active document found")

    selection = FreeCADGui.Selection.getSelection()
    if not selection:
        raise RuntimeError("No object selected")

    msgb = QtGui.QMessageBox()
    msgb.setWindowTitle("Export STL: Select Quality")
    text = "\n".join([f"{name}\t=>  Surface deviation: {linear_deflection}mm ,Angular deviation: {angular_deflection}°" for name, (linear_deflection, angular_deflection) in export_settings])
    msgb.setText(text)
    msgb.setIcon(QtGui.QMessageBox.Question)
    for name, _ in export_settings:
        msgb.addButton(name, QtGui.QMessageBox.AcceptRole)
    msgb.addButton("Cancel", QtGui.QMessageBox.RejectRole)
    msgb.exec_()

    msgbRep = msgb.clickedButton()
    (ld, ad) = (0, 0)
    for name, (linear_deflection, angular_deflection) in export_settings:
        if msgbRep.text() == name:
            ld = linear_deflection
            ad = angular_deflection / 180 * 3.14159265359
            break
    if ld == 0:
        return
    print(f"Linear Deflection: {ld}, Angular Deflection: {ad}")

    object = selection[0]

    dir = os.path.dirname(doc.FileName)
    path = os.path.join(dir, object.Label + ".stl")
    msg = f"{object.Label} ({object.Name}) to {os.path.basename(path)}"
    print("Exporting " + msg)

    mesh = doc.addObject("Mesh::Feature","Mesh")
    part = object
    shape = Part.getShape(part,"")
    mesh.Mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=ld, AngularDeflection=ad, Relative=False)
    mesh.Label = object.Label + " (Meshed)"

    Mesh.export([mesh], path)
    doc.removeObject(mesh.Name)
    doc.recompute()

    QtGui.QMessageBox.information(None, "Success", "Exported " + msg)

if __name__ == "__main__":
    try:
        export()
    except Exception as e:
        QtGui.QMessageBox.critical(None, "Error", str(e))
