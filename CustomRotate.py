import math

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin
from PySide import QtGui

# In Preferences->Display->Navigation, you can set the number of steps per turn.
# However, this only affects clicking the rotate buttons on the navigation cube,
# and not Shift+Left/Right, which rotates in 90° steps. This macro overrides
# the keybindings to rotate in custom steps.

stepsByTurn = 16 # how many steps are needed to rotate 360°

def custRotateLeft():
    custRotate(1)

def custRotateRight():
    custRotate(-1)

def custRotate(dir):
    camOrientation = Gui.activeView().getViewer().getSoRenderManager().getCamera().orientation
    currRot = camOrientation.getValue()
    vertDir = coin.SbVec3f(0, 0, -1)
    vertDir = currRot.multVec(vertDir)
    newRot = coin.SbRotation(vertDir, dir * 2 * math.pi / stepsByTurn)
    camOrientation.setValue(currRot * newRot)

def run():
    Gui.getMainWindow().findChild(QtGui.QAction,'Std_ViewRotateLeft').triggered.disconnect()
    Gui.getMainWindow().findChild(QtGui.QAction,'Std_ViewRotateRight').triggered.disconnect()
    Gui.getMainWindow().findChild(QtGui.QAction,'Std_ViewRotateLeft').triggered.connect(custRotateLeft)
    Gui.getMainWindow().findChild(QtGui.QAction,'Std_ViewRotateRight').triggered.connect(custRotateRight)

if __name__ == '__main__':
    run()
