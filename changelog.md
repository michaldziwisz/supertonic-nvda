# Changelog

## 1.2.0

- Switched to the multilingual **supertonic-3** model, adding support for 31
  languages including Polish and Ukrainian. The same speaker voices (M1-M5,
  F1-F5) now speak in whichever language the text is in.
- Added **automatic language switching**: when NVDA's "Automatic language
  switching" option is enabled, each piece of text is spoken in its own
  language. When it is disabled, the new **Language** setting (in Speech
  settings) selects the language manually.
- The library was updated to Supertonic 1.3.1, which wraps text with a
  language token so accented characters (e.g. ą, ę, ż) are pronounced
  correctly.
- Note: supertonic-3 reports only a total duration per utterance, so in-phrase
  cursor tracking is approximated proportionally to character position rather
  than per word. Sentence/utterance boundaries (say all) are unaffected.

## 1.1.0

- Voice styles are no longer bundled with the add-on. The shared ONNX model is
  still shipped, but individual voices are downloaded on demand, keeping the
  add-on download small.
- Added a **voice manager** (NVDA menu > Tools > Supertonic voice manager...) to
  download, delete and refresh the official Supertonic voices.
  Downloaded voices are stored in the NVDA user configuration and survive
  add-on updates.
- Supertonic now only appears in NVDA's synthesizer list when at least one
  voice is installed, so it is impossible to switch to it without a usable
  voice (even via the synthesizer ring).
- The active voice falls back safely if its style file is removed while in use.

## 1.0.0

- Initial release of Supertonic TTS for NVDA.

