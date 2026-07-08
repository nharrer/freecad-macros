# -*- coding: utf-8 -*-

import FreeCAD
import FreeCADGui
from PySide import QtGui


def traverse_tree(obj, objects=[]):
    objects.append(obj)
    if hasattr(obj, "Group"):
        for child in obj.Group:
            traverse_tree(child, objects)
    return objects


if __name__ == "__main__":
    doc = FreeCADGui.ActiveDocument
    if doc is None:
        QtGui.QMessageBox.critical(None, "Error", "No active document found")
        raise RuntimeError("No active document found")

    objects = []
    for obj in doc.TreeRootObjects:
        if obj.getParent() is None:
            traverse_tree(obj, objects)

        print(f"{obj.Name} = {obj.Label}")

    ps = 0
    for obj in objects:
        o = doc.getObject(obj.Name)
        if hasattr(o, "PointSize"):
            new_point_size = 9 if o.PointSize == 1 else 1
            if ps == 0:
                ps = new_point_size
            print(f"Setting PointSize of {obj.Name} to {ps}")
            o.PointSize = ps
