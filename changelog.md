# Changelog

## 1.3.0

- Numbers are now expanded to words in the active language before synthesis,
  because the neural model pronounces bare digit sequences poorly. For example
  Polish "masz 5 nowych wiadomości" is now spoken "masz pięć nowych
  wiadomości", and "2025" becomes "dwa tysiące dwadzieścia pięć".
- Uses the bundled num2words library, covering 26 of the 31 model languages
  (including Polish, Ukrainian, German, French, Russian…). The remaining five
  (Bulgarian, Greek, Estonian, Hindi, Croatian) fall back to raw digits until
  number words are available. Expansion follows the segment's language, so it
  works with automatic language switching too.

## 1.2.2

- Fixed garbled, sped-up "drunken" speech that occurred after the model was
  switched to the multilingual supertonic-3 engine. Voice style files are tied
  to a specific model; voices downloaded for the previous English-only model
  produce half-length, distorted audio when fed to supertonic-3, but did not
  raise any error (so nothing appeared in the log).
- Voices are now stamped with the model revision they were downloaded for. On
  start-up, any voices that do not match the bundled model are discarded
  automatically so they can be re-downloaded for the correct model. A fresh
  install is unaffected.

## 1.2.1

- Fixed a crash when opening NVDA's Speech settings while Supertonic was the
  active synthesizer. The list of available languages was returned as a plain
  set, but NVDA expects an ordered mapping of language descriptions; this made
  the settings dialog (and the synth settings ring language item) error out.
- The language list is now reported to NVDA in the correct form, so automatic
  language switching and the manual Language setting work as intended.

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

