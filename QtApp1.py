import sys
import cv2
from PyQt4.QtCore import Qt, QRect, QEvent, QSettings, QSize, QString
from PyQt4.QtGui import QPixmap, QImage, QColor,QPainter, QApplication, QMenu, QAction, QCursor, QFileDialog, QColorDialog
import QtGui1
import PyQt4.Qwt5 as Qwt
import time

from imgconvert import *
from MarkedImg import mImage, imImage, QLayer

P_SIZE=4000000

CONST_FG_COLOR = QColor(255, 255, 255,128)
CONST_BG_COLOR = QColor(255, 0, 255,128)

thickness = 30*4
State = {'drag' : False, 'drawing' : False , 'tool_rect' : False, 'rect_over' : False, 'ix' : 0, 'iy' :0, 'rawMask' : None}

rect_or_mask = 0

def QRect2tuple(qrect):
    return (qrect.left(), qrect.top(), qrect.right()-qrect.left(), qrect.bottom()-qrect.top())

def waitBtnEvent():
    global btn_pressed
    btn_pressed=False
    while not btn_pressed:
        time.sleep(0.1)
        print 'waiting'
    btn_pressed = False




mask=None
mask_s=None

def do_grabcut(img0, preview=-1, nb_iter=1, mode=cv2.GC_INIT_WITH_RECT, again=False):
    """
    segment source MImage instance.

    :param img0: source Mimage, unmodified.
    :param preview:
    :param nb_iter:
    :param mode
    :return:
    """
    #img0.rect = QRect(500, 400, Mimg.width() - 2000, Mimg.height() - 1000)

    print '********* do_grabCut call'
    mask_s = State['rawMask']
    global rect_or_mask

    #if preview>0:
        #img0_r=img0.resize(preview)
    #else:
    img0_r=img0

    # set rect mask
    rectMask = np.zeros((img0_r.height(), img0_r.width()), dtype=np.uint8)
    rectMask[img0_r.rect.top():img0_r.rect.bottom(), img0_r.rect.left():img0_r.rect.right()] = cv2.GC_PR_FGD

    if not again:
        #get painted values in BGRA order
        paintedMask = QImageToNdarray(img0_r._layers['drawlayer'])

        paintedMask[paintedMask==255]=cv2.GC_FGD
        paintedMask[paintedMask==0]=cv2.GC_BGD

        np.copyto(rectMask, paintedMask[:,:,1], where=(paintedMask[:,:,3]>0)) # copy  painted (A > 0) pixels (G value only)

        if mask_s is not None:
            np.copyto(rectMask, mask_s, where=(np.logical_and((mask_s==0),(paintedMask[:,:,0]==0))))

        mask_s=rectMask
        rect_or_mask=0
    else:
        if mask_s is None:
            mask_s=rectMask
            print "None mask"
        else:
            print "reuse mask"

    bgdmodel = np.zeros((1, 13 * 5), np.float64)  # Temporary array for the background model
    fgdmodel = np.zeros((1, 13 * 5), np.float64)  # Temporary array for the foreground model

    t0 = time.time()
    if preview >0:
        img0_r=img0_r.resize(preview)
        mask_s=cv2.resize(mask_s, (img0_r.width(), img0_r.height()), interpolation=cv2.INTER_NEAREST)
        #a=img0_r.cv2Img()
    #cv2.grabCut_mtd(img0_r.cv2Img()[:,:,:3],
    cv2.grabCut(img0_r.cv2Img()[:, :, :3],
                mask_s,
                None,#QRect2tuple(img0_r.rect),
                bgdmodel, fgdmodel,
                nb_iter,
                mode)
    print 'grabcut_mtd time :', time.time()-t0

    img0_r = img0
    if preview >0:
        mask_s=cv2.resize(mask_s, (img0.width(), img0.height()), interpolation=cv2.INTER_NEAREST)

    State['rawMask'] = mask_s
    # apply mask
    current_mask = mask_s
    #mask= np.bitwise_and(mask_s , 12)
    #mask= np.right_shift(mask, 2)
    #mask[:200,:200]=1
    #mask_s=np.bitwise_and(mask_s , 3)
    #current_mask=mask_s
    mask_s = np.where((current_mask == cv2.GC_FGD) + (current_mask == cv2.GC_PR_FGD), 1, 0)
    mask_s1 = np.where((current_mask == cv2.GC_FGD) + (current_mask == cv2.GC_PR_FGD), 1, 0.4)

    tmp = np.copy(img0_r.cv2Img())

    tmp[:, :, 3] = tmp[:, :, 3] * mask_s1 # cast float to uint8

    img1= imImage(cv2Img=tmp, cv2mask=current_mask)
    #display
    #window.label_2.repaint()

    b=np.zeros((img0_r.height(), img0_r.width()), dtype=np.uint8)
    c=np.zeros((img0_r.height(), img0_r.width()), dtype=np.uint8)
    b[:,:]=255
    alpha = ((1 - mask_s) * 255).astype('uint8')
    #cv2mask = cv2.resize(np.dstack((b, c, c, alpha)), (img0.qImg.width(), img0.qImg.height()), interpolation=cv2.INTER_NEAREST)
    cv2mask = np.dstack((c, c, b, alpha))
    img0._layers['masklayer']=QLayer(QImg=ndarrayToQImage(cv2mask))
    #img0.drawLayer=mImage(QImg=ndarrayToQImage(cv2mask))
    #img1=imImage(cv2Img=cv2.inpaint(img1.cv2Img[:,:,:3], mask_s, 20, cv2.INPAINT_NS), format=QImage.Format_RGB888)
    return img1

