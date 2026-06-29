# Supertonic TTS voice manager global plugin for NVDA.
# Copyright (C) 2026
# This file is covered by the GNU General Public License (GPL 2).

import os
import sys
import threading

import globalPluginHandler
import gui
import wx
import ui
from logHandler import log
from scriptHandler import script

# The shared voice-management logic lives in the synthDrivers package. Make sure
# the synthDrivers directory (and its bundled libs) is importable.
_SYNTH_DIR = os.path.join(os.path.dirname(__file__), "..", "synthDrivers")
_SYNTH_DIR = os.path.abspath(_SYNTH_DIR)
if _SYNTH_DIR not in sys.path:
	sys.path.insert(0, _SYNTH_DIR)

try:
	from synthDrivers import _supertonicVoices as voices
except ImportError:
	import _supertonicVoices as voices

# Translators: Title of the Supertonic voice manager dialog.
_DIALOG_TITLE = _("Supertonic voice manager")


class VoiceManagerDialog(wx.Dialog):
	"""Dialog to download, delete and review Supertonic voices."""

	_instance = None

	def __init__(self, parent):
		super().__init__(parent, title=_DIALOG_TITLE)
		self._busy = False

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		contentSizer = wx.BoxSizer(wx.HORIZONTAL)

		# Installed voices column.
		installedSizer = wx.BoxSizer(wx.VERTICAL)
		# Translators: Label for the list of installed Supertonic voices.
		installedSizer.Add(wx.StaticText(self, label=_("&Installed voices:")))
		self.installedList = wx.ListBox(self, style=wx.LB_SINGLE)
		installedSizer.Add(self.installedList, proportion=1, flag=wx.EXPAND)
		# Translators: Button to delete the selected installed voice.
		self.deleteButton = wx.Button(self, label=_("&Delete"))
		installedSizer.Add(self.deleteButton)
		contentSizer.Add(installedSizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

		# Available (downloadable) voices column.
		availableSizer = wx.BoxSizer(wx.VERTICAL)
		# Translators: Label for the list of official voices available to download.
		availableSizer.Add(wx.StaticText(self, label=_("&Available to download:")))
		self.availableList = wx.ListBox(self, style=wx.LB_SINGLE)
		availableSizer.Add(self.availableList, proportion=1, flag=wx.EXPAND)
		# Translators: Button to download the selected available voice.
		self.downloadButton = wx.Button(self, label=_("Dow&nload"))
		availableSizer.Add(self.downloadButton)
		contentSizer.Add(availableSizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

		mainSizer.Add(contentSizer, proportion=1, flag=wx.EXPAND)

		# Status line + bottom buttons.
		# Translators: Initial status text in the voice manager.
		self.statusText = wx.StaticText(self, label=_("Ready."))
		mainSizer.Add(self.statusText, flag=wx.EXPAND | wx.ALL, border=5)

		bottomSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: Button to refresh the list of available voices.
		self.refreshButton = wx.Button(self, label=_("&Refresh list"))
		bottomSizer.Add(self.refreshButton)
		# Translators: Button to close the voice manager dialog.
		self.closeButton = wx.Button(self, wx.ID_CLOSE, label=_("&Close"))
		bottomSizer.Add(self.closeButton)
		mainSizer.Add(bottomSizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=5)

		self.SetSizer(mainSizer)
		mainSizer.Fit(self)

		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		self.downloadButton.Bind(wx.EVT_BUTTON, self.onDownload)
		self.refreshButton.Bind(wx.EVT_BUTTON, self.onRefresh)
		self.closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.Close())
		self.Bind(wx.EVT_CLOSE, self.onCloseEvent)
		self.SetEscapeId(wx.ID_CLOSE)

		self._populateInstalled()
		# Populate the downloadable list from a thread (touches the network).
		self._refreshAvailableAsync()

	# --- list population -------------------------------------------------

	def _populateInstalled(self):
		self.installedList.Clear()
		installed = voices.list_installed_voices()
		for name in installed:
			self.installedList.Append(voices.voice_label(name), name)
		self.deleteButton.Enable(bool(installed) and not self._busy)

	def _populateAvailable(self, available):
		self.availableList.Clear()
		for name in available:
			self.availableList.Append(voices.voice_label(name), name)
		self.downloadButton.Enable(bool(available) and not self._busy)

	def _refreshAvailableAsync(self):
		self._setBusy(True, _("Fetching the list of available voices..."))

		def worker():
			try:
				available = voices.list_downloadable_voices()
				error = None
			except Exception as e:
				log.error("Supertonic: failed to list voices", exc_info=True)
				available = []
				error = str(e)
			wx.CallAfter(self._onAvailableFetched, available, error)

		threading.Thread(target=worker, daemon=True).start()

	def _onAvailableFetched(self, available, error):
		self._populateAvailable(available)
		self._setBusy(False)
		if error:
			# Translators: Status shown when the list of voices could not be fetched.
			self._setStatus(_("Could not fetch voice list: {error}").format(error=error))
		else:
			# Translators: Status shown after the available voice list refreshed.
			self._setStatus(_("Ready."))

	# --- busy / status helpers ------------------------------------------

	def _setBusy(self, busy, status=None):
		self._busy = busy
		self.downloadButton.Enable(not busy and self.availableList.GetCount() > 0)
		self.deleteButton.Enable(not busy and self.installedList.GetCount() > 0)
		self.refreshButton.Enable(not busy)
		if status is not None:
			self._setStatus(status)

	def _setStatus(self, text):
		self.statusText.SetLabel(text)
		# Make the change perceivable to screen reader users immediately.
		ui.message(text)

	# --- button handlers -------------------------------------------------

	def onRefresh(self, evt):
		if self._busy:
			return
		self._populateInstalled()
		self._refreshAvailableAsync()

	def onDownload(self, evt):
		if self._busy:
			return
		sel = self.availableList.GetSelection()
		if sel == wx.NOT_FOUND:
			return
		name = self.availableList.GetClientData(sel)
		# Translators: Status shown while a voice is downloading.
		self._setBusy(True, _("Downloading voice {name}...").format(name=name))

		def worker():
			try:
				voices.download_voice(name)
				error = None
			except Exception as e:
				log.error("Supertonic: failed to download voice %s" % name, exc_info=True)
				error = str(e)
			wx.CallAfter(self._onDownloadDone, name, error)

		threading.Thread(target=worker, daemon=True).start()

	def _onDownloadDone(self, name, error):
		self._setBusy(False)
		self._populateInstalled()
		self._refreshAvailableAsync()
		if error:
			# Translators: Status shown when a voice download fails.
			self._setStatus(_("Download of {name} failed: {error}").format(name=name, error=error))
		else:
			# Translators: Status shown after a voice downloaded successfully.
			self._setStatus(_("Voice {name} downloaded.").format(name=name))

	def onDelete(self, evt):
		if self._busy:
			return
		sel = self.installedList.GetSelection()
		if sel == wx.NOT_FOUND:
			return
		name = self.installedList.GetClientData(sel)

		# Warn when removing the last remaining voice: doing so disables the
		# whole synthesizer (check() will start returning False).
		remaining = [v for v in voices.list_installed_voices() if v != name]
		if not remaining:
			# Translators: Confirmation shown before deleting the last voice.
			msg = _(
				"{name} is the only installed voice. Deleting it will disable the "
				"Supertonic synthesizer until you download another voice. Delete anyway?"
			).format(name=name)
		else:
			# Translators: Confirmation shown before deleting a voice.
			msg = _("Delete voice {name}?").format(name=name)
		if gui.messageBox(
			msg,
			# Translators: Title of the delete confirmation dialog.
			_("Confirm deletion"),
			wx.YES_NO | wx.ICON_WARNING,
			self,
		) != wx.YES:
			return

		try:
			voices.delete_voice(name)
			# Translators: Status shown after a voice was deleted.
			status = _("Voice {name} deleted.").format(name=name)
		except Exception as e:
			log.error("Supertonic: failed to delete voice %s" % name, exc_info=True)
			# Translators: Status shown when deleting a voice fails.
			status = _("Could not delete {name}: {error}").format(name=name, error=str(e))
		self._populateInstalled()
		self._refreshAvailableAsync()
		self._setStatus(status)

	def onCloseEvent(self, evt):
		VoiceManagerDialog._instance = None
		self.Destroy()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: Name of the synthesizer category in the input gestures dialog.
	scriptCategory = _("Supertonic TTS")

	def __init__(self):
		super().__init__()
		self._menuItem = None
		try:
			self._toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
			self._menuItem = self._toolsMenu.Append(
				wx.ID_ANY,
				# Translators: Item in the NVDA Tools menu opening the voice manager.
				_("Supertonic voice manager..."),
			)
			gui.mainFrame.sysTrayIcon.Bind(
				wx.EVT_MENU, self.onVoiceManager, self._menuItem
			)
		except Exception:
			log.error("Supertonic: failed to add Tools menu item", exc_info=True)

	def terminate(self):
		try:
			if self._menuItem is not None:
				self._toolsMenu.Remove(self._menuItem)
		except Exception:
			log.error("Supertonic: failed to remove Tools menu item", exc_info=True)
		super().terminate()

	def _openManager(self):
		if VoiceManagerDialog._instance is not None:
			# Already open: bring it to the front.
			try:
				VoiceManagerDialog._instance.Raise()
				return
			except Exception:
				VoiceManagerDialog._instance = None
		dlg = VoiceManagerDialog(gui.mainFrame)
		VoiceManagerDialog._instance = dlg
		dlg.Show()
		dlg.Raise()

	def onVoiceManager(self, evt):
		wx.CallAfter(self._openManager)

	@script(
		# Translators: Description of the command to open the Supertonic voice manager.
		description=_("Opens the Supertonic voice manager"),
		gesture=None,
	)
	def script_openVoiceManager(self, gesture):
		wx.CallAfter(self._openManager)
