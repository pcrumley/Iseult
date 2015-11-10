#!/usr/bin/env pythonw
import wx # allows us to make the GUI
import re # regular expressions
import os # Used to make the code portable
import h5py # Allows us the read the data files
from thread import start_new_thread
from threading import Thread
import time,string
import matplotlib
import new_cmaps
from phase_plots import PhasePanel, PhaseSettings
from validator import MyValidator
import numpy as np
import wx.lib.buttons as buttons
import  wx.lib.intctrl
import matplotlib.colors as mcolors
from matplotlib.gridspec import GridSpec
matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import \
    FigureCanvasWxAgg as FigCanvas, \
    NavigationToolbar2WxAgg as NavigationToolbar

class FigWrapper:
    """A simple class  that will eventually hold all of the information
    about each figure in the plot"""

    def __init__(self, parent, ctype='', graph=''):
        self.parent = parent
        self.chartType = ctype
        self.graph = graph
        self.tmp = []
    def LoadKey(self, h5key):
        for elm in self.parent.path_list:
            with h5py.File(os.path.join(self.parent.dirname,elm[self.parent.timeStep.value-1]), 'r') as f:
                if h5key in f.keys():
                    return f[h5key][:]


class Knob:
    """
    Knob - simple class with a "setKnob" method.
    A Knob instance is attached to a Param instance, e.g., param.attach(knob)
    Base class is for documentation purposes.
    """
    def setKnob(self, value):
        pass

class Param:

    """
    The idea of the "Param" class is that some parameter in the GUI may have
    several knobs that both control it and reflect the parameter's state, e.g.
    a slider, text, and dragging can all change the value of the frequency in
    the waveform of this example.
    The class allows a cleaner way to update/"feedback" to the other knobs when
    one is being changed.  Also, this class handles min/max constraints for all
    the knobs.

    Idea - knob list - in "set" method, knob object is passed as well
      - the other knobs in the knob list have a "set" method which gets
        called for the others.
    """
    def __init__(self, initialValue=None, minimum=0., maximum=1.):
        self.minimum = minimum
        self.maximum = maximum
        if initialValue != self.constrain(initialValue):
            raise ValueError('illegal initial value')
        self.value = initialValue
        self.knobs = []

    def attach(self, knob):
        self.knobs += [knob]

    def set(self, value, knob=None):
        self.value = self.constrain(value)
        for feedbackKnob in self.knobs:
            if feedbackKnob != knob:
                feedbackKnob.setKnob(self.value)
        return self.value

    def setMax(self, max_arg, knob=None):
        self.maximum = max_arg
        self.value = self.constrain(self.value)
        for feedbackKnob in self.knobs:
            if feedbackKnob != knob:
                feedbackKnob.setKnob(self.value)
        return self.value
    def constrain(self, value):
        if value <= self.minimum:
            value = self.minimum
        if value >= self.maximum:
            value = self.maximum
        return value


class FloatSliderGroup(Knob):
    def __init__(self, parent, label, param):
        self.sliderLabel = wx.StaticText(parent, label=label)
        self.sliderText = wx.TextCtrl(parent, -1, style=wx.TE_PROCESS_ENTER)
        self.slider = wx.Slider(parent, -1)
        self.slider.SetMax(param.maximum*1000)
        self.slider.SetMax(param.minimum*1000)
        self.setKnob(param.value)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.sliderLabel, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=2)
        sizer.Add(self.sliderText, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=2)
        sizer.Add(self.slider, 1, wx.EXPAND)
        self.sizer = sizer

        self.slider.Bind(wx.EVT_SLIDER, self.sliderHandler)
        self.sliderText.Bind(wx.EVT_TEXT_ENTER, self.sliderTextHandler)

        self.param = param
        self.param.attach(self)

    def sliderHandler(self, evt):
        value = evt.GetInt() / 1000.
        self.param.set(value)

    def sliderTextHandler(self, evt):
        value = float(self.sliderText.GetValue())
        self.param.set(value)

    def setKnob(self, value):

        self.sliderText.SetValue('%g'%value)
        self.slider.SetValue(value*1000)

def scale_bitmap(bitmap, width, height, flip=False):
    image = wx.ImageFromBitmap(bitmap)
    image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    if flip:
        image = image.Mirror()
    result = wx.BitmapFromImage(image)
    return result

