import difflib
import os
import sys
import threading
import queue

# Add the libs directory to sys.path so we can import supertonic and its dependencies
libs_path = os.path.join(os.path.dirname(__file__), "libs")
if libs_path not in sys.path:
	sys.path.insert(0, libs_path)

import numpy as np
import synthDriverHandler
import languageHandler
from logHandler import log
import nvwave
import supertonic
from synthDriverHandler import synthIndexReached, synthDoneSpeaking
from autoSettingsUtils.driverSetting import NumericDriverSetting
from speech.commands import IndexCommand, LangChangeCommand
from supertonic.utils import chunk_text

try:
	from synthDrivers import _supertonicVoices as voices
except ImportError:
	import _supertonicVoices as voices

def _build_remap(source_text, target_text):
	remap = [0] * (len(source_text) + 1)
	if not source_text:
		return remap

	matcher = difflib.SequenceMatcher(a=source_text, b=target_text, autojunk=False)
	for tag, i1, i2, j1, j2 in matcher.get_opcodes():
		if tag == "equal":
			for i in range(i1, i2):
				remap[i] = j1 + (i - i1)
		elif tag in ("replace", "delete"):
			for i in range(i1, i2):
				remap[i] = j1
		# "insert" has no source indices to map.

	remap[len(source_text)] = len(target_text)
	last = 0
	for i in range(len(remap)):
		if remap[i] == 0 and i != 0:
			remap[i] = last
		if remap[i] < last:
			remap[i] = last
		last = remap[i]

	return remap

