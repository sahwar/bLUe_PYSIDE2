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
import ctypes
import threading
from os.path import isfile, basename
from itertools import product

import cv2
import numpy as np

from PySide2 import QtCore
from PySide2.QtGui import QColor, QImage, QPainter, QPixmap, QIcon, QFont
from PySide2.QtWidgets import QListWidget, QListWidgetItem, \
    QSlider, QLabel, QDockWidget, QStyle, QColorDialog, QPushButton
from PySide2.QtCore import Qt, QObject, QRect

from bLUeCore.rollingStats import movingVariance
from bLUeGui.bLUeImage import QImageBuffer
from bLUeGui.baseSignal import baseSignal_No


def qColorToRGB(color):
    """
    Converts a QColor to its R,G,B components (range 0..255)
    @param color:
    @type color: QColor
    @return:
    @rtype: 3-uple of int
    """
    return color.red(), color.green(), color.blue()

def qColorToCMYK(color):
    """
    Converts a QColor to its C, M, Y, K components (range 0..255)
    @param color:
    @type color: QColor
    @return:
    @rtype: 4-uple of int
    """
    return color.cyan(), color.magenta(), color.yellow(), color.black()

def qColorToHSV(color):
    """
    Converts a QColor to its H,S,V components
    @param color:
    @type color: QColor
    @return:
    @rtype: 3-uple of int
    """
    return color.hue(), color.saturation(), color.value()


