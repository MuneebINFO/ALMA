# ALMA — Privacy Policy

*Covers both editions of ALMA. The **free edition** is what ships and what
runs unless you subscribe; **ALMA+** is
described in its own section below, because it sends more, and you should
know exactly what.*

## The short version

ALMA is a rule-based assistant that runs **on your computer**. In its
default configuration — the free edition, text mode — nothing you type or
that ALMA sees on your screen is sent anywhere. Voice mode, and ALMA+
if you subscribe, change that in specific, limited ways described
below, with no surprises.

## What ALMA can see, and why

To carry out commands like "close Chrome" or "click Subscribe", ALMA reads:

- **Window titles and screen layout** — which windows are open, on which
  monitor, so it acts only on the one you're working on.
- **Browser tab titles and, when a command needs it, the visible text of the
  active page** — to find the tab you asked for.
- **Your microphone audio** — only in voice mode, and only while actively
  listening for a command.
- **Your camera** — only when you ask for a picture, and only for that one
  frame. The camera is released immediately afterwards; ALMA has no preview
  and never keeps the device open.

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
| Photos taken with the camera | On request | Nothing — the image is written to your Pictures folder and goes nowhere else | — |
| ALMA+ — questions and image analysis | **Off** until you subscribe | See the section below | Anthropic, through ALMA's relay |
| Advanced fallback (`ollama`, `claude_code`) | **Off** by default | The question's text | A model running entirely on your machine (`ollama`, no network at all), or the Claude Code CLI under your own subscription (`claude_code`) |

Voice mode and everything below the first three rows are opt-in: you turn
them on yourself.

**The free edition never contacts a server operated by ALMA's developer.**
Subscribers do — that is what a subscription is, and it is described in full
below. If you never subscribe, no request of yours ever reaches us.

## ALMA+, in detail

ALMA+ is inactive until you subscribe through the Microsoft Store. There is
no other way to turn it on, and no key to obtain from anyone. Until you
subscribe, ALMA runs exactly as described above.

What is sent, and **only when you ask**:

- the text of a question that no local command could answer;
- **an image from your camera**, when you ask ALMA to look at something
  ("analyse ce que j'ai dans la main"). The whole frame is sent, not a crop.
  No picture is ever taken or sent unless you asked for one in that moment.

Nothing else. Your screen contents, window titles, notes, clipboard, and
command history are never sent — in either edition.

### Where it goes

Your requests pass through a **relay we operate**, which forwards them to
Anthropic under our key — that is the only way a subscription can work
without handing every subscriber a key of their own.

What the relay does with a request:

- it checks with Microsoft that your subscription is active, and counts the
  request against your monthly allowance;
- it forwards the question, or the image, to Anthropic and returns the answer;
- **it does not store the content of your requests, nor the images.** What is
  kept is a count per subscriber, which is what an allowance needs and nothing
  more.

We never see your Microsoft password or your payment details: the Store
handles the purchase, and hands the app only a signed token saying that your
subscription is valid. Cancelling returns ALMA to the free edition, which keeps working
exactly as before.

## What's stored, and where

Your settings, notes, reminders, and command history are saved locally:

- Running from source: inside the project folder.
- Running the packaged app (`Alma.exe`, or the Microsoft Store version):
  under `%LOCALAPPDATA%\Alma` on your own machine.

Nothing is uploaded, synced, or backed up by ALMA. Uninstalling the app (or
deleting that folder) removes all of it.

## No accounts, no telemetry, no ads

Neither edition requires an account with ALMA, collects analytics or
crash reports, or shows ads. There's no tracking of what you say to
ALMA or what it does on your screen, beyond the local history file you can
read and delete yourself.

## Third-party services referenced above

- [Open-Meteo](https://open-meteo.com) — see their own [terms](https://open-meteo.com/en/terms)
- Google Speech-to-Text (voice mode only, and replaceable by a fully offline engine) — see [Google's Privacy Policy](https://policies.google.com/privacy)
- Microsoft Edge neural text-to-speech — see [Microsoft's Privacy Statement](https://privacy.microsoft.com/privacystatement)
- Anthropic — ALMA+ requests, sent through our relay, and the Claude Code CLI when explicitly enabled — see [Anthropic's Privacy Policy](https://www.anthropic.com/legal/privacy)

## Changes to this policy

If ALMA's features change in a way that changes what data is read or sent,
this document will be updated and the update noted in the app's release
notes.

## Contact

Questions about this policy: open an issue on the project's repository, or
contact the developer at the address listed on the Microsoft Store listing.
