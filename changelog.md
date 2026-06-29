# Changelog

## 1.1.0

- Voice styles are no longer bundled with the add-on. The shared ONNX model is
  still shipped, but individual voices are downloaded on demand, keeping the
  add-on download small.
- Added a **voice manager** (NVDA menu > Tools > Supertonic voice manager...) to
  download, delete and refresh the official Supertonic voices (M1-M5, F1-F5).
  Downloaded voices are stored in the NVDA user configuration and survive
  add-on updates.
- Supertonic now only appears in NVDA's synthesizer list when at least one
  voice is installed, so it is impossible to switch to it without a usable
  voice (even via the synthesizer ring).
- The active voice falls back safely if its style file is removed while in use.

## 1.0.0

- Initial release of Supertonic TTS for NVDA.
