#!/usr/bin/env python3
# coding: utf-8
# vim: set ai ts=4 sw=4 sts=0 noet pi ci

# Copyright © 2017-2019 René Wirnata.
# This file is part of Elk Optics Analyzer (ElkOA).
#
# Elk Optics Analyzer (ElkOA) is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Elk Optics Analyzer (ElkOA) is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar. If not, see <http://www.gnu.org/licenses/>.

import os
import sys

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt

import UiInterface
import Utilities

import matplotlib as mpl
# make sure we use QT5
mpl.use("Qt5Agg")  # noqa
import matplotlib.pyplot as plt
from matplotlib.backends import backend_qt5agg


class TensorElementsDialog(
    QtWidgets.QDialog, UiInterface.Ui_TensorElementsDialog
):
    """Dialog class for choosing tensor elements to plot.

    The user can decide which of the currently available elements should be
    plotted by clicking checkboxes. In case files for certain elements are
    missing, the associated box will be disabled.

    Attributes:
        states: Array holding the currently enabled/disabled/n.a. elements.
        needUpdate: Boolean indicating if refreshing the plots is necessary.
        boxes: Array holding all checkBox objects for convenient looping.
    """

    def __init__(self):
        super(TensorElementsDialog, self).__init__()
        # generate dialog box
        self.setupUi(self)
        # initialize class variables
        self.states = None
        self.needUpdate = False
        self.boxes = [
            self.checkBox_11,
            self.checkBox_12,
            self.checkBox_13,
            self.checkBox_21,
            self.checkBox_22,
            self.checkBox_23,
            self.checkBox_31,
            self.checkBox_32,
            self.checkBox_33,
        ]
        # connect signals and slots
        self.buttonBox.rejected.connect(self.rejected)
        self.buttonBox.accepted.connect(self.accepted)
        self.btnDiagonalOnly.clicked.connect(self.diagonalOnly)

    def exec(self):
        """Extending QDialog's exec() with checkbox initialization."""
        self.setBoxStates()
        # call original method from base class QDialog
        super(TensorElementsDialog, self).exec()

    def setBoxStates(self):
        """Sets checkbox check-states according to current configuration."""
        for boxID, box in enumerate(self.boxes):
            state = self.states[boxID]
            box.setCheckState(state)
            # disable box when corresponding file not in path
            if state == Qt.PartiallyChecked:
                box.setEnabled(False)
            else:
                box.setEnabled(True)

    def diagonalOnly(self):
        """Checks all diagonal elements, unchecks rest."""
        for boxID, box in enumerate(self.boxes):
            # leave unavailable data files as is
            if box.checkState() == Qt.PartiallyChecked:
                continue
            elif boxID in [0, 4, 8]:
                box.setCheckState(Qt.Checked)
            else:
                box.setCheckState(Qt.Unchecked)

    def rejected(self):
        """Signals main window 'no update necessary' and hides this dialog."""
        self.needUpdate = False
        self.hide()

    def accepted(self):
        """Updates tensor states and signals main window to update."""
        self.needUpdate = True
        # read current states from GUI and update array of states
        for boxID, box in enumerate(self.boxes):
            self.states[boxID] = box.checkState()
        # instead of destroying the widget, hide and re-use it later via show
        self.hide()


