# ALMA — Privacy Policy

*Applies to the free, local version of ALMA. If a paid tier is introduced
later, this document will be updated before that tier ships, and the
Microsoft Store listing will link to the version in effect at the time.*

## The short version

ALMA is a rule-based assistant that runs **on your computer**. In its
default configuration (text mode, no AI fallback), nothing you type or that
ALMA sees on your screen is sent anywhere. Voice mode and the optional AI
fallback change that in specific, limited ways — described below, with no
surprises.

## What ALMA can see, and why

To carry out commands like "close Chrome" or "click Subscribe", ALMA reads:

- **Window titles and screen layout** — which windows are open, on which
  monitor, so it acts only on the one you're working on.
- **Browser tab titles and, when a command needs it, the visible text of the
  active page** — to find the tab you asked for, or to read back an answer
  (e.g. Google's AI Mode results, when that fallback is enabled).
- **Your microphone audio** — only in voice mode, and only while actively
  listening for a command.

This reading happens locally, through the standard Windows accessibility
APIs (UI Automation) — the same technology used by screen readers. **None
of it is transmitted anywhere by ALMA itself.** Data only leaves your
device through the specific network calls listed below.

## What leaves your device, and when

| Feature | Default state | What's sent | To whom |
|---|---|---|---|
| Text commands, local rules | Always on | Nothing | — |
| Weather ("quel temps fait-il") | Always on | City name | [Open-Meteo](https://open-meteo.com) — free, no account, no API key |
| Voice mode — speech recognition | **Off** by default | Your spoken audio | Google's speech API, unless you switch `stt_engine` to `whisper` or `vosk` (fully offline, on-device) |
| Voice mode — spoken replies | **Off** by default | The text ALMA is about to say | Microsoft's Edge neural voice service, unless you switch `voice.engine` to `sapi5` (fully offline, on-device) |
| AI fallback (questions with no matching command) | **Off** by default | The question's text | Depends on which provider you configure: a Google search page opened in a hidden window (`gemini`), the Claude Code CLI under your own Anthropic subscription (`claude_code`), or a model running entirely on your machine (`ollama`, no network at all) |

Voice mode and the AI fallback are both opt-in: you turn them on yourself,
in `config.yaml` or with a command-line flag. The free version never
contacts a server operated by ALMA's developer — there isn't one.

## What's stored, and where

Your settings, notes, reminders, and command history are saved locally:

- Running from source: inside the project folder.
- Running the packaged app (`Alma.exe`, or the Microsoft Store version):
  under `%LOCALAPPDATA%\Alma` on your own machine.

Nothing is uploaded, synced, or backed up by ALMA. Uninstalling the app (or
deleting that folder) removes all of it.

## No accounts, no telemetry, no ads

The free version doesn't require an account, doesn't collect analytics or
crash reports, and doesn't show ads. There's no tracking of what you say to
ALMA or what it does on your screen, beyond the local history file you can
read and delete yourself.

## Third-party services referenced above

- [Open-Meteo](https://open-meteo.com) — see their own [terms](https://open-meteo.com/en/terms)
- Google Speech-to-Text and Google Search (AI Mode) — see [Google's Privacy Policy](https://policies.google.com/privacy)
- Microsoft Edge neural text-to-speech — see [Microsoft's Privacy Statement](https://privacy.microsoft.com/privacystatement)
- Anthropic (Claude Code CLI, when explicitly enabled) — see [Anthropic's Privacy Policy](https://www.anthropic.com/legal/privacy)

## Changes to this policy

If ALMA's features change in a way that changes what data is read or sent,
this document will be updated and the update noted in the app's release
notes.

## Contact

Questions about this policy: open an issue on the project's repository, or
contact the developer at the address listed on the Microsoft Store listing.