class PlaybackGroup(Knob):
    def __init__(self, parent, label, param):
        self.Parent = parent
        self.sliderLabel = wx.StaticText(parent, label=label)
        self.sliderText = wx.TextCtrl(parent, -1, style=wx.TE_PROCESS_ENTER)
        self.slider = wx.Slider(parent, -1)
        self.slider.SetMax(param.maximum)
        self.slider.SetMin(param.minimum)
        self.skipSize = 1
        self.waitTime = .2 # 24 fps (may be much slower because of the plotting time)
        self.param = param

        self.setKnob(self.param.value)

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.playIcon = scale_bitmap(wx.Bitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),'icons', 'play.png')), 35,35)
        self.pauseIcon = scale_bitmap(wx.Bitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),'icons', 'pause.png')), 35,35)
        self.skip_r_Icon = scale_bitmap(wx.Bitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),'icons', 'skip.png')), 35,35)
        self.skip_l_Icon = scale_bitmap(wx.Bitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),'icons', 'skip.png')), 35,35, True)
        self.prefIcon = scale_bitmap(wx.Bitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)),'icons', 'params.png')), 35,35)

        self.skiplButton = wx.BitmapButton(parent, -1, self.skip_l_Icon, size = (35,35), style  = wx.NO_BORDER)
        self.playButton = buttons.GenBitmapToggleButton(parent, -1, self.playIcon, size = (35,35),
                            style = wx.NO_BORDER)
        self.playButton.SetBitmapSelected(self.pauseIcon)
        self.skiprButton = wx.BitmapButton(parent, -1, self.skip_r_Icon, size = (35,35), style  = wx.NO_BORDER)
        self.prefButton = wx.BitmapButton(parent, -1, self.prefIcon, size = (35,35), style  = wx.NO_BORDER)

        sizer.Add(self.skiplButton, 0, wx.EXPAND)
        sizer.Add(self.playButton, 0, wx.EXPAND)
        sizer.Add(self.skiprButton, 0, wx.EXPAND)
        sizer.Add(self.sliderLabel, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=2)
        sizer.Add(self.sliderText, 0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=2)
        sizer.Add(self.slider, 1, wx.EXPAND)
        sizer.Add(self.prefButton, 0, wx.EXPAND)

        self.sizer = sizer

        self.slider.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.sliderHandler)
        self.sliderText.Bind(wx.EVT_TEXT_ENTER, self.sliderTextHandler)

        self.skiplButton.Bind(wx.EVT_BUTTON, self.skipLeft)
        self.skiprButton.Bind(wx.EVT_BUTTON, self.skipRight)
        self.playButton.Bind(wx.EVT_BUTTON, self.onPlay)
        self.prefButton.Bind(wx.EVT_BUTTON, self.openPrefs)

        self.param.attach(self)


    def openPrefs(self, evt):
        win = SettingsFrame(self.Parent, -1, "Playback Settings", size=(350, 200),
                  style = wx.DEFAULT_FRAME_STYLE)
        win.Show(True)

    def skipLeft(self, evt):
        self.param.set(self.param.value - self.skipSize)

    def skipRight(self, evt):
        self.param.set(self.param.value + self.skipSize)

    def onPlay(self, evt):
        start_new_thread(self.playLoop, (self,))

    def playLoop(self, evt):
        start = time.time()
        while self.playButton.GetValue() and self.param.value <self.param.maximum:
            time.sleep(0.02)
            if time.time()-start > self.waitTime:
                self.param.set(self.param.value + self.skipSize)
                start = time.time()
        self.playButton.SetValue(0)

    def sliderHandler(self, evt):
        value = evt.GetInt()
        self.param.set(value)

    def sliderTextHandler(self, evt):
        value = float(self.sliderText.GetValue())
        self.param.set(value)

    def setKnob(self, value):
        self.sliderText.SetValue('%g'%value)
        self.slider.SetValue(value)
        self.slider.SetMax(self.param.maximum)