def canny(img0, img1) :
   low = window.slidersValues['low']
   high = window.slidersValues['high']

   l= [k[-1] for k in window.btnValues if window.btnValues[k] == 1]
   if l :
       aperture = int(l[0])
   else :
       aperture =3

   print 'Canny edges', 'low=%d, high=%d aperture=%d' % (low, high, aperture)

   edges = cv2.Canny(img0.cv2Img, low, high, L2gradient=True, apertureSize=aperture) #values 3,5,7

   contours= cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
   edges[:]=0
   print len(contours)
   cv2.drawContours(edges, contours[0], -1, 255, 2)
   img1.__set_cv2Img(edges)
   window.label_2.repaint()

qp=QPainter()


def paintEvent(widg, e) :

    qp.begin(widg)
    qp.translate(5, 5)
    qp.setClipRect(QRect(0,0, widg.width()-10, widg.height()-10))
    #qp.setCompositionMode(qp.CompositionMode_DestinationIn)  # avoid alpha summation

    mimg= widg.img
    r=mimg.resize_coeff(widg)
    qp.setPen(QColor(0,255,0))
    qp.fillRect(QRect(0, 0, widg.width() - 10, widg.height() - 10), QColor(255, 128, 0, 50));

    for layer in mimg._layers.values() :
        if layer.visible:
            qp.drawPixmap(QRect(mimg.xOffset,mimg.yOffset, mimg.width()*r-10, mimg.height()*r-10), # target rect
                          layer.qPixmap
                         )
    if mimg.rect is not None :
        qp.drawRect(mimg.rect.left()*r + mimg.xOffset, mimg.rect.top()*r +mimg.yOffset,
                    mimg.rect.width()*r, mimg.rect.height()*r
                    )
    #if mimg.mask is not None :
        #qp.drawImage(QRect(mimg.xOffset, mimg.yOffset, mimg.width * r-10, mimg.height * r  -10), mimg.mask)
    """
    for layer in mimg.layers.values() :
        if layer.visible:
            qp.drawImage(QRect(mimg.xOffset, mimg.yOffset, mimg.qImg.width() * r - 10, mimg.qImg.height() * r - 10), layer.qImg)
    """
    qp.end()

def showResult(img0, img1, turn):
    global mask, mask_s
    print 'turn', turn
    img0=img0.resize(P_SIZE)
    #mask = np.zeros(img0.cv2Img.shape[:2], dtype=np.uint8)
    if turn ==0:
        current_mask = mask
    else:
        current_mask= mask_s

    mask2 = np.where((current_mask == cv2.GC_FGD) + (current_mask == cv2.GC_PR_FGD), 1, 0).astype('uint8')
    #img1.set_cv2Img_(img0.cv2Img)
    img1=imImage(cv2Img=img0.cv2Img)
    img1.cv2Img[:, :, 3] = img1.cv2Img[:, :, 3] * mask2
    #img1.set_cv2Img_(img1.cv2Img)
    img1 = imImage(cv2Img=img0.cv2Img)
    window.label_2.img=img1
    window.label_2.repaint()