class colorInfoView(QDockWidget):
    """
    Display formatted color info for a pixel
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.label = QLabel()
        self.label.setWindowTitle('Info')
        self.setWidget(self.label)
        self.setWindowTitle(self.label.windowTitle())
        self.setFocusPolicy(Qt.ClickFocus)
        self.label.setStyleSheet("font-family: 'courier'; font-size: 8pt")
        self.label.setWhatsThis(
"""<b>ActiveLayer input/output</b><br>
For each color space (RGB, CMYK, HSV) input values are displayed in the left column
and output values in the right column.<br>
"""
                        )  # end of setWhatsThis

    def setText(self, clrI, clrC):
        """
        Set widget text to formatted color info
        @param clrI: input color
        @type clrI: QColor
        @param clrC: output color
        @type clrC: QColor
        """
        r0 = 'R ' + "".join([str(w).ljust(4) if type(w) is int else w
                             for w in (clrI.red(), clrC.red(), 'C ', clrI.cyan() * 100 // 255,
                                       clrC.cyan() * 100 // 255, 'H ', clrI.hue(), clrC.hue())])
        r1 = 'G ' + "".join([str(w).ljust(4) if type(w) is int else w
                             for w in (clrI.green(), clrC.green(), 'M ',
                                       clrI.magenta() * 100 // 255, clrC.magenta() * 100 // 255, 'S ',
                                       clrI.saturation() * 100 // 255, clrC.saturation() * 100 // 255)])
        r2 = 'B ' + "".join([str(w).ljust(4) if type(w) is int else w
                             for w in (clrI.blue(), clrC.blue(), 'Y ',
                                       clrI.yellow() * 100 // 255, clrC.yellow() * 100 // 255, 'V ',
                                       clrI.value() * 100 // 255, clrC.value() * 100 // 255)])
        r3 = "".join((' ',) * 10)  + 'K ' + "".join([str(w).ljust(4) for w in
                                                     (clrI.black() * 100 // 255, clrC.black() * 100 // 255)])
        self.label.setText('\n'.join((r0, r1, r2, r3)))

def hideConsole():
    """
    Hides the console window
    """
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)
        ctypes.windll.kernel32.CloseHandle(whnd)

def showConsole():
    """
    Shows the console window
    """
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 1)
        ctypes.windll.kernel32.CloseHandle(whnd)

def multiply(matr_a, matr_b):
    """Return product of an MxP matrix A with an PxN matrix B."""
    cols, rows = len(matr_b[0]), len(matr_b)
    resRows = range(len(matr_a))
    rMatrix = [[0] * cols for _ in resRows]
    for idx in resRows:
        for j, k in product(range(cols), range(rows)):
            rMatrix[idx][j] += matr_a[idx][k] * matr_b[k][j]
    return rMatrix

def inversion(m):
    """
    @param m:
    @type m:
    @return:
    @rtype:
    """
    m1, m2, m3, m4, m5, m6, m7, m8, m9 = m.ravel()
    inv = np.array([[m5 * m9 - m6 * m8, m3 * m8 - m2 * m9, m2 * m6 - m3 * m5],
                    [m6 * m7 - m4 * m9, m1 * m9 - m3 * m7, m3 * m4 - m1 * m6],
                    [m4 * m8 - m5 * m7, m2 * m7 - m1 * m8, m1 * m5 - m2 * m4]])
    return inv / multiply(inv[0], m[:, 0])

class UDict(object):
    """
    Union of dictionaries. The dictionaries are neither copied nor changed.
    """
    def __init__(self, *args):
        """
        If args is a tuple of dict instances, build an (ordered) union
        of the dictionaries : __getitem__(key) returns the first found
        value corresponding to the key, and None if the key is not present
        in any of the dictionaries. No exception is raised if the key does not
        exist.
        @param args: empty or sequence of dict
        @type args:
        """
        if args:
            self.__dictionaries = tuple(args[0])
        else:
            self.__dictionaries = ()

    def __getitem__(self, item):
        for i in range(len(self.__dictionaries)):
            if item in self.__dictionaries[i]:
                return self.__dictionaries[i][item]
        return None


class QbLUeColorDialog(QColorDialog):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.closeSignal = baseSignal_No()

    def closeEvent(self, e):
        self.closeSignal.sig.emit()

class QbLUeSlider(QSlider):
    """
    Enhanced QSlider.
    Override mousepressevent to prevent jumps
    when clicking the handle and to update value
    with a single jump when clicking on the groove.
    """
    bLueSliderDefaultColorStylesheet = """QSlider::groove:horizontal:enabled { 
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 blue, stop:1 red);
                                                                        }
                                          QSlider::groove:horizontal:disabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8888FF, stop:1 #FF8888);
                                                                        }"""
    bLueSliderDefaultMGColorStylesheet = """QSlider::groove:horizontal:enabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 magenta, stop:1 green);
                                                                        }
                                            QSlider::groove:horizontal:disabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8888FF, stop:1 #FF8888);
                                                                        }"""
    bLueSliderDefaultIMGColorStylesheet = """QSlider::groove:horizontal:enabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 green, stop:1 magenta);
                                                                        }
                                             QSlider::groove:horizontal:disabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8888FF, stop:1 #FF8888);
                                                                        }"""
    bLueSliderDefaultIColorStylesheet = """QSlider::groove:horizontal:enabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 red, stop:1 blue);
                                                                        }
                                            QSlider::groove:horizontal:disabled { 
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8888FF, stop:1 #FF8888);
                                                                        }"""
    bLueSliderDefaultBWStylesheet = """QSlider::groove:horizontal:enabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #333333, stop:1 white);
                                                                        }
                                       QSlider::groove:horizontal:disabled {
                                                                        background: #888888;
                                                                        }"""
    bLueSliderDefaultIBWStylesheet = """QSlider::groove:horizontal:enabled {
                                                                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 gray, stop:1 #333333);
                                                                        }
                                        QSlider::groove:horizontal:disabled {
                                                                        background: #888888;
                                                                        }"""

    def __init__(self, *args, **kwargs):
        super(QbLUeSlider, self).__init__(*args, **kwargs)
        self.setTickPosition(QSlider.NoTicks)
        self.setMaximumSize(16777215, 10)

    def mousePressEvent(self, event):
        """
        Update the slider value with a single jump when clicking on the groove.

        @param event:
        @type event:
        """
        pressVal = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), event.x(), self.width(), 0)  # 0 is for horizontal slider only
        if abs(pressVal - self.value()) > (self.maximum() - self.minimum()) * 20 / self.width():  # handle width should be near 20
            self.setValue(pressVal)
        else:
            super().mousePressEvent(event)


class QbLUeLabel(QLabel):
    """
    Emits a signal when double clicked
    """
    doubleClicked = QtCore.Signal()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()

class QbLUePushButton(QPushButton):
    """
    Form PushButtons (specific style sheet)
    """
    pass

class historyList(list):
    """
    History management.
    Implements undo/redo methods.
    """

    def __init__(self, size=5):
       """
       The attribute self.current indicates the
       index of the last restored item, -1 if no
       restoration was done since the last saving:
       next item to restore has always index self.current+1
       @param size: max history size
       @type size: int
       """
       self.size= size
       self.current = -1

    def addItem(self, item):
        super().insert(0, item)
        if len(self) > self.size:
            self.pop()
        # next item to save has index 0.
        self.current = -1

    def undo(self, saveitem=None):
        """
        Return the next item in history.
        Parameter saveitem should be the old value
        (before restoration) of the variable to restore.
        IL is saved to history if it not already a  restored state
        (i.e. if self.current == -1).
        @param saveitem: item possibly to save, depending on history state
        @type saveitem: object
        @return:
        @rtype: object
        """
        if (self.current >= len(self) - 1):
            # no more items to restore
            return None
        # stack a possibly unsaved (i.e. not restored) item
        if (self.current == -1) and (saveitem is not None):
            self.addItem(saveitem)
            self.current = 0
        self.current += 1
        item = self[self.current]
        return item

    def redo(self):
        if self.current <= 0:
            return None
        self.current -= 1
        return self[self.current]

    def canUndo(self):
        return self.current < len(self) - 1

    def canRedo(self):
        return self.current > 0

class optionsWidgetItem(QListWidgetItem):
    def __init__(self, *args, intName='',**kwargs, ):
        super().__init__(*args, **kwargs)
        self._internalName = intName

    @property
    def internalName(self):
        return self._internalName

    def setInternalName(self, name):
        self._internalName = name

    def isChecked(self):
        return self.checkState() == Qt.CheckState.Checked

class optionsWidget(QListWidget) :
    """
    Displays a list of options with checkboxes.
    The choices can be mutually exclusive (default) or not
    exclusive. Actions can be done on item selection by assigning
    a function to onSelect. It is called after the selection of the new item.
    if changed is not None, it is called when an item is clicked.
    """

    def __init__(self, options=None, optionNames=None, exclusive=True, changed=None, parent=None):
        """
        @param options: list of options
        @type options: list of str
        @param optionNames: list of displayed names corresponding to options
        @type optionNames: list of str
        @param exclusive:
        @type exclusive: bool
        @param changed: SLOT for itemclicked signal
        @type changed: function
        @param parent:
        @type parent: QObject
        """
        super().__init__(parent)
        if options is None:
            options = []
        if optionNames is None:
            self.extNames = options
        else:
            self.extNames = optionNames
        self.intNames = options
        # dict of items with option internal name as keys
        self.items = {}
        # dict of item states (True, False) with option internal name as key
        self.options = {}
        for intName, name in zip(self.intNames, self.extNames):
            listItem = optionsWidgetItem(name, self, intName=intName)
            listItem.setCheckState(Qt.Unchecked)
            self.addItem(listItem)
            self.items[intName] = listItem
            self.options[intName] = (listItem.checkState() == Qt.Checked)
        #self.setMinimumWidth(self.sizeHintForColumn(0)) # TODO 18/04/18 validate suppression to improve graphicsLUT3D
        self.setMinimumHeight(self.sizeHintForRow(0)*len(options))
        self.setMaximumHeight(self.sizeHintForRow(0) * len(options) + 10) # TODO added 14/09/18 to improve the aspect of all graphic forms. Validate
        self.exclusive = exclusive
        self.itemClicked.connect(self.select)
        if changed is not None:
            self.itemClicked.connect(changed)
        # selection hook.
        self.onSelect = lambda x : 0

    def select(self, item, callOnSelect=True):
        """
        Item clicked event handler. It updates the states of the items and
        the dict of options. Next, if callOnSelect is True, onSelect is called.
        @param item:
        @type item: QListWidgetItem
        @param callOnSelect:
        @type callOnSelect: bool
        """
        # Update item states:
        # if exclusive, clicking on an item should turn it
        # into (or keep it) checked. Otherwise, there is nothing to do
        # since select is called after the item state has changed.
        if self.exclusive:
            for r in range(self.count()):
                currentItem = self.item(r)
                if currentItem is not item:
                    currentItem.setCheckState(Qt.Unchecked)
                else:
                    currentItem.setCheckState(Qt.Checked)
        # update options dict
        for option in self.options.keys():
            self.options[option] = (self.items[option].checkState() == Qt.Checked)
        if callOnSelect:
            self.onSelect(item)

    def checkOption(self, name, checked=True, callOnSelect=True):
        """
        Check or (for non exclusive options only) uncheck an item.
        Next, if callOnSelect is True, onSelect is called.
        A ValueError exception is raised  if an attempt is done to
        uncheck an item in a list of mutually exclusive options.
        @param name: internal name of option
        @type name: str
        @param checked: check/uncheck flag
        @type checked: bool
        @param callOnSelect:
        @type callOnSelect: bool
        """
        item = self.items[name]
        if not checked and self.exclusive:
            raise ValueError('For mutually exclusive options, unchecking is not possible. Please, check another item')
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.select(item, callOnSelect=callOnSelect)

    def unCheckAll(self):
        if self.exclusive:
            return
        for r in range(self.count()):
            self.item(r).setCheckState(Qt.Unchecked)

def checkeredImage(format=QImage.Format_ARGB32):
    """
    Returns a 20x20 checker
    @param format:
    @type format:
    @return: checker
    @rtype: QImage
    """
    base = QImage(20, 20, format)
    qp = QPainter(base)
    qp.setCompositionMode(QPainter.CompositionMode_Source)
    qp.fillRect(0, 0, 10, 10, Qt.gray)
    qp.fillRect(10, 0, 10, 10, Qt.white)
    qp.fillRect(0, 10, 10, 10, Qt.white)
    qp.fillRect(10, 10, 10, 10, Qt.gray)
    qp.end()
    return base
    """
    qp=QPainter(image)
    qp.setCompositionMode(QPainter.CompositionMode_Source)
    # draw the pattern once at 0,0
    qp.drawImage(0, 0, base)
    imageW, imageH = image.width(), image.height()
    baseW, baseH = base.width(), base.height()
    while ((baseW < imageW) or (baseH < imageH) ):
        if (baseW < imageW) :
            # Copy and draw the existing pattern to the right
            qp.drawImage(QRect(baseW, 0, baseW, baseH), image, QRect(0, 0, baseW, baseH))
            baseW *= 2
        if (baseH < imageH) :
            # Copy and draw the existing pattern to the bottom
            qp.drawImage(QRect(0, baseH, baseW, baseH), image, QRect(0, 0, baseW, baseH))
            # Update height of our pattern
            baseH *= 2
    qp.end()
    return image
    """

class stateAwareQDockWidget(QDockWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._closed = False
    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)
    @property
    def isClosed(self):
        return self._closed

class loader(threading.Thread):
    """
    Thread class for batch loading of images in a
    QListWidget object
    """
    def __init__(self, gen, wdg):
        """

        @param gen: generator of image file names
        @type gen: generator
        @param wdg:
        @type wdg: QListWidget
        """
        super(loader, self).__init__()
        self.fileListGen = gen
        self.wdg = wdg
    def run(self):
        # next() raises a StopIteration exception when the generator ends.
        # If this exception is unhandled by run(), it causes thread termination.
        # If wdg internal C++ object was destroyed by main thread (form closing)
        # a RuntimeError exception is raised and causes thread termination too.
        # Thus, no further synchronization is needed.
        import exiftool
        with exiftool.ExifTool() as e:
            while True:
                try:
                    filename = next(self.fileListGen)
                    # get orientation
                    try:
                        # read metadata from sidecar (.mie) if it exists, otherwise from image file.
                        profile, metadata = e.get_metadata(filename, tags=("colorspace", "profileDescription", "orientation", "model", "rating", "FileCreateDate"),
                                                           createsidecar=False)
                    except ValueError:
                        metadata = {}
                    # get image info
                    tmp = [value for key, value in metadata.items() if 'orientation' in key.lower()]
                    orientation = tmp[0] if tmp else 1  # metadata.get("EXIF:Orientation", 1)
                    # EXIF:DateTimeOriginal seems to be missing in many files
                    tmp = [value for key, value in metadata.items() if 'date' in key.lower()]
                    date = tmp[0] if tmp else ''  # metadata.get("EXIF:ModifyDate", '')
                    tmp = [value for key, value in metadata.items() if 'rating' in key.lower()]
                    rating = tmp[0] if tmp else 0  # metadata.get("XMP:Rating", 5)
                    rating = ''.join(['*']*int(rating))
                    transformation = exiftool.decodeExifOrientation(orientation)
                    # get thumbnail
                    img = e.get_thumbNail(filename, thumbname='thumbnailimage')
                    # no thumbnail found : try preview
                    if img.isNull():
                        img = e.get_thumbNail(filename, thumbname='PreviewImage')  # the order is important : for jpeg PreviewImage is full sized !
                    # all failed : open image
                    if img.isNull():
                        img = QImage(filename)
                    # remove possible black borders, except for .NEF
                    if filename[-3:] not in ['nef', 'NEF']:
                        bBorder = 7
                        img = img.copy(QRect(0,bBorder, img.width(), img.height()-2*bBorder))
                    pxm = QPixmap.fromImage(img)
                    if not transformation.isIdentity():
                        pxm = pxm.transformed(transformation)
                    # set item caption and tooltip
                    item = QListWidgetItem(QIcon(pxm), basename(filename)) # + '\n' + rating)
                    item.setToolTip(basename(filename) + ' ' + date + ' ' + rating)
                    # set item mimeData to get filename=item.data(Qt.UserRole)[0] transformation=item.data(Qt.UserRole)[1]
                    item.setData(Qt.UserRole, (filename, transformation))
                    self.wdg.addItem(item)
                # for clean exiting we catch all exceptions and force break
                except OSError:
                    continue
                except:
                    break

def clip(image, mask, inverted=False):
    """
    clip an image by applying a mask to its alpha channel
    @param image:
    @type image:
    @param mask:
    @type mask:
    @param inverted:
    @type inverted:
    @return:
    @rtype:
    """
    bufImg = QImageBuffer(image)
    bufMask = QImageBuffer(mask)
    if inverted:
        bufMask = bufMask.copy()
        bufMask[:,:,3] = 255 - bufMask[:,:,3]
    bufImg[:,:,3] = bufMask[:,:,3]

def boundingRect(img, pattern):
    """
    Given an image img, the function builds the bounding rectangle
    of the region defined by (img == pattern). If the region is empty, the function
    returns an invalid rectangle.
    @param img:
    @type img: 2D array
    @param pattern:
    @type pattern: img.dtype
    @return:
    @rtype: QRect or None
    """
    def leftPattern(b):
        """
        For a 1-channel image, returns the leftmost
        x-coordinate of max value.
        @param b: image
        @type b: 2D array, dtype=int or float
        @return: leftmost x-coordinate of max value
        @rtype: int
        """
        # we build the array of first occurrences of row max
        XMin = np.argmax(b, axis=1)
        # To exclude the rows with a max different of the global max,
        # we assign to them a value greater than all possible indices.
        XMin = np.where(np.diagonal(b[:, XMin])==np.max(b), XMin, np.sum(b.shape)+1)
        return np.min(XMin)
    # indicator function of the region
    img = np.where(img==pattern, 1, 0)
    # empty region
    if np.max(img) == 0:
        return None
    # build the enclosing rectangle
    left = leftPattern(img)
    right = img.shape[1] - 1 - leftPattern(img[::-1, ::-1])
    top = leftPattern(img.T)
    bottom = img.shape[0] - 1 - leftPattern(img.T[::-1, ::-1])
    return QRect(left, top, right - left, bottom - top)


if __name__ == '__main__':
    a= np.ones(100, dtype=int).reshape(10,10)
    #b=strides_2d(a, (11,11))
    m = movingVariance(a,7)
    print(m)