class SettingsFrame(wx.Frame):
    def __init__(
            self, parent, ID, title, pos=wx.DefaultPosition,
            size=wx.DefaultSize, style=wx.DEFAULT_FRAME_STYLE
            ):

        wx.Frame.__init__(self, parent, ID, title, pos, size, style)
        panel = wx.Panel(self, -1)
        self.parent = parent
        #Create some sizers
        self.mainsizer = wx.BoxSizer(wx.VERTICAL)
        grid =  wx.GridBagSizer(hgap = 10, vgap = 10)

        # A button
        self.button = wx.Button(self, label='Reload Directory')
        self.Bind(wx.EVT_BUTTON, self.OnReload, self.button)

        # Make a button to change the skip size
        self.lblskip = wx.StaticText(self, label = 'Skip Size')
        grid.Add(self.lblskip, pos=(0,0))
        self.enterSkipSize = wx.lib.intctrl.IntCtrl(self, value = self.parent.timeSliderGroup.skipSize, size=( 50, -1 ) )
        grid.Add(self.enterSkipSize, pos=(0,1))
        self.Bind(wx.lib.intctrl.EVT_INT, self.EvtSkipSize, self.enterSkipSize)

        # Make a button to change the time
        self.lblwait = wx.StaticText(self, label = 'Playback time delay')
        grid.Add(self.lblwait, pos=(1,0))
        self.enterWait =wx.TextCtrl(self, -1,
                                str(self.parent.timeSliderGroup.waitTime),
                                validator = MyValidator('DIGIT_ONLY'))
        grid.Add(self.enterWait, pos=(1,1))
        self.Bind(wx.EVT_TEXT, self.EvtWait, self.enterWait)

        # the combobox Control
        self.cmapList = ['magma', 'inferno', 'plasma', 'viridis']
        self.lblcmap = wx.StaticText(self, label='Choose Color Map')
        grid.Add(self.lblcmap, pos=(2,0))
        self.choosecmap = wx.ListBox(self, size = (95,-1), choices = self.cmapList, style = wx.LB_SINGLE)
        self.choosecmap.SetStringSelection(self.parent.cmap)
        grid.Add(self.choosecmap, pos=(2,1))

        self.Bind(wx.EVT_LISTBOX, self.EvtChooseCmap, self.choosecmap)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.EvtChooseCmap, self.choosecmap)

        grid.Add(self.button, (3,0), span= (1,2), flag=wx.CENTER)
        self.mainsizer.Add(grid,0, border=15)
        self.SetSizerAndFit(self.mainsizer)
    # Define functions for the events
    def EvtSkipSize(self, evt):
        self.parent.timeSliderGroup.skipSize = evt.GetValue()

    def EvtWait(self, evt):
        self.parent.timeSliderGroup.waitTime = float(evt.GetString())

    def EvtChooseCmap(self, event):
        self.parent.cmap = event.GetString()
        self.parent.refreshAllGraphs()

    def OnReload(self, event):
        self.parent.findDir()

    def OnCloseMe(self, event):
        self.Close(True)

    def OnCloseWindow(self, event):
        self.Destroy()

class MainWindow(wx.Frame):
    """ We simply derive a new class of Frame """
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title =title, pos = (-1,-1))

        self.CreateStatusBar() # A statusbar in the bottom of the window
        # intialize the working directory
        # Setting up the menu.
        filemenu = wx.Menu()

        # wx.ID_ABOUT and wx.ID_EXIT are standard IDs provided by wxWidgets.
        menuAbout = filemenu.Append(wx.ID_ABOUT, '&About', ' Information about this program')
        menuExit = filemenu.Append(wx.ID_EXIT,'E&xit', 'Terminate the program')
        menuOpen = filemenu.Append(wx.ID_OPEN, '&Open Directory\tCtrl+o', ' Open the Directory')

        # create the menubar
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu, '&File') # Adding the 'filemenu; to the MenuBar
        self.SetMenuBar(menuBar) # Add the menubar to the frame

        # create a bunch of regular expressions used to search for files
        f_re = re.compile('flds.tot.*')
        p_re = re.compile('prtl.tot.*')
        s_re = re.compile('spect.*')
        param_re = re.compile('param.*')
        self.re_list = [f_re, p_re, s_re, param_re]

        flds_paths = []
        prtl_paths = []
        param_paths = []
        spect_paths = []

        self.path_list = [flds_paths, prtl_paths, param_paths, spect_paths]

        # Set the default color map

        self.cmap = 'inferno'

        # Make the know that will hold the timestep info
        self.timeStep = Param(1, minimum=1, maximum=1000)

        # Look for the tristan output files and load the file paths into
        # previous objects
        self.dirname = os.curdir
        self.findDir()


        self.timeStep.attach(self)

        # Make some sizers:
        mainsizer = wx.BoxSizer(wx.VERTICAL)
        grid =  wx.GridBagSizer(hgap = 0.5, vgap = 0.5)
        # Make the playback controsl that will control the time slice of the
        # simulation

        self.timeSliderGroup = PlaybackGroup(self, label=' n:', \
            param=self.timeStep)

        # Make the Figures
        self.Fig1 = FigWrapper(self)
        self.Fig1.graph = PhasePanel(self, self.Fig1)

        self.Fig2 = FigWrapper(self)
        self.Fig2.graph = PhasePanel(self, self.Fig2)
        self.Fig2.graph.prtl_type = 1
        self.Fig2.graph.draw()
        self.Fig3 = FigWrapper(self)
        self.Fig3.graph = PhasePanel(self, self.Fig3)
        self.Fig4 = FigWrapper(self)
        self.Fig4.graph = PhasePanel(self, self.Fig4)
        self.Fig5 = FigWrapper(self)
        self.Fig5.graph = PhasePanel(self, self.Fig5)
        self.Fig6 = FigWrapper(self)
        self.Fig6.graph = PhasePanel(self, self.Fig6)
        self.FigList = [self.Fig1, self.Fig2, self.Fig3, self.Fig4, self.Fig5, self.Fig6]
        col_counter = 0
        for elm in self.FigList:

            grid.Add(elm.graph, pos=(col_counter/2,col_counter%2), flag = wx.EXPAND)
            col_counter += 1
        x = self.Fig3.graph
