# -*- coding: utf-8 -*-

import FreeCAD
import FreeCADGui
import Part

# Get the selected object
selection = FreeCADGui.Selection.getSelectionEx()

if selection:
    obj = selection[0]
    if obj.SubObjects and obj.SubObjects[0].ShapeType == "Edge":
        selected_edge = obj.SubObjects[0]
        print(f"Selected edge: {selected_edge}")

        # Get edge properties
        start_point = selected_edge.Vertexes[0].Point
        end_point = selected_edge.Vertexes[-1].Point
        length = selected_edge.Length

        # Get the direction vector
        direction = selected_edge.tangentAt(selected_edge.FirstParameter)

        # Normalize the direction vector
        direction.normalize()

        print(f"Start point: {start_point}")
        print(f"End point: {end_point}")
        print(f"Length: {length}")
        print(f"Edge direction vector: ({direction.x}, {direction.y}, {direction.z})")
    else:
        print("No edge selected. Please select an edge.")
else:
    print("Nothing selected. Please select an edge.")
