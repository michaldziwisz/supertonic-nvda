# Supertonic TTS for NVDA

Warning: this is alpha quality software. Expect issues.

This add-on provides a synthesizer driver for the Supertonic text-to-speech engine in NVDA.
Supertonic is a high-performance, on-device TTS powered by ONNX Runtime. However, while extremely fast for its sound quality, it's still not quite fast enough for realtime use. Consider using this for say all, and nothing else.

## Features

- High-quality, lightning-fast speech synthesis.
- On-device processing (no internet required for synthesis itself).
- Multiple official voice styles (M1-M5, F1-F5), downloaded on demand.
- A built-in voice manager to download, delete and switch voices.
- Control over speech speed and quality.

## Voices

To keep the add-on download small, voice styles are **not** bundled. The ONNX
model (shared by every voice) ships with the add-on, but you download the
individual voices yourself the first time you use it.

### Voice manager

Open **NVDA menu > Tools > Supertonic voice manager...** to:

- See which voices are installed and which official voices are available.
- Download a voice (it is fetched from the official Hugging Face repository).
- Delete a voice you no longer want.
- Refresh the list of available voices.

Downloaded voices are stored in your NVDA user configuration, so they survive
add-on updates and reinstalls. You need an internet connection only while
downloading voices; synthesis itself is fully offline.

> **Important:** Supertonic only appears in NVDA's synthesizer list once at
> least one voice is installed. If you delete every voice, Supertonic becomes
> unavailable for selection until you download a voice again. This prevents you
> from ever switching to a synthesizer that has no voice to speak with.

### Switching voices

Once you have more than one voice installed, change between them in NVDA's
Speech settings (the **Voice** setting), exactly like with any other
synthesizer.

## Issues

- Speed only pretends to work. Increasing speed makes it skip words instead of actually speaking faster.
- Pitch can't be changed
- I suspect we don't need to bundle quite as many Python packages as we do, but NVDA includes weird versions of things and I'm scared

## Settings

The following settings are available in NVDA's Speech settings dialog when Supertonic is selected as the synthesizer:

### Voice
Choose from several available voice styles (M1-M5, F1-F5).

### Rate (Speech Speed Control)
Adjust the speed of the speech.

### Speech Quality Control
Adjust the number of synthesis steps (1-100). Higher values result in better quality but slower synthesis. The default value of 5 provides an excellent balance between speed and quality.

## Requirements

- NVDA 2026.1 or later.
- Windows 10/11 (x64).