class SynthDriver(synthDriverHandler.SynthDriver):
	"""
	NVDA Synth Driver for Supertonic TTS (multilingual, supertonic-3).
	"""
	name = "supertonic"
	description = _("Supertonic")

	# We support automatic language switching: when NVDA's "Automatic language
	# switching" option is on, it injects LangChangeCommand objects into the
	# speech sequence and we honour them per text segment. When off, no such
	# commands arrive and we fall back to the manually selected language.
	supportedCommands = {IndexCommand, LangChangeCommand}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		# Only advertise Supertonic as selectable when it can actually speak:
		# the ONNX model must be present AND at least one voice must be installed.
		# This prevents the user from ever switching (even accidentally, via the
		# synth ring) to a Supertonic that has no usable voice.
		return voices.is_ready()

	def __init__(self):
		super().__init__()
		# The ONNX model is bundled; voice styles live in the writable user dir.
		model_dir = voices.get_bundle_model_dir()
		try:
			self._tts = supertonic.TTS(model_dir=model_dir, auto_download=False)
		except Exception:
			log.error("Failed to initialize Supertonic TTS", exc_info=True)
			raise RuntimeError("Supertonic initialization failed")

		self._player = nvwave.WavePlayer(
			channels=1,
			samplesPerSec=self._tts.sample_rate,
			bitsPerSample=16
		)
		
		# Initialize settings with defaults from the installed (user) voices.
		installed = voices.list_installed_voices()
		self._voice = installed[0] if installed else "M1"
		# Default speed is 1.05. 
		# NVDA rate 27 maps to approx 1.05 with our mapping: 0.7 + (27/100)*1.3 = 1.051
		self._rate = 27 
		self._quality = 5
		# Manually selected language (used when automatic language switching is
		# off). Defaults to NVDA's interface language if the model supports it,
		# otherwise to English.
		self._language = voices.normalize_lang(languageHandler.getLanguage()) or voices.DEFAULT_LANGUAGE
		if self._language == voices.UNKNOWN_LANGUAGE:
			self._language = voices.DEFAULT_LANGUAGE
		
		self._job_queue = queue.Queue()
		self._generation = 0
		self._generation_lock = threading.Lock()
		self._stop_event = threading.Event()
		self._worker_thread = threading.Thread(target=self._worker, daemon=True)
		self._worker_thread.start()

	def _worker(self):
		while not self._stop_event.is_set():
			try:
				job = self._job_queue.get(timeout=0.5)
			except queue.Empty:
				continue
			
			generation, segments, voice_name, rate, quality = job
			
			with self._generation_lock:
				if generation != self._generation:
					self._job_queue.task_done()
					continue
			
			try:
				self._process_job(generation, segments, voice_name, rate, quality)
			except Exception:
				log.error("Error in Supertonic worker", exc_info=True)
				synthDoneSpeaking.notify(synth=self)
			finally:
				self._job_queue.task_done()

	def _resolve_voice(self, voice_name):
		"""Return (voice_name, voice_file) for an installed voice, or (None, None)."""
		voice_file = voices.voice_path(voice_name)
		if not voice_file.exists():
			installed = voices.list_installed_voices()
			if not installed:
				return None, None
			voice_name = installed[0]
			self._voice = voice_name
			voice_file = voices.voice_path(voice_name)
		return voice_name, voice_file

	def _process_job(self, job_generation, segments, voice_name, rate, quality):
		"""Synthesize a list of (text, lang, index_map) segments in order.

		Each segment carries its own language so that, with automatic language
		switching enabled, mixed-language text is spoken correctly. Audio from
		all segments is fed to a single player so playback is continuous.
		"""
		voice_name, voice_file = self._resolve_voice(voice_name)
		if voice_file is None:
			log.error("Supertonic: no voices installed; cannot synthesize")
			synthDoneSpeaking.notify(synth=self)
			return
		voice_style = self._tts.get_voice_style_from_path(voice_file)
		speed = 0.7 + (rate / 100.0) * (2.0 - 0.7)

		processor = self._tts.model.text_processor
		max_chunk_length = 10000
		silence_duration = 0.1

		spoke_anything = False
		for text, lang, index_map in segments:
			with self._generation_lock:
				if self._generation != job_generation:
					return
			if not text.strip():
				continue
			ok = self._synthesize_segment(
				job_generation, processor, voice_style, speed, quality,
				max_chunk_length, silence_duration, text, lang, index_map,
			)
			if ok:
				spoke_anything = True

		# Wait for playback to finish (only if we actually fed audio).
		if spoke_anything:
			with self._generation_lock:
				if self._generation != job_generation:
					return
			self._player.idle()
		synthDoneSpeaking.notify(synth=self)

	def _synthesize_segment(
		self, job_generation, processor, voice_style, speed, quality,
		max_chunk_length, silence_duration, text, lang, index_map,
	):
		"""Synthesize and feed a single same-language text segment.

		Returns True if audio was fed to the player. Index notifications are
		fired in sync with playback, mirroring the original single-segment path.
		"""
		# Spell numbers out into words before anything else, because the neural
		# model reads bare digits poorly. This changes the text length, so we
		# remap the index marks (caret/say-all positions) through the same
		# difflib-based remap used for the other text transformations.
		expanded_text = voices.expand_numbers(text, lang)
		if expanded_text != text:
			remap_expand = _build_remap(text, expanded_text)
			remapped = []
			for offset, idx in index_map:
				if offset > len(text):
					offset = len(text)
				remapped.append((remap_expand[offset], idx))
			index_map = remapped
			text = expanded_text

		# Sanitize text and remap indices to the filtered text.
		filtered_chars = []
		remap_filtered = [0] * (len(text) + 1)
		for i, char in enumerate(text):
			remap_filtered[i] = len(filtered_chars)
			is_valid, _ = processor.validate_text(char)
			if is_valid:
				filtered_chars.append(char)
		remap_filtered[len(text)] = len(filtered_chars)
		filtered_text = "".join(filtered_chars)

		if not filtered_text.strip():
			return False

		chunks = chunk_text(filtered_text, max_chunk_length)
		processed_chunks = [processor._preprocess_text(chunk, lang) for chunk in chunks]
		processed_text = "".join(processed_chunks)
		remap_processed = _build_remap(filtered_text, processed_text)

		# Rebuild index map with new offsets.
		new_index_map = []
		for offset, idx in index_map:
			if offset > len(text):
				offset = len(text)
			filtered_offset = remap_filtered[offset]
			if filtered_offset > len(filtered_text):
				filtered_offset = len(filtered_text)
			new_offset = remap_processed[filtered_offset]
			if new_offset > len(processed_text):
				new_offset = len(processed_text)
			new_index_map.append((new_offset, idx))
		index_map = new_index_map

		with self._generation_lock:
			if self._generation != job_generation:
				return False

		wav, _, dur_lists = self._tts.synthesize(
			filtered_text,
			voice_style=voice_style,
			speed=speed,
			total_steps=quality,
			max_chunk_length=max_chunk_length,
			silence_duration=silence_duration,
			lang=lang,
			return_alignment=True,
		)

		cum_durations_list = []
		elapsed = 0.0
		for i, dur in enumerate(dur_lists):
			flat = np.ravel(dur)
			if flat.size == 0:
				continue
			chunk_cumsum = np.cumsum(flat) + elapsed
			cum_durations_list.append(chunk_cumsum)
			if i < len(dur_lists) - 1:
				elapsed = chunk_cumsum[-1] + silence_duration
			else:
				elapsed = chunk_cumsum[-1]

		all_durations = np.concatenate(cum_durations_list) if cum_durations_list else np.array([], dtype=np.float32)
		bytes_per_sec = self._tts.sample_rate * 2

		audio_data = np.clip(wav.squeeze() * 32767, -32768, 32767).astype(np.int16).tobytes()

		with self._generation_lock:
			if self._generation != job_generation:
				return False

		# Map index marks to playback time. supertonic-3's duration predictor
		# only exposes a single total duration per chunk (no per-token
		# durations), so we cannot place marks per character exactly. We map
		# each index proportionally to its character position within the
		# processed text, which gives smooth, continuous progress tracking
		# (good enough for caret/say-all) rather than snapping to start/end.
		total_time = float(all_durations[-1]) if len(all_durations) > 0 else 0.0
		text_len = max(len(processed_text), 1)
		indices_by_offset = {}
		audio_len = len(audio_data)

		for char_offset, index in index_map:
			frac = 0.0 if char_offset <= 0 else min(char_offset / text_len, 1.0)
			target_time = total_time * frac

			target_byte = int(target_time * bytes_per_sec)
			target_byte = target_byte - (target_byte % 2)
			if target_byte > audio_len:
				target_byte = audio_len

			if target_byte not in indices_by_offset:
				indices_by_offset[target_byte] = []
			indices_by_offset[target_byte].append(index)

		sorted_offsets = sorted(indices_by_offset.keys())
		last_fed_byte = 0

		for offset in sorted_offsets:
			with self._generation_lock:
				if self._generation != job_generation:
					return True

			indices = indices_by_offset[offset]

			if offset == 0:
				for idx in indices:
					synthIndexReached.notify(synth=self, index=idx)
				continue

			chunk_len = offset - last_fed_byte
			if chunk_len > 0:
				chunk = audio_data[last_fed_byte:offset]

				def on_done(idxs=indices):
					for i in idxs:
						synthIndexReached.notify(synth=self, index=i)

				self._player.feed(chunk, onDone=on_done)
				last_fed_byte = offset
			else:
				for idx in indices:
					synthIndexReached.notify(synth=self, index=idx)

		# Feed remaining audio.
		if last_fed_byte < len(audio_data):
			chunk = audio_data[last_fed_byte:]
			self._player.feed(chunk)
		return True

	def speak(self, speechSequence):
		# Split the sequence into same-language segments. NVDA inserts
		# LangChangeCommand items only when automatic language switching is on;
		# otherwise the whole sequence uses the manually selected language.
		segments = []
		current_lang = self._language
		text = ""
		index_map = []

		def flush():
			nonlocal text, index_map
			if text:
				segments.append((text, voices.normalize_lang(current_lang) or self._language, index_map))
			text = ""
			index_map = []

		for item in speechSequence:
			if isinstance(item, str):
				text += item
			elif isinstance(item, IndexCommand):
				index_map.append((len(text), item.index))
			elif isinstance(item, LangChangeCommand):
				# Close the current segment and switch language. A None lang
				# means "back to the NVDA default" -> use the manual setting.
				flush()
				current_lang = item.lang if item.lang else self._language
		flush()

		if not any(t.strip() for t, _l, _im in segments):
			synthDoneSpeaking.notify(synth=self)
			return

		with self._generation_lock:
			generation = self._generation

		self._job_queue.put((generation, segments, self._voice, self._rate, self._quality))

	def cancel(self):
		with self._generation_lock:
			self._generation += 1
		
		# Clear queue
		while not self._job_queue.empty():
			try:
				self._job_queue.get_nowait()
				self._job_queue.task_done()
			except queue.Empty:
				break
		
		self._player.stop()

	def pause(self, switch):
		self._player.pause(switch)

	def terminate(self):
		self._stop_event.set()
		self._player.stop()
		self._player.close()
		self._worker_thread.join()

	def _get_availableVoices(self):
		# Voices are the JSON style files installed in the user directory.
		# Voices are language-independent (the model is multilingual), so
		# VoiceInfo.language is left as None.
		result = {}
		for name in voices.list_installed_voices():
			result[name] = synthDriverHandler.VoiceInfo(name, voices.voice_label(name))
		return result

	def _get_voice(self):
		installed = voices.list_installed_voices()
		# Keep the reported voice consistent with what is actually installed.
		if self._voice not in installed and installed:
			self._voice = installed[0]
		return self._voice

	def _set_voice(self, value):
		# Refuse to switch to a voice that is not installed; keep the current one
		# (or fall back to the first installed voice) so we never end up pointing
		# at a missing style file.
		installed = voices.list_installed_voices()
		if value in installed:
			self._voice = value
		elif self._voice not in installed and installed:
			self._voice = installed[0]

	def _get_language(self):
		return self._language

	def _set_language(self, language):
		# Map the requested locale onto a supported model language. Unknown
		# locales fall back to English so the manual setting is always valid.
		code = voices.normalize_lang(language)
		if code and code != voices.UNKNOWN_LANGUAGE:
			self._language = code
		else:
			self._language = voices.DEFAULT_LANGUAGE

	def _get_availableLanguages(self):
		# NVDA's settings GUI and languageIsSupported expect an OrderedDict of
		# LanguageInfo keyed by language code (it calls .values() and iterates
		# the codes through normalizeLanguage). Returning a raw set crashes the
		# Speech Settings dialog and breaks automatic language switching.
		from collections import OrderedDict

		result = OrderedDict()
		for code in sorted(voices.available_locales()):
			result[code] = synthDriverHandler.LanguageInfo(code)
		return result

	def _get_rate(self):
		return self._rate

	def _set_rate(self, value):
		self._rate = value

	def _get_quality(self):
		return self._quality

	def _set_quality(self, value):
		self._quality = value

	supportedSettings = (
		NumericDriverSetting("quality", _("Speech Quality Control"), 1, 100, 5),
		synthDriverHandler.SynthDriver.VoiceSetting(),
		synthDriverHandler.SynthDriver.LanguageSetting(),
		synthDriverHandler.SynthDriver.RateSetting(),
	)