turn = 0
def mouseEvent(widget, event) :

    global rect_or_mask, mask, mask_s, turn,Mimg_1

    img= widget.img

    r = img.resize_coeff(widget)
    x, y = event.x(), event.y()
    modifier = QApplication.keyboardModifiers()

    if modifier == Qt.ControlModifier:
        if event.type() == QEvent.MouseButtonPress:
            showResult(Mimg_p, Mimg_1, turn)
            turn = (turn + 1) % 2
        return

    if event.type() == QEvent.MouseButtonPress :
        if event.button() == Qt.LeftButton:
            pass #State['tool_rect'] = True
        """
        elif event.button() == Qt.RightButton:
            #State['drag'] = True
            if not State['rect_over']:
                print("first draw rectangle \n")
            else:
                pass
                # State['drawing'] = True
                # # cv2.circle(img.cv2Img, (int(x/r), int(y/r)), thickness, value['color'], -1)
                # cv2.circle(img.mask, (int(x/r), int(y/r)), thickness, value['val'], -1)
                # rect_or_mask = 1
                # mask = cv2.bitwise_or(img.mask, mask)
                # do_grabcut(Mimg_p, Mimg_1, preview=P_SIZE)
        """
        State['ix'], State['iy'] = x, y

    elif event.type() == QEvent.MouseMove :
        if window.btnValues['rectangle'] :
            img.rect = QRect(min(State['ix'], x)/r -img.xOffset/r, min(State['iy'], y)/r - img.yOffset/r, abs(State['ix'] - x)/r, abs(State['iy'] - y)/r)
            rect_or_mask = 0
        elif (window.btnValues['drawFG'] or window.btnValues['drawBG']):
            color= CONST_FG_COLOR if window.btnValues['drawFG'] else CONST_BG_COLOR
            #qp.begin(img.mask)
            qp.begin(img._layers['drawlayer'])
            qp.setPen(color)
            qp.setBrush(color);
            qp.setCompositionMode(qp.CompositionMode_Source)  # avoid alpha summation
            qp.drawEllipse(int(x / r)-img.xOffset/r, int(y / r)- img.yOffset/r, 80, 80)
            qp.end()
            rect_or_mask=1

            #mask=cv2.bitwise_or(img.resize(40000).mask, mask)

            #window.label_2.img=do_grabcut(Mimg_p, preview=P_SIZE)
            #window.label_2.repaint()
            window.label.repaint()
        else:
            img.xOffset+=(x-State['ix'])
            img.yOffset+=(y-State['iy'])
            State['ix'],State['iy']=x,y
            print x,y,img.xOffset, img.yOffset
    elif event.type() == QEvent.MouseButtonRelease :
        if event.button() == Qt.LeftButton:
            if window.btnValues['rectangle']:
                #State['tool_rect'] = False
                #State['rect_over'] = True
                #cv2.rectangle(img, (State['ix'], State['iy']), (x, y), BLUE, 2)
                img.rect = QRect(min(State['ix'], x)/r-img.xOffset/r, min(State['iy'], y)/r- img.yOffset/r, abs(State['ix'] - x)/r, abs(State['iy'] - y)/r)
                rect_or_mask = 0 #init_with_rect
                #tmp=np.zeros((img.height, img.width), dtype=np.uint8)
                #tmp[img.rect.top():img.rect.bottom(), img.rect.left():img.rect.right()] = cv2.GC_PR_FGD
                #img.mask=ndarrayToQimage(tmp)
                #mask=tmp
                #mask_s=tmp
                #window.label_2.img=do_grabcut(Mimg_p, preview=P_SIZE, mode =cv2.GC_INIT_WITH_MASK)
                #window.label_2.repaint()
                rect_or_mask=1 # init with mask
                #print(" Now press the key 'n' a few times until no further change \n")
        """
        elif event.button() == Qt.RightButton:
            State['drag'] = False
            if window.btnValues['drawFG']:
                #State['drawFG'] = False
                #cv2.circle(img.cv2Img, (x, y), thickness, value['color'], -1)
                #cv2.circle(img.mask, (int(x/r), int(y/r)), thickness, value['val'], -1)
                qp.drawEllipse(int(x/r), int(y/r), 10,10)
                rect_or_mask=1
                #cv2.bitwise_or(img.mask, mask)
                #window.label_2.img=do_grabcut(Mimg_p, preview=P_SIZE)
                #tmp = img.mask
                #if not (mask is None):
                    #np.copyto(mask, tmp, where=(tmp == 1))
                window.label.repaint()
        """
    widget.repaint()

