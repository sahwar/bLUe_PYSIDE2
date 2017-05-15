"""
This File is part of bLUe software.

Copyright (C) 2017  Bernard Virot <bernard.virot@libertysurf.fr>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as
published by the Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
Lesser General Lesser Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import sys

from PySide.QtCore import QRect, QBuffer, QDataStream, QIODevice
from PySide.QtGui import QApplication, QPainter, QWidget, QDockWidget
from PySide.QtGui import QGraphicsView, QGraphicsScene, QGraphicsPathItem, QPainterPath, QPainterPathStroker, QPen, \
    QBrush, QColor, QPixmap, QMainWindow, QLabel, QSizePolicy
from PySide.QtCore import Qt, QPoint, QPointF, QRectF
import numpy as np
from PySide.QtGui import QPolygonF
from PySide.QtGui import QPushButton

from colorModels import hueSatModel
from graphicsRGBLUT import cubicItem, activePoint
from spline import cubicSplineCurve
from utils import optionsWidget, channelValues, drawPlotGrid

strokeWidth = 3
controlPoints = []
computeControlPoints = True


class graphicsLabForm(QGraphicsView):
    @classmethod
    def getNewWindow(cls, cModel=None, targetImage=None, axeSize=500, layer=None, parent=None, mainForm=None):
        newWindow = graphicsLabForm(cModel=cModel, targetImage=targetImage, axeSize=axeSize, layer=layer, parent=parent, mainForm=mainForm)
        newWindow.setWindowTitle(layer.name)
        return newWindow

    def __init__(self, cModel=None, targetImage=None, axeSize=500, layer=None, parent=None, mainForm=None):
        super(graphicsLabForm, self).__init__(parent=parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMinimumSize(axeSize + 60, axeSize + 140)
        # self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        # self.setBackgroundBrush(QBrush(Qt.black, Qt.SolidPattern))
        # self.bgPixmap = QPixmap.fromImage(hueSatModel.colorWheel(size, size, cModel))
        self.graphicsScene = QGraphicsScene()
        self.setScene(self.graphicsScene)
        self.scene().targetImage = targetImage
        self.scene().layer = layer
        self.scene().bgColor = QColor(200, 200, 200)  # self.palette().color(self.backgroundRole()) TODO parametrize

        self.graphicsScene.onUpdateScene = lambda: 0

        self.graphicsScene.axeSize = axeSize
        self.mainForm=mainForm
        # axes and grid
        item = drawPlotGrid(axeSize)
        self.graphicsScene.addItem(item)

        # self.graphicsScene.addPath(qppath, QPen(Qt.DashLine))  #create and add QGraphicsPathItem

        # curves
        cubic = cubicItem(axeSize)
        self.graphicsScene.addItem(cubic)
        self.graphicsScene.cubicR = cubic
        cubic.channel = channelValues.L
        cubic.histImg = self.scene().layer.inputImgFull().histogram(size=self.scene().axeSize,
                                                                    bgColor=self.scene().bgColor, range=(0, 1),
                                                                    chans=channelValues.L, mode='Lab')
        cubic.initFixedPoints()
        cubic = cubicItem(self.graphicsScene.axeSize)
        self.graphicsScene.addItem(cubic)
        self.graphicsScene.cubicG = cubic
        cubic.channel = channelValues.a
        cubic.histImg = self.scene().layer.inputImgFull().histogram(size=self.scene().axeSize,
                                                                    bgColor=self.scene().bgColor, range=(-100, 100),
                                                                    chans=channelValues.a, mode='Lab')
        cubic.initFixedPoints()
        cubic = cubicItem(self.graphicsScene.axeSize)
        self.graphicsScene.addItem(cubic)
        self.graphicsScene.cubicB = cubic
        cubic.channel = channelValues.b
        cubic.histImg = self.scene().layer.inputImgFull().histogram(size=self.scene().axeSize,
                                                                    bgColor=self.scene().bgColor, range=(-100, 100),
                                                                    chans=channelValues.b, mode='Lab')
        cubic.initFixedPoints()
        # set current
        self.scene().cubicItem = self.graphicsScene.cubicR
        self.scene().cubicItem.setVisible(True)

        def onResetCurve():
            """
            Reset the selected curve
            """
            self.scene().cubicItem.reset()
            self.scene().onUpdateLUT()

        def onResetAllCurves():
            """
            Reset all curves
            """
            for cubicItem in [self.graphicsScene.cubicR, self.graphicsScene.cubicG, self.graphicsScene.cubicB]:
                cubicItem.reset()
            self.scene().onUpdateLUT()

        def updateStack():
            layer.applyToStack()
            targetImage.onImageChanged()

        # buttons
        pushButton1 = QPushButton("Reset Curve")
        pushButton1.setMinimumSize(1, 1)
        pushButton1.setGeometry(100, 20, 80, 30)  # x,y,w,h
        pushButton1.adjustSize()
        pushButton1.clicked.connect(onResetCurve)
        self.graphicsScene.addWidget(pushButton1)
        pushButton2 = QPushButton("Reset All")
        pushButton2.setMinimumSize(1, 1)
        pushButton2.setGeometry(100, 50, 80, 30)  # x,y,w,h
        pushButton2.adjustSize()
        pushButton2.clicked.connect(onResetAllCurves)
        self.graphicsScene.addWidget(pushButton2)
        pushButton3 = QPushButton("Update Top Layers")
        pushButton3.setObjectName("btn_reset_channel")
        pushButton3.setMinimumSize(1, 1)
        pushButton3.setGeometry(100, 80, 80, 30)  # x,y,w,h
        pushButton3.adjustSize()
        pushButton3.clicked.connect(updateStack)
        self.graphicsScene.addWidget(pushButton3)

        # options
        self.listWidget1 = optionsWidget(options=['L', 'a', 'b'], exclusive=True)
        self.listWidget1.select(self.listWidget1.items['L'])
        self.listWidget1.setGeometry(20, 20, 10, 80)
        self.graphicsScene.addWidget(self.listWidget1)

        def onSelect1(item):
            self.scene().cubicItem.setVisible(False)
            if item.isSelected():
                if item.text() == 'L':
                    self.scene().cubicItem = self.graphicsScene.cubicR
                elif item.text() == 'a':
                    self.scene().cubicItem = self.graphicsScene.cubicG
                elif item.text() == 'b':
                    self.scene().cubicItem = self.graphicsScene.cubicB

                self.scene().cubicItem.setVisible(True)
                # no need for update, but for color mode RGB.
                # self.scene().onUpdateLUT()

                # draw  histogram
                self.scene().invalidate(QRectF(0.0, -self.scene().axeSize, self.scene().axeSize, self.scene().axeSize),
                                        QGraphicsScene.BackgroundLayer)

        self.listWidget1.onSelect = onSelect1

    def showEvent(self, e):
        self.mainForm.tableView.setEnabled(False)

    def hideEvent(self, e):
        self.mainForm.tableView.setEnabled(True)

    def drawBackground(self, qp, qrF):
        s = self.graphicsScene.axeSize
        if self.scene().cubicItem.histImg is not None:
            qp.drawPixmap(QRect(0, -s, s, s), QPixmap.fromImage(self.scene().cubicItem.histImg))

    def writeToStream(self, outStream):
        layer = self.scene().layer
        outStream.writeQString(layer.actionName)
        outStream.writeQString(layer.name)
        if layer.actionName in ['actionBrightness_Contrast', 'actionCurves_HSpB', 'actionCurves_Lab']:
            outStream.writeQString(self.listWidget1.selectedItems()[0].text())
            self.graphicsScene.cubicR.writeToStream(outStream)
            self.graphicsScene.cubicG.writeToStream(outStream)
            self.graphicsScene.cubicB.writeToStream(outStream)
        return outStream

    def readFromStream(self, inStream):
        actionName = inStream.readQString()
        name = inStream.readQString()
        sel = inStream.readQString()
        cubics = []
        #for i in range(3):
            #cubic = cubicItem.readFromStream(inStream)
            #cubics.append(cubic)
        #kwargs = dict(zip(['cubicR', 'cubicG', 'cubicB'], cubics))
        #self.setEntries(sel=sel, **kwargs)
        self.graphicsScene.cubicR.readFromStream(inStream)
        self.graphicsScene.cubicG.readFromStream(inStream)
        self.graphicsScene.cubicB.readFromStream(inStream)
        return inStream

    #unused
    def setEntries(self, sel='', cubicR=None, cubicG=None, cubicB=None):
        listWidget = self.listWidget1
        self.graphicsScene.cubicR = cubicR
        self.graphicsScene.cubicG = cubicG
        self.graphicsScene.cubicB = cubicB
        for r in range(listWidget.count()):
            currentItem = listWidget.item(r)
            if currentItem.text() == sel:
                listWidget.select(currentItem)
        self.repaint()