#        self.Fig3.graph = PhasePanel(self)

#        grid.Replace(x, self.Fig3.graph)#pos=(0,1))
#        x.Destroy()
#        grid.Add(self.Fig3.graph, pos=(0,1), flag = wx.EXPAND)
        for i in range(2):
            grid.AddGrowableCol(i)
        for i in range(3):
            grid.AddGrowableRow(i)



        mainsizer.Add(grid,1, wx.EXPAND)
        mainsizer.Add(self.timeSliderGroup.sizer,0, wx.EXPAND | wx.ALIGN_CENTER | wx.ALL, border=5)

        self.SetSizerAndFit(mainsizer)
#        self.Center()
        APPWIDTH = 1400
        APPHEIGHT = 800
        self.SetSizeWH(APPWIDTH, APPHEIGHT)
        self.Center=()

        # Set the Title


        # Set events.
        self.Bind(wx.EVT_MENU, self.OnAbout, menuAbout)
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)
        self.Bind(wx.EVT_MENU, self.OnOpen, menuOpen)

        self.Show(True)
        self.SetTitle('Iseult: Showing n = %s' % self.timeStep.value)
    def refreshAllGraphs(self):
        tlist = []
        for elm in self.FigList:
            x = Thread(target=elm.graph.draw, args=())
            x.start()
            tlist.append(x)
        is_Done = False
        while not is_Done:
            time.sleep(0.02)
            is_Done = True
            for elm in tlist:
                is_Done &= not elm.isAlive()

    def setKnob(self, value):
#        for elm in self.file_list:
            # Pass the new t_arg
#            elm.Update(value)
        # Set the title

        frame.SetTitle('Iseult: Showing n = %s' % value)

        # refresh the graphs
        self.refreshAllGraphs()

    # Define the Main Window functions
    def OnAbout(self,e):
        # A message dialog box with an OK buttion. wx.OK is a standardID in wxWidgets.
        dlg = wx.MessageDialog(self, 'A plotting program for Tristan-MP output files', 'About Iseult', wx.OK)
        dlg.ShowModal() # show it
        dlg.Destroy() # destroy it when finished

    def OnExit(self, e):
        self.Close(True)

    def pathOK(self):
        """ Test to see if the current path contains tristan files
        using regular expressions, then generate the lists of files
        to iterate over"""
        is_okay = True

        for i in range(len(self.re_list)):
            self.path_list[i]= (filter(self.re_list[i].match, os.listdir(self.dirname)))
            self.path_list[i].sort()
            is_okay &= len(self.path_list[i]) > 0
        self.timeStep.setMax(len(self.path_list[0]))
        return is_okay

    def OnOpen(self,e):
        """open a file"""
        dlg = wx.DirDialog(self, 'Choose the directory of the output files.', style = wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirname = dlg.GetPath()
        dlg.Destroy()
        if not self.pathOK():
            self.findDir('Directory must contain either the output directory or all of the following: flds.tot.*, ptrl.tot.*, params.*, spect.*')


    def findDir(self, dlgstr = 'Choose the directory of the output files.'):
        """Look for /ouput folder, where the simulation results are
        stored. If output files are already in the path, they are
        automatically loaded"""
        dirlist = os.listdir(self.dirname)
        if 'output' in dirlist:
            self.dirname = os.path.join(self.dirname, 'output')
        if not self.pathOK():
            dlg = wx.DirDialog(self,
                               dlgstr,
                               style = wx.DD_DEFAULT_STYLE
                               | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                self.dirname = dlg.GetPath()
            dlg.Destroy()
            if not self.pathOK() :
                self.findDir('Directory must contain either the output directory or all of the following: flds.tot.*, ptrl.tot.*, params.*, spect.*')

app = wx.App(False)
frame = MainWindow(None, 'Iseult')
app.MainLoop()