def wheelEvent(widget,img, event):
    numDegrees = event.delta() / 8
    numSteps = numDegrees / 150.0
    img.Zoom_coeff += numSteps
    widget.repaint()

app = QApplication(sys.argv)
window = QtGui1.Form1()


#window.showMaximized()

#load test image
Mimg = imImage(filename='orch2-2-2.jpg')

Mimg_p=Mimg

#Mimg_0 = imImage(QImg=Mimg_p.qImg, copy=True)
#Mimg_1 = imImage(QImg=Mimg_p.qImg, copy=True)

#set left and right images
window.label.img=Mimg_p
window.label_2.img= Mimg_p
window.tableView.addLayers(Mimg_p)

def set_event_handler(widg):
    widg.paintEvent = lambda e, wdg=widg : paintEvent(wdg,e)
    widg.mousePressEvent = lambda e, wdg=widg : mouseEvent(wdg, e)
    widg.mouseMoveEvent = lambda e, wdg=widg : mouseEvent(wdg, e)
    widg.mouseReleaseEvent = lambda e, wdg=widg : mouseEvent(wdg, e)
    widg.wheelEvent = lambda e, wdg=widg : wheelEvent(wdg, wdg.img, e)

set_event_handler(window.label)
set_event_handler(window.label_2)

window.label.setStyleSheet("background-color: rgb(200, 200, 200);")


#img_0=Mimg_0.cv2Img()
#Mimg.rect = QRect(500, 400, Mimg.qImg.width()-2000, Mimg.qImg.height()-1000)

def button_change(widg):
    if str(widg.accessibleName()) == "Apply" :
        print "grabcut"
        #do_grabcut(Mimg_p, mode=cv2.GC_INIT_WITH_MASK, again=(rect_or_mask==0))
        do_grabcut(window.label.img, mode=cv2.GC_INIT_WITH_MASK, again=(rect_or_mask==0))
    elif str(widg.accessibleName()) == "Preview" :
        print "grabcut preview"
        window.label_2.img = do_grabcut(window.label.img, preview=P_SIZE, mode=cv2.GC_INIT_WITH_MASK, again=(rect_or_mask==0))
    print "done"
    window.label_2.repaint()

def contextMenu(widget):
    qmenu = QMenu("Context menu")
    for k in widget.img.layers.keys():
        action1 = QAction(k, qmenu, checkable=True)
        qmenu.addAction(action1)
        action1.triggered[bool].connect(lambda b, widget=widget, layer=widget.img.layers[k]: toggleLayer(widget, layer,b))
        action1.setChecked(widget.img.layers[k].visible)
    qmenu.exec_(QCursor.pos())

def toggleLayer(widget, layer, b):
    layer.visible = b
    widget.repaint()

def fileMenu(name):
    window._recentFiles = window.settings.value('paths/recent', [], QString)
    window.updateMenuOpenRecent()
    if name == 'actionOpen' :
        lastDir = window.settings.value('paths/dlgdir', 'F:/bernard').toString()
        dlg =QFileDialog(window, "select", lastDir)

        if dlg.exec_():
            filenames = dlg.selectedFiles()
            newDir = dlg.directory().absolutePath()
            window.settings.setValue('paths/dlgdir', newDir)
            filter(lambda a: a != filenames[0], window._recentFiles)
            window._recentFiles.append(filenames[0])
            if len(window._recentFiles) > 5:
                window._recentFiles.remove(0)
            window.settings.setValue('paths/recent', window._recentFiles)
            window.updateMenuOpenRecent()
            window.label.img = imImage(filename=filenames[0])
            window.label.repaint()

def openFile(f):
    window.label.img = imImage(filename=f)
    window.label.repaint()



# set button and slider change handler
window.onWidgetChange = button_change
window.onShowContextMenu = contextMenu
window.onExecFileMenu = fileMenu
window.onExecFileOpen = openFile


#color=QColorDialog(window)
#color.setWindowFlags(Qt.Widget)
#color.show()

window.readSettings()

window._recentFiles = window.settings.value('paths/recent', [], QString)
window.updateMenuOpenRecent()

window.show()
sys.exit(app.exec_())