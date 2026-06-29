"""Shared voice-management logic for the Supertonic NVDA add-on.

The ONNX model is shipped inside the add-on bundle, but the individual voice
styles (small JSON files holding the style vectors) are *not* bundled. They are
downloaded on demand from the official Hugging Face repository
(``Supertone/supertonic``) into a writable directory under the NVDA user
configuration, so they survive add-on updates.

This module is imported by both the synth driver (``synthDrivers.supertonic``)
and the global plugin (``globalPlugins.supertonic``). It deliberately contains
no NVDA-GUI code so the logic can be unit tested outside NVDA.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Make the bundled third-party libraries (huggingface_hub, numpy, ...) importable.
_LIBS_PATH = os.path.join(os.path.dirname(__file__), "libs")
if _LIBS_PATH not in sys.path:
	sys.path.insert(0, _LIBS_PATH)

# Hugging Face source of the official voices. Kept in sync with
# ``supertonic.config`` (DEFAULT_MODEL_REPO / DEFAULT_MODEL_REVISION).
HF_REPO_ID = "Supertone/supertonic"
HF_REVISION = "v1.0.0"
# Sub-directory inside the HF repo (and inside our user directory) holding voices.
VOICE_SUBDIR = "voice_styles"

# The official catalogue. The HF repo ships exactly these ten voices. We keep a
# static fallback so the manager works offline, but try to refresh it live from
# the Hugging Face API when network is available (see list_official_voices()).
_OFFICIAL_VOICE_FALLBACK = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]


def voice_label(name: str) -> str:
	"""Return a human-friendly label for a voice id (e.g. ``M1`` -> ``M1 (Male 1)``)."""
	if len(name) >= 2 and name[0] in ("M", "F") and name[1:].isdigit():
		gender = _("Male") if name[0] == "M" else _("Female")
		return f"{name} ({gender} {name[1:]})"
	return name


# ``_`` may not be defined when running outside NVDA (tests). Provide a no-op.
try:  # pragma: no cover - trivial guard
	_  # type: ignore[name-defined]
except NameError:  # pragma: no cover
	def _(text: str) -> str:  # type: ignore[no-redef]
		return text


def get_bundle_model_dir() -> Path:
	"""Directory shipped inside the add-on that holds the ONNX model files."""
	return Path(__file__).parent / "models"


def get_user_voices_dir() -> Path:
	"""Writable directory where downloaded voice styles are stored.

	Located under the NVDA user configuration so it persists across add-on
	updates and reinstalls. Falls back to a path next to this file when NVDA's
	config machinery is unavailable (e.g. during unit tests).
	"""
	config_path: Optional[str] = None
	try:
		import globalVars  # type: ignore[import-not-found]

		config_path = globalVars.appArgs.configPath
	except Exception:
		config_path = None

	if not config_path:
		config_path = os.environ.get(
			"SUPERTONIC_USER_DIR", str(Path(__file__).parent / "_user_voices")
		)

	voices_dir = Path(config_path) / "supertonic" / VOICE_SUBDIR
	voices_dir.mkdir(parents=True, exist_ok=True)
	return voices_dir


def model_present() -> bool:
	"""True if all required ONNX model files are present in the bundle.

	Mirrors ``supertonic.loader.has_all_onnx_modules`` without importing the
	heavy ``supertonic``/onnxruntime stack.
	"""
	model_dir = get_bundle_model_dir()
	required = [
		model_dir / "onnx" / "duration_predictor.onnx",
		model_dir / "onnx" / "text_encoder.onnx",
		model_dir / "onnx" / "vector_estimator.onnx",
		model_dir / "onnx" / "vocoder.onnx",
	]
	return all(p.exists() for p in required)


def _is_valid_voice_file(path: Path) -> bool:
	"""Validate that *path* is a well-formed Supertonic voice style file.

	Mirrors ``supertonic.utils.validate_voice_style_format`` but inlined to
	avoid importing the heavy ``supertonic`` package (numpy/onnxruntime) just to
	check two JSON keys.
	"""
	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
		if not isinstance(data, dict):
			return False
		for key in ("style_ttl", "style_dp"):
			section = data.get(key)
			if not isinstance(section, dict):
				return False
			if "dims" not in section or "data" not in section:
				return False
		return True
	except Exception:
		return False


def list_installed_voices() -> list[str]:
	"""Sorted names of voices currently installed in the user directory."""
	voices_dir = get_user_voices_dir()
	names = []
	for p in voices_dir.glob("*.json"):
		names.append(p.stem)
	return sorted(names)


def is_voice_installed(name: str) -> bool:
	return (get_user_voices_dir() / f"{name}.json").exists()


def voice_path(name: str) -> Path:
	"""Absolute path to an installed voice's JSON file."""
	return get_user_voices_dir() / f"{name}.json"


def list_official_voices() -> list[str]:
	"""Names of the official voices available for download.

	Tries the live Hugging Face API first; on any failure falls back to the
	static catalogue so the manager remains usable offline.
	"""
	try:
		from huggingface_hub import HfApi

		api = HfApi()
		files = api.list_repo_files(repo_id=HF_REPO_ID, revision=HF_REVISION)
		prefix = f"{VOICE_SUBDIR}/"
		names = sorted(
			Path(f).stem
			for f in files
			if f.startswith(prefix) and f.endswith(".json")
		)
		if names:
			return names
	except Exception:
		pass
	return list(_OFFICIAL_VOICE_FALLBACK)


def list_downloadable_voices() -> list[str]:
	"""Official voices that are not yet installed."""
	installed = set(list_installed_voices())
	return [v for v in list_official_voices() if v not in installed]


def download_voice(name: str) -> Path:
	"""Download a single official voice from Hugging Face into the user directory.

	Returns the path to the installed file. Raises on failure (and leaves the
	user directory untouched if the download or validation fails).
	"""
	from huggingface_hub import hf_hub_download

	filename = f"{VOICE_SUBDIR}/{name}.json"
	dest = voice_path(name)

	# Download into an isolated temp dir, validate, then atomically move.
	tmp_root = tempfile.mkdtemp(prefix="supertonic_dl_")
	try:
		downloaded = hf_hub_download(
			repo_id=HF_REPO_ID,
			filename=filename,
			revision=HF_REVISION,
			local_dir=tmp_root,
		)
		downloaded_path = Path(downloaded)
		if not _is_valid_voice_file(downloaded_path):
			raise ValueError(
				f"Downloaded voice '{name}' failed validation (unexpected format)."
			)
		dest.parent.mkdir(parents=True, exist_ok=True)
		# shutil.move replaces an existing file on the same filesystem.
		tmp_final = dest.parent / f".{name}.json.tmp"
		shutil.copyfile(downloaded_path, tmp_final)
		os.replace(tmp_final, dest)
		return dest
	finally:
		shutil.rmtree(tmp_root, ignore_errors=True)


def delete_voice(name: str) -> bool:
	"""Delete an installed voice. Returns True if a file was removed."""
	p = voice_path(name)
	if p.exists():
		p.unlink()
		return True
	return False


def is_ready() -> bool:
	"""True when the synthesizer can actually speak: model present AND >=1 voice.

	The synth driver's ``check()`` relies on this so NVDA never offers Supertonic
	for selection while it has no usable voice.
	"""
	return model_present() and len(list_installed_voices()) > 0