class MainWindow(
    QtWidgets.QMainWindow, UiInterface.Ui_ElkOpticsAnalyzerMainWindow
):
    """Main window class where the plots are located.

    The user can choose to display data from available tasks and how to plot
    them, i.e. real/imag part together, only one or in vertical/horizontal
    split screen. Combobox tasks with unavailable files in current working
    directory will be disabled.

    Attributes:
        Shortcuts for convenience:
            tabNameDict, fileNameDict, labelDict, readerDict
        version: Holds the current version in Major.Minor.Patch format.
        splitMode: Character indicating horizontal or vertical split mode.
        dpi: Pixel density to use in figures.
        use_global_states: Bool, true if tensor element dialog should apply to
            all plots, false when apply only to current figure.
        additionalPlots: 'triggered' -> true after user loaded additional data
            manually, 'tabID' -> in which tab new plots should be added.
        additionalData: List with data from manually loaded files.
        data: Holds all optical data from Elk output files read during startup.
        tenElementsDialog: Dialog to choose tensor elements to plot.
        needUpdate: Shortcut, see class TensorElementsDialog.
        elkInput: Class that holds all parameters read from elk.in and
            INFO.OUT in current working directory.
        plotter: Class instance taking care of global plot settings .
        ElkDict: Class of many dictionaries used to find the correct reader,
            plotter and axes labels for each Elk task.
    """

    tabNameDict = Utilities.ElkDict.TAB_NAME_DICT
    fileNameDict = Utilities.ElkDict.FILE_NAME_DICT
    readerDict = Utilities.ElkDict.READER_DICT
    labelDict = Utilities.ElkDict.LABEL_DICT
    version = "1.0.0"

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi(self)

        # attributes with default values
        self.splitMode = "h"
        self.dpi = 100
        # NOTE: keep in sync with MainWindow.ui
        self.use_global_states = False
        self.additionalPlots = {"triggered": False, "tabID": [0]}
        self.additionalData = []
        self.data = {}
        self.tenElementsDialog = TensorElementsDialog()
        self.needUpdate = self.tenElementsDialog.needUpdate

        # apply signal/slot settings
        self.connectSignals()
        # add version number permanently to far right end of status bar
        versionLabel = QtWidgets.QLabel("v{}".format(self.version), self)
        self.statusbar.addPermanentWidget(versionLabel)
        self.setStyleSheet("QStatusBar::item {border: 2px;}")
        # print license information in terminal
        self.printAbout()
        # set global plot options
        self.setMplOptions()
        # read Elk input file and INFO.OUT
        self.elkInput = self.parseElkFiles()
        while self.elkInput is None:
            self.setWorkingDirectory()
        # setup plotters for different Elk output files / tasks
        self.plotter = Utilities.Plot(self.elkInput.minw, self.elkInput.maxw)
        # read in all available optics data
        self.readAllData()
        print("--- start plotting ---\n")

    class TabData:
        """Stores content of Elk optical output files."""
        def __init__(self, freqs=None, field=None):
            self.freqs = freqs
            self.field = field
            self.enabled = True
            self.isTensor = False
            self.states = None

    class AdditionalData:
        """Stores content of e.g. experimental data files."""
        def __init__(self, freqs=None, real=None, imag=None, label=None):
            self.freqs = freqs
            self.real = real
            self.imag = imag
            self.label = label

    def connectSignals(self):
        """Connects GUI buttons and menu options to functions of this class."""
        # combo box for tasks
        self.taskChooser.currentIndexChanged[str].connect(self.updateWindow)
        # menu buttons
        self.actionQuit.triggered.connect(self.quitGui)
        self.actionAbout.triggered.connect(self.showAbout)
        self.actionVerticalSplit.triggered.connect(
            lambda: self.changeSplitMode("v")
        )
        self.actionHorizontalSplit.triggered.connect(
            lambda: self.changeSplitMode("h")
        )
        self.actionTensorElements.triggered.connect(
            self.tenElementsDialogWrapper
        )
        self.actionGlobalTensorSettings.triggered.connect(
            self.toggleGlobalTensorSettings
        )
        self.actionGetAdditionalData.triggered.connect(self.getAdditionalData)
        self.actionRemoveAllAdditionalData.triggered.connect(
            self.removeAllAdditionalData
        )
        self.actionSetWorkingDir.triggered.connect(self.setWorkingDirectory)
        self.actionReload.triggered.connect(self.reloadData)
        # (sub)plot configuration
        self.btnRealPart.clicked.connect(self.updateWindow)
        self.btnImaginaryPart.clicked.connect(self.updateWindow)
        self.btnTogether.clicked.connect(self.updateWindow)
        self.btnSplitView.clicked.connect(self.updateWindow)
        self.checkBoxfullRange.clicked.connect(self.setPlotRange)

    def readAllData(self):
        """Reads data from Elk input files and Elk optical output."""
        print("--- reading data ---\n")
        for task in self.fileNameDict:
            # create new TabData instance for each tab for current task
            self.data[task] = [
                self.TabData() for tab in self.tabNameDict[task]
            ]
            for tabIdx, tab in enumerate(self.tabNameDict[task]):
                reader = self.readerDict[task][tabIdx]
                fname = self.fileNameDict[task][tabIdx]
                freqs, field = reader(fname, self.elkInput.numfreqs)
                # disable tab if field data is not present
                if field is None:
                    self.data[task][tabIdx].enabled = False
                else:
                    self.data[task][tabIdx].field = field
                    self.data[task][tabIdx].freqs = freqs
                    # update tensor element states for tensor fields
                    if Utilities.misc.isTensor(field):
                        self.data[task][tabIdx].isTensor = True
                        self.data[task][tabIdx].states = \
                            Utilities.misc.getStates(field)  # noqa
                    print("[INFO] Successfully read data for", fname)
            # disable/mark combo box entry if no task data is present
            tabStates = [tab.enabled for tab in self.data[task]]
            if not any(tabStates):
                # find index of comboBox item that contains `task` as substring
                idx = self.taskChooser.findText(task, Qt.MatchContains)
                # remove unavailable tasks
                self.taskChooser.removeItem(idx)
        self.statusbar.showMessage("Data loaded, ready to plot...", 0)
        print("\n")

    def reloadData(self):
        """Forces to read all Elk output data again from current path."""
        print("\n[INFO] Clearing data cache...\n")
        self.data = {}
        self.readAllData()
        self.statusbar.showMessage("Data reloaded, ready to plot...", 0)
        print("--- start plotting ---\n")

    def updateWindow(self):
        """Redraws figure for currently chosen Elk task."""
        currentText = self.taskChooser.currentText()
        # extract task number (integer) from combobox entry
        task = currentText.split()[0]
        # force user to choose valid task
        # TODO: replace with isEnabled == False check
        if currentText in ("", None, "Please choose an Elk task..."):
            QtWidgets.QMessageBox.warning(
                self, "No task chosen!", "Please choose a task..."
            )
            # TODO find cleaner solution
            self.additionalPlots["triggered"] = False
            return
        # TODO need to remove child widgets manually??
        plt.close("all")
        self.tabWidget.clear()
        self.createTabs(task)

    def createTabs(self, task):
        """Creates and enables/disables new QT tab widgets.

        Args:
            task: Elk task for which new tab should be created.
        """
        # check if only real/imag part or both should be displayed
        style = self.getPlotStyle()
        for tabIdx, name in enumerate(self.tabNameDict[task]):
            # create new tab in tab widget
            tab = QtWidgets.QWidget()
            self.tabWidget.addTab(tab, name)
            # create new figure or disable tab if no data is available
            if self.data[task][tabIdx].enabled:
                self.createFigure(tab, style, task, tabIdx)
            else:
                self.tabWidget.setTabEnabled(tabIdx, False)

    def createFigure(self, tab, style, task, tabIdx):
        """Creates subplots for figure in current tab.

        Args:
            tab: Reference to tab widget that is to be filled.
            style: Plot style passed to subplot creater.
            task: Elk task for this tab.
            tabIdx: Index of this tab w.r.t. tab bar parent widget.
        """
        # create matplotlib interface
        fig = plt.figure(dpi=self.dpi)
        canvas = backend_qt5agg.FigureCanvasQTAgg(fig)
        canvas.mpl_connect("resize_event", self.tightLayout)
        toolbar = backend_qt5agg.NavigationToolbar2QT(canvas, self)
        grid = QtWidgets.QGridLayout()
        tab.setLayout(grid)
        grid.addWidget(toolbar, 0, 0)
        grid.addWidget(canvas, 1, 0)
        # resolve tab titles etc. from dictionaries
        tabName = self.tabNameDict[task][tabIdx]
        label = self.labelDict[tabName]
        data = self.data[task][tabIdx]
        # take tensor element states from field data
        if not self.use_global_states:
            # valid array reference if tensor, None if scalar field
            self.tenElementsDialog.states = data.states
        # create plots
        if data.isTensor:
            ax1, ax2 = self.plotter.plotTen(
                fig,
                data.freqs,
                data.field,
                self.tenElementsDialog.states,
                label,
                style,
            )
        else:
            ax1, ax2 = self.plotter.plotScal(
                fig, data.freqs, data.field, label, style
            )
        # additional plots, e.g. experimental data
        if (
            self.additionalPlots["triggered"]
            and tabIdx in self.additionalPlots["tabID"]
        ):
            # real parts
            if ax1 is not None:
                for ad in self.additionalData:
                    ax1.plot(ad.freqs, ad.real, label=ad.label)
                ax1.legend()
            # imaginary parts
            if ax2 is not None:
                for ad in self.additionalData:
                    ax2.plot(ad.freqs, ad.imag, label=ad.label)
                ax2.legend()
        # draw all plots to canvas
        canvas.draw()

    def getAdditionalData(self):
        """Reads non-Elk data from file(s) and triggers window update."""
        cwd = os.getcwd()
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select one or more files to add to the current plot",
            cwd,
            "Data files (*.dat *.out *.mat);;All files (*.*)",
            options=QtWidgets.QFileDialog.DontUseNativeDialog
        )
        for fname in files:
            freqs, field = Utilities.Read.getAdditionalData(fname)
            # extract filename from path
            fname = os.path.basename(fname)
            # remove extension --> (base, ext)
            fname = os.path.splitext(fname)[0]
            # make label latex friendly
            label = fname.replace("_", "\_")  # noqa
            self.additionalData.append(
                self.AdditionalData(freqs, field.real, field.imag, label)
            )
        self.additionalPlots["triggered"] = True
        self.updateWindow()

    def removeAllAdditionalData(self):
        """Redraws window with all non-Elk data removed."""
        self.additionalData = []
        self.additionalPlots["triggered"] = False
        self.updateWindow()

    def parseElkFiles(self):
        """Wrapper that handles reading of Elk input files."""
        try:
            elkInput = Utilities.ElkInput()
        except FileNotFoundError:
            QtWidgets.QMessageBox.about(
                self,
                "[ERROR] File not found!",
                "File(s) elk.in and/or INFO.OUT could not be found in current "
                "working directory.",
            )
            return None
        return elkInput

    def setWorkingDirectory(self):
        """Updates current working dir to user choice and reads Elk input."""
        from QtWidgets.QFileDialog import DontUseNativeDialog, ShowDirsOnly
        cwd = os.getcwd()
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Directory", cwd, ShowDirsOnly | DontUseNativeDialog
        )
        try:
            os.chdir(path)
        except FileNotFoundError:
            print("[ERROR] Invalid path! Please start again...")
            sys.exit()
        self.statusbar.showMessage("Change working dir to " + str(path), 2000)
        self.elkInput = self.parseElkFiles()

    def tenElementsDialogWrapper(self):
        """Wrapper that handles opening of tensor element dialog."""
        try:
            self.tenElementsDialog.exec()
        except TypeError:
            QtWidgets.QMessageBox.about(
                self, "[ERROR] No task!", "Please choose a task first..."
            )
        # check "return value" -> did user change any settings?
        if self.tenElementsDialog.needUpdate is True:
            self.updateWindow()
            self.statusbar.showMessage("Plot updated...", 2000)

    def toggleGlobalTensorSettings(self):
        """Inverts current setting of global tensor element states usage."""
        self.use_global_states = not self.use_global_states

    def setPlotRange(self, full: bool):
        """Sets the visible frequency range either to minimum or to zero."""
        if full:
            self.plotter.minw = self.elkInput.minw
            self.statusbar.showMessage(
                "Setting minimum frequency to {} eV...".format(
                    self.elkInput.minw
                ),
                2000,
            )
        else:
            self.plotter.minw = 0
            self.statusbar.showMessage(
                "Setting minimum frequency to 0 eV", 2000
            )
        self.updateWindow()

    def changeSplitMode(self, mode):
        """Updates window with new split mode when split is enabled.

        Args:
            mode: Split style can be 'v' for vertical or 'h' for horizontal.
        """
        if mode == "h":
            self.splitMode = "h"
        elif mode == "v":
            self.splitMode = "v"
        if self.btnSplitView.isChecked() is True:
            self.updateWindow()

    def getPlotStyle(self):
        """Reads plot style from current GUI configuration."""
        if self.btnRealPart.isChecked():
            return "r"
        elif self.btnImaginaryPart.isChecked():
            return "i"
        elif self.btnSplitView.isChecked():
            return self.splitMode
        elif self.btnTogether.isChecked():
            return "t"
        else:
            assert False

    def tightLayout(self, event):
        """Wrapper to catch strange error from mpl's resize function."""
        try:
            plt.tight_layout()
        except ValueError:
            print("[ERROR] strange error from plt.tight_layout()")

    def setMplOptions(self):
        """Makes default plot lines, markers and fonts more visible."""
        # font configuration for axes, legend, etc.
        font = {"family": "serif", "size": 18}
        plt.rc("font", **font)
        plt.rc("text", usetex=True)
        plt.rc("legend", fontsize=16)
        # global line and marker options
        mpl.rcParams["lines.linewidth"] = 2
        mpl.rcParams["lines.markeredgewidth"] = 2
        mpl.rcParams["lines.markersize"] = 10
        mpl.rcParams["markers.fillstyle"] = "none"
        # make sure we use QT5
        mpl.use("Qt5Agg")

    def showAbout(self):
        """Opens GUI window with copyright and license information."""
        about = QtWidgets.QMessageBox(self)
        about.setWindowTitle("About...")
        # make links work
        about.setTextFormat(Qt.RichText)
        about.setText(
            "<div align='center'>"
            "Elk Optics Analyzer (ElkOA) v{} <br>".format(self.version) +
            "- Easily plot and analyze Elk optics output data -</div>"
            "<p>Copyright © 2017-2019 René Wirnata</p>"
            "<p>This program is free software: you can redistribute it and/or "
            "modify it under the terms of the GNU General Public License as "
            "published by the Free Software Foundation, either version 3 of "
            "the License, or (at your option) any later version. </p>"
            "<p>This program is distributed in the hope that it will be "
            "useful, but WITHOUT ANY WARRANTY; without even the implied "
            "warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. "
            "See the GNU General Public License for more details. </p>"
            "<p>You should have received a copy of the GNU General Public "
            "License along with this program. If not, see "
            "<a href='https://www.gnu.org/licenses/'>"
            "https://www.gnu.org/licenses/</a>.</p>"
            "<p style='line-height:1.4'>See also:<br>"
            "<a href='http://elk.sourceforge.net'> The Elk Code</a><br>"
            "<a href='https://qftmaterials.wordpress.com'> Quantum Field "
            "Theory of Material Properties</a><br>"
            "<a href='https://tu-freiberg.de/fakultaet2/thph'> Institute for "
            "Theoretical Physics @ TU BA Freiberg</a>"
        )
        about.exec()

    def printAbout(self):
        """Prints copyright and license information to terminal."""
        txt = (
            "\n>>> Elk Optics Analyzer (ElkOA) Copyright (C) 2017-2019 "
            "René Wirnata <<<\n\n"
            "This program is free software and comes with ABSOLUTELY NO"
            "WARRANTY.\nYou are welcome to redistribute it under certain "
            "conditions. See\nHelp->About in GUI for details.\n\n"
            "Running version {} \n\n".format(self.version)
        )
        print(txt)

    def quitGui(self):
        """Quits QT application."""
        print("--- quitting application ---\n")
        self.close()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = MainWindow()
    ui.show()
    sys.exit(app.exec_())

# EOF - ElkOpticsAnalyzer.py