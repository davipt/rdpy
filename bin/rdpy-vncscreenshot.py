#!/usr/bin/python
#
# Copyright (c) 2014-2015 Sylvain Peyrefitte
#
# This file is part of rdpy.
#
# rdpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

"""
example of use rdpy
take screenshot of login page
"""

import sys, os, getopt
from PyQt5 import QtCore, QtGui, QtWidgets
from rdpy.protocol.rfb import rfb
import rdpy.core.log as log
from rdpy.ui.qt5 import qtImageFormatFromRFBPixelFormat
from twisted.internet import task

from rdpy.core.layer import RawLayer

#set log level
log._LOG_LEVEL = log.Level.INFO

def stop(reactor):
    try:
        # https://stackoverflow.com/a/13538248
        reactor.removeAll()
        reactor.iterate()
        reactor.stop()
    except Exception as e:
        log.warning(f"Error stopping reactor: {e}")


class RFBScreenShotFactory(rfb.ClientFactory):
    """
    @summary: Factory for screenshot exemple
    """
    __INSTANCE__ = 0
    def __init__(self, reactor, password, path, timeout):
        """
        @param password: password for VNC authentication
        @param path: path of output screenshot
        """
        RFBScreenShotFactory.__INSTANCE__ += 1
        self._reactor = reactor
        self._path = path
        self._timeout = timeout
        self._password = password
        
    def clientConnectionLost(self, connector, reason):
        """
        @summary: Connection lost event
        @param connector: twisted connector use for rfb connection (use reconnect to restart connection)
        @param reason: str use to advertise reason of lost connection
        """
        if "Connection was closed cleanly" not in f"{reason}":
            log.info("connection lost : %s"%reason)
        RFBScreenShotFactory.__INSTANCE__ -= 1
        if(RFBScreenShotFactory.__INSTANCE__ == 0):
            # reactor.stop()
            stop(reactor)
            app.exit()
        
    def clientConnectionFailed(self, connector, reason):
        """
        @summary: Connection failed event
        @param connector: twisted connector use for rfb connection (use reconnect to restart connection)
        @param reason: str use to advertise reason of lost connection
        """
        log.info("connection failed : %s"%reason)
        RFBScreenShotFactory.__INSTANCE__ -= 1
        if(RFBScreenShotFactory.__INSTANCE__ == 0):
            # reactor.stop()
            stop(reactor)
            app.exit()
        
        
    def buildObserver(self, controller, addr):
        """
        @summary: build ScreenShot observer
        @param controller: RFBClientController
        @param addr: address of target
        """
        class ScreenShotObserver(rfb.RFBClientObserver):
            """
            @summary: observer that connect, cache every image received and save at deconnection
            """
            def __init__(self, controller, path, timeout, reactor):
                """
                @param controller: RFBClientController
                @param path: path of output screenshot
                """
                rfb.RFBClientObserver.__init__(self, controller)
                self._path = path
                self._buffer = None
                self._timeout = timeout
                self._reactor = reactor
                self._startTimeout = False
                self._got_screenshot = False
                
            def onUpdate(self, width, height, x, y, pixelFormat, encoding, data):
                """
                Implement RFBClientObserver interface
                @param width: width of new image
                @param height: height of new image
                @param x: x position of new image
                @param y: y position of new image
                @param pixelFormat: pixefFormat structure in rfb.message.PixelFormat
                @param encoding: encoding type rfb.message.Encoding
                @param data: image data in accordance with pixel format and encoding
                """
                imageFormat = qtImageFormatFromRFBPixelFormat(pixelFormat)
                if imageFormat is None:
                    log.error("Receive image in bad format")
                    return
                image = QtGui.QImage(data, width, height, imageFormat)
                with QtGui.QPainter(self._buffer) as qp:
                    #draw image
                    qp.drawImage(x, y, image, 0, 0, width, height)
                log.info(f"incoming frame pos={x},{y} size={width},{height}")
                self._got_screenshot = True
                self.mouseEvent(1, 1, 1)
                self.keyEvent(True, 27)  # escape key

                if not self._startTimeout:
                    self._startTimeout = False
                    self._reactor.callLater(self._timeout, self.checkUpdate)

            def onReady(self):
                """
                @summary: callback use when RDP stack is connected (just before received bitmap)
                """
                log.info("connected %s"%addr)
                self._width, self._height = self._controller.getScreen()
                log.info(f"ready size={self._width},{self._height}")
                self._buffer = QtGui.QImage(self._width, self._height, QtGui.QImage.Format_RGB32)
            
            def onClose(self):
                """
                @summary: callback use when RDP stack is closed
                """
                if self._got_screenshot:
                    log.info("save screenshot into %s"%self._path)
                    self._buffer.save(self._path)
                log.info("close")
        
            def checkUpdate(self):
                self._controller.close()

        controller.setPassword(self._password)
        return ScreenShotObserver(controller, self._path, self._timeout, self._reactor)
        
def help():
    print("Usage: rdpy-vncscreenshot [options] ip[:port]")
    print("\t-o: file path of screenshot default(/tmp/rdpy-vncscreenshot.jpg)")
    print("\t-t: timeout of connection without any updating order (default is 2s)")
    print("\t-p: password for VNC Session")
        
if __name__ == '__main__':
    #default script argument
    path = "/tmp/"
    timeout = 2.0
    password = ""
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hp:o:")
    except getopt.GetoptError:
        opts = [('-h', '')]
    for opt, arg in opts:
        if opt == "-h":
            help()
            sys.exit()
        elif opt == "-o":
            path = arg
        elif opt == "-p":
            password = arg
        elif opt == "-t":
            timeout = float(arg)
        
    #create application
    app = QtWidgets.QApplication(sys.argv)
    
    #add qt5 reactor
    import qt5reactor
    qt5reactor.install()
    from twisted.internet import reactor


    # FIXME
    if len(args) != 1:
        raise Exception(f"Only one host supported, got {args}")
    
    for arg in args:      
        if ':' in arg:
            ip, port = arg.split(':')
        else:
            ip, port = arg, "5900"

        # FIXME 
        out_file = path + "%s.bin" % ip
        if os.path.exists(out_file):
            os.unlink(out_file)        
        print(f"[*] INFO:       out_file={out_file}")
        def hack(data):
            # print(f"FOOBAR data {data}")
            # only first line
            if os.path.exists(out_file):
                return
            out= open(out_file, "ab")
            out.write(data)
            # out.write(b"\n")
            out.close()
        RawLayer.__hack__ = hack

        reactor.connectTCP(ip, int(port), RFBScreenShotFactory(reactor, password, path + "%s.jpg" % ip, timeout))

    
    reactor.runReturn()
    app.exec_()