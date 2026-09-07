# ALMA — a local voice assistant for Windows

> **A**utonomous **L**ocal **M**achine **A**ssistant

A personal assistant you drive with your voice, running **entirely on your own
machine**. Say "**ALMA**" to wake it, then speak.

> **No paid generative AI.** ALMA's "brain" is a local rule engine (regular
> expressions plus typo-tolerant keyword matching), not a remote LLM. No API
> key, no subscription, no bill. See
> [Why no AI](#why-no-ai-and-how-to-add-one-later).

---

## Contents

- [Quick start](#quick-start)
- [The voice app](#the-voice-app)
- [The voice](#the-voice)
- [If ALMA cannot hear you](#if-alma-cannot-hear-you)
- [Building an executable](#building-an-executable)
- [What ALMA can do](#what-alma-can-do)
- [Configuration](#configuration)
- [Adding a command](#adding-a-command)
- [Architecture](#architecture)
- [Tests](#tests)
- [Why no AI](#why-no-ai-and-how-to-add-one-later)
- [Planned extensions](#planned-extensions)
- [Troubleshooting](#troubleshooting)

---

## Quick start

Run this **from Windows** — PowerShell or a terminal, not WSL. ALMA drives
Windows itself (microphone, volume, applications), so it cannot work from a
Linux subsystem.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

That is enough: **no configuration file is required**, ALMA starts in text mode
with sensible defaults.

```
[text mode] Type your request. "aide" for the list, "quitte" to exit.
ALMA > Good evening, at your service. Type "aide" to see what I can do.
You > ouvre Chrome
ALMA > J'ouvre chrome.
```

For the full voice experience, install the audio dependencies and create the
desktop shortcut:

```bash
pip install -r requirements-voice.txt
python creer_raccourci.py --bureau
```

> **ALMA speaks French.** Commands, replies and the interface are in French —
> that is the language it was designed for. This README is in English; the
> assistant is not.

### Launch options

| Command | What it does |
|---|---|
| `Alma.lnk` / `Alma.bat` | **voice app** (continuous listening, animated orb) |
| `python gui.py` | same, from a terminal |
| `python main.py` | text mode in the console |
| `python main.py -c "ouvre Chrome"` | run one command and exit |
| `python main.py --list-commands` | print every command |
| `python main.py --list-voices` | list the voices installed on Windows |
| `python diagnostic_micro.py` | check that the microphone picks up your voice |
| `python main.py --debug` | show debug logs |

> `-c` is ideal for a Windows shortcut or a macro key — for example a key bound
> to `python main.py -c "capture"`.

---

## The voice app

ALMA is a voice application first. It listens continuously from the moment it
starts, but stays passive: it only acts once you say its name.

```bash
python creer_raccourci.py --bureau
```

This creates an `Alma` shortcut, with icon, in the project folder and on your
desktop. Double-click it and the app opens, calibrates the microphone and starts
listening. There is no text field — everything goes through speech.

### Three ways to talk to it

| You say | What happens |
|---|---|
| "**Alma, quelle heure est-il**" | the command runs immediately |
| "**Alma**" then a pause | it answers "Oui ?" and waits for your request |
| "il fait beau aujourd'hui" | **ignored** — no accidental triggering |

The name is still recognised when the transcription mangles it (*almat*,
*almas*, *halma*), but a nearby word such as *alba* will not wake it.

### The listening session

Saying the name opens a **session that lasts one minute**, and every sentence
you say restarts the countdown. Inside it you speak normally, without repeating
the name:

```
You  — Alma, va sur YouTube
ALMA — Je bascule sur l'onglet youtube.        (60 s)
You  — recherche Damso                          ← no wake word needed
ALMA — Je cherche « Damso » sur youtube.       (countdown restarts)
You  — stop
ALMA — Très bien.                               ← session closed at once
```

The session ends after a minute of silence, or immediately if you say **"stop"**
(also "c'est bon", "laisse tomber", "annule", "silence"). Once closed, nothing
runs until you say the name again — so a conversation in the room can never
trigger anything.

Length is set by `voice.armed_seconds` (60 by default).

### Following the conversation

ALMA remembers what you were just talking about. After "va sur YouTube",
a bare "recherche Damso" searches **on YouTube**, in that tab — not on Google.
Naming another site moves the context:

```
va sur Netflix        →  cherche Interstellar   searches Netflix
va sur YouTube        →  mets du lofi           plays on YouTube
```

That memory lives exactly as long as the session. Once it expires, "recherche
Damso" is an ordinary web search again — so a request made an hour later never
lands on the wrong site by accident.

### Renaming the assistant

The wake word comes **entirely from configuration** — no code to touch:

```yaml
general:
  assistant_name: ALMA       # displayed name
  wake_word: alma            # spoken name
  wake_variants: []          # extra transcriptions to accept
  wake_require_prefix: false # true = require "OK ALMA" rather than "ALMA" alone
```

Two details that matter for reliability:

**Tolerance scales with the length of the name.** A four-letter name inevitably
shares three letters out of four with dozens of words — *alma* and *alba* are
75 % similar. A uniform tolerance would wake the assistant constantly. Below
five letters an exact match is required; fuzziness is only allowed on names long
enough to absorb it.

**Spelling variants are generated automatically** (silent endings, initial *h*,
common letter confusions). Coverage is not exhaustive — if the assistant stays
silent while you can see your sentence under the orb, add the spelling you
observed to `wake_variants`.

Finally, "salut ALMA" and "bonjour ALMA" remain **greetings**: the polite word is
passed through as a command, unlike the technical prefixes "ok" and "dis", which
are simply dropped.

### The orb

The ring deforms with the **real level of your microphone**, surrounded by
rotating arcs and a halo, so you can see at a glance whether your voice is being
picked up.

| Colour | State |
|---|---|
| purple | measuring background noise |
| deep blue | listening, waiting for the wake word |
| **cyan, rippling ring** | **voice detected** |
| green | awake — waiting for your request |
| amber | running the command |
| violet | replying |
| red | error (no microphone, etc.) |

---

## The voice

Two engines, selected automatically:

| Engine | Quality | Cost | Network |
|---|---|---|---|
| **edge-tts** (default) | **neural** female voice, very natural | free, **no key** | required |
| **SAPI5** (automatic fallback) | local Windows voice, more robotic | free | none |

The default voice is **Denise** (`fr-FR-DeniseNeural`). To change it:

```yaml
voice:
  neural_voice: fr-BE-CharlineNeural   # Belgium
  neural_rate: "+0%"                   # "+15%" to speak faster
```

Other French female voices: `fr-FR-EloiseNeural`, `fr-CH-ArianeNeural`,
`fr-CA-SylvieNeural`. To force offline mode: `voice.engine: sapi5`.

Short replies ("Oui ?", "Je vous écoute") are **synthesised at startup** and
replayed from a cache, so the answer to the wake word is instant instead of
waiting on a network round trip.

---

## If ALMA cannot hear you

```bash
python diagnostic_micro.py
```

A live meter appears: speak, and the bar should cross the threshold marker. At
the end a verdict tells you whether the settings are right — and if not, the
exact value to put in `config.yaml`.

The two usual causes:

1. **You are running under WSL or Linux.** ALMA is a Windows application: from
   WSL there is no Windows microphone, no volume control and no way to launch
   applications. Start it from PowerShell, not Ubuntu. This is also why
   `pip install PyAudio` fails there with `portaudio.h: No such file` — on
   Windows a prebuilt wheel installs with nothing to compile.
2. **The microphone gain is low.** Many built-in microphones capture very
   quietly. The threshold is adaptive (derived from the measured background
   noise), but you can lower it:
   ```yaml
   voice:
     min_threshold: 0.002   # default 0.004; lower is more sensitive
     noise_factor: 3.5      # margin above background noise
   ```
   Also raise the input volume in Windows Settings > System > Sound.

---

## Building an executable

```bash
pip install -r requirements-build.txt
python build_exe.py
```

This produces `dist/Alma.exe` (~54 MB, self-contained, no Python needed on the
target machine).

> **Windows Smart App Control blocks unsigned executables.** If it is enabled,
> the executable builds correctly but Windows refuses to run it
> (`WinError 4551`). This is not specific to ALMA — every unsigned PyInstaller
> binary is treated the same way.
>
> **Use the shortcut instead** (`python creer_raccourci.py`): it goes through
> `pythonw.exe`, which is signed and therefore allowed, and gives you exactly
> the same application. The `.exe` is only worth building to hand ALMA to
> someone else — and you would then need to sign it, or turn Smart App Control
> off (**note: re-enabling it requires reinstalling Windows**).

---

## What ALMA can do

Every command works **in French and English**, accepts several phrasings, and
tolerates typos (`ouvre gogle chrome` works). You can prefix any sentence with
"ALMA, …" — the wake word is stripped.

### Applications
```
ouvre Chrome                  lance VS Code
ouvre la calculatrice         démarre le bloc-notes
ferme Chrome                  quelles applications connais-tu
```

### Websites
```
ouvre YouTube                 va sur GitHub
ouvre Gmail                   ouvre Netflix
```

### Search
```
cherche les dernières nouvelles sur l'IA sur Google
ouvre YouTube et cherche lofi hip hop
demande à Claude comment fonctionne un moteur de recherche
qui est Marie Curie                    (Wikipedia summary, read aloud)
cherche Alan Turing sur Wikipedia
traduis bonjour le monde en anglais
cherche des images de montagne
où est la gare centrale
```

### Media, per screen or per app

ALMA controls each player **separately**, through the Windows media sessions
API. Global media keys only ever reach one application: if Chrome and Firefox
are both playing, they cannot be told apart. Media sessions can.

```
mets pause sur l'écran 2              pause what is playing on screen 2
arrête la vidéo sur le deuxième écran
reprends la lecture sur l'écran 2
mets tout en pause                    every player at once
qu'est-ce qui joue                    lists what is playing, and where
pause / chanson suivante / précédente
```

Screens are numbered left to right, then top to bottom, so "écran 1" is always
the leftmost. "écran de droite", "le deuxième écran" and "l'autre écran" work
too.

Players that expose a media session (Chrome, Firefox, Spotify, Edge…) are paused
precisely, without stealing focus. Streaming sites whose custom player registers
no session fall back to bringing the window forward and sending the pause key —
the same thing you would do by hand.

### Opening a site and searching inside it

```
va sur Netflix et mets Fast and Furious
mets Interstellar sur Prime Video
sur YouTube, mets lofi hip hop
va sur Disney+ et cherche Star Wars
```

ALMA first looks for a browser window **already showing that site**. If it finds
one, it brings that window forward and navigates its current tab, instead of
opening yet another one — and it stays in the browser where the site was open,
not in your default browser. Otherwise it opens the site normally.

Around 30 platforms support in-site search: Netflix, YouTube, Prime Video,
Disney+, Crunchyroll, Twitch, Spotify, Deezer, SoundCloud, Dailymotion, TikTok,
IMDb, AlloCiné, RTBF Auvio, france.tv, Amazon, eBay, Leboncoin, GitHub, Reddit,
LinkedIn, Pinterest, Booking and more. Add your own with a `search_url` in
`config.yaml`:

```yaml
websites:
  monsite:
    aliases: [mon site]
    url: https://example.com
    search_url: https://example.com/search?q={q}
```

**Background tabs are found too.** A window title only ever reflects the
*active* tab, so ALMA also reads the tab strip through UI Automation — the
accessibility API screen readers use. Saying "va sur l'onglet YouTube" switches
to the YouTube tab even when TikTok is the one on screen, instead of opening a
duplicate.

Simply showing a site never reloads it: "va sur YouTube" activates the tab and
leaves your video playing. Navigation only happens when you actually ask for
something ("mets X sur YouTube").

> **Two limitations worth knowing.** Firefox only exposes its active tab to UI
> Automation, so background tabs are found in Chromium browsers (Chrome, Edge,
> Brave, Vivaldi) but not in Firefox. And a tab is matched on its *title*: a
> GitHub tab named "Your Repositories" contains no clue that it is GitHub, so
> ALMA will open a new one.

### Scrolling and clicking

```
scrolle                            scroll down (the default)
fais défiler vers le haut          scroll up
descends / remonte la page
arrête                             stops the scrolling

clique sur Abonnements             clicks the element with that name
clique sur la vidéo Interstellar   names the kind, then the title
clique sur le film Interstellar
clique sur le bouton lecture       restricts the search to buttons
clique sur la première vidéo       picks by position instead
```

Scrolling is **continuous**: the command returns immediately and ALMA keeps
listening, so you can stop it with a word. Speed is measured at roughly
**365 pixels per second** with the default settings — a comfortable reading
pace. Two wheel notches per tick already exceed 1300 px/s, which is unreadable,
so raise it carefully:

```yaml
interaction:
  scroll_crans: 1        # wheel notches per tick
  scroll_intervalle: 0.25
```

Saying "arrête" while scrolling **stops the scrolling and keeps the session
open** — it does not hang up on you. It only closes the session when nothing is
running.

Clicking goes through the accessibility API: elements are matched by their
name, preferring an exact match, then the shortest one containing your words —
so "Damso" targets the link named *Damso* rather than an 80-character title
that merely mentions him. Only elements **actually on screen** are considered;
anything scrolled out of view is ignored, since clicking it would land
somewhere else.

**Naming the kind narrows the search.** "clique sur le bouton lecture" looks at
buttons first, so it will not land on a video title that happens to contain the
word. Recognised kinds: *bouton, lien, image, vignette, onglet, case, champ,
vidéo, film, série, épisode, clip, chanson, musique, titre, résultat*. If
nothing matches within that kind, ALMA widens the search rather than giving up.

**English labels are matched too.** Interfaces are often in English even when
you speak French, so "le bouton lecture" also finds *Play*, "plein écran" finds
*Full screen*, and "abonnements" finds *Subscriptions*.

Pages load asynchronously, so if nothing is found ALMA waits a moment and looks
once more before answering.

> "clique sur la première vidéo" is a heuristic: nothing distinguishes a video
> from any other link, so ALMA takes the elements in reading order and skips
> short labels, which are almost always navigation buttons. Naming what you
> want is more reliable.

### System
```
mets le volume à 30%          coupe le son / remets le son
monte le son                  baisse le volume
mets la luminosité à 50%      prends une capture d'écran
verrouille l'ordinateur       ouvre le dossier téléchargements
mets l'ordinateur en veille   éteins l'ordinateur      (asks for confirmation)
redémarre l'ordinateur        annule l'extinction
```

### Productivity
```
note que je dois rappeler ma banque demain
lis mes notes                 supprime la note 2
rappelle-moi dans 10 minutes de sortir le gâteau
lance un minuteur de 5 minutes
mes rappels                   annule mes rappels
lis le presse-papiers         copie ce texte dans le presse-papiers
```

### Information
```
quelle heure est-il           quel jour sommes-nous
quel temps fait-il à Bruxelles                (free weather API, no key)
```

### Music
```
mets de la musique            lance la vidéo
pause                         mets pause à la vidéo
chanson suivante              chanson précédente
arrête la musique
```

"lance la vidéo" and "mets pause à la vidéo" are **explicit**: the first only
resumes, the second only pauses. Bare "pause" or "play" stays a toggle. The
object must end the sentence — "lance la vidéo Interstellar" names a specific
video, so it is treated as a search rather than a playback command.

### Editing (applies to the app in front)
```
copie la sélection            colle
coupe la sélection            annule la dernière action
rétablis                      sélectionne tout
enregistre                    imprime la page
cherche dans la page          écris bonjour tout le monde
valide                        échap
```

### Windows and tabs
```
ouvre un nouvel onglet        ferme cet onglet
rouvre l'onglet fermé         onglet suivant / précédent
actualise la page             page précédente / suivante
zoom avant / arrière / normal plein écran
minimise / agrandis la fenêtre
change de fenêtre             affiche le bureau
capture une zone
```

### Machine
```
niveau de batterie            espace libre sur le disque
mon adresse IP                vide la corbeille
```

### Arithmetic and chance
```
combien font 15 fois 4        calcule 200 divisé par 8
pile ou face                  lance un dé
donne-moi un nombre entre 1 et 100
```

Arithmetic is parsed and evaluated through a **restricted** syntax tree: only
numbers and the four operations are accepted, so nothing else can be executed
even if the sentence contained it.

### Miscellaneous
```
aide / que peux-tu faire      raconte-moi une blague
répète                        historique
bonjour / comment ça va       au revoir ALMA
```

`aide` always prints the complete, up-to-date list.

---

## Configuration

`config.yaml` is **optional**. To customise:

```bash
copy config.yaml.example config.yaml
```

You do not need to copy everything: the merge is recursive, so keep only what
you change.

### Adding an application

```yaml
applications:
  obsidian:
    aliases: [obsidian, mes notes markdown]
    paths: ["%LOCALAPPDATA%/Obsidian/Obsidian.exe"]
    process: Obsidian.exe
```

- `aliases` — every way you might name it out loud;
- `paths` — candidates tried in order: full path, executable on `PATH`, or a
  shell URI (`ms-settings:`). Windows variables (`%ProgramFiles%`, `%APPDATA%`…)
  are expanded;
- `process` — process name, used by "ferme X".

### Adding a website

```yaml
websites:
  intranet:
    aliases: [intranet, le portail]
    url: https://intranet.example.be
```

### Secrets

The `.env` file (see `.env.example`) is optional too: **no API key is needed**
for anything described above.

---

## The command specification

[`commandes.json`](commandes.json) lists every action and the phrases that
trigger it, in plain French. It is not read at runtime — it is the
**specification**, and a test enforces it: every phrase in the file must reach
a real command, and reach the one the file describes.

```json
{
  "action": "Ouvrir un site et y lancer une recherche",
  "phrases": [
    "va sur X et mets Y",
    "mets X sur Y",
    "cherche X sur Y"
  ]
}
```

`X` and `Y` mark the variable parts. Add a phrasing to the file, run `pytest`,
and a failure tells you the code does not understand it yet.

## Adding a command

There is **no large if/elif block** to edit. One command is one decorated
function, discovered automatically at startup.

Create or edit a file in `commands/`:

```python
# commands/perso.py
from core.context import CommandContext, Response
from core.registry import command


@command(
    name="cafe",
    patterns=[r"^(?:fais|prepare)\s+(?:moi\s+)?(?:un\s+)?cafe$"],
    keywords=[["cafe"]],                 # safety net if the regex misses
    category="Divers",
    description="Rappeler qu'il est l'heure du café",
    examples=["fais-moi un café"],
    priority=50,
)
def cafe(ctx: CommandContext) -> Response:
    """Docstring: used as the default description."""
    return Response(text="Je ne fais pas encore le café, mais j'y travaille.")
```

Then add the module name to `MODULES` in `commands/__init__.py` — that list is
what gets bundled into the executable. A test fails if you forget.

That is all: the command shows up in `aide` and is automatically covered by
`test_les_exemples_documentes_sont_routes_vers_leur_commande`.

### The `@command` decorator

| Parameter | Role |
|---|---|
| `patterns` | regular expressions matched against the **normalised** sentence (lowercase, accents folded, punctuation to spaces) |
| `keywords` | groups of words; a group matches when **all** of its words are present (typo-tolerant) |
| `priority` | the more specific the command, the higher it should be (tested first) |
| `guard` | optional predicate: return `False` and the router keeps looking |
| `sources` | where the command may be triggered from (`text`, `voice`, `gesture`) |

### Getting the arguments

`ctx.arg` (= `ctx.group(1)`) returns the captured text **exactly as the user
wrote it**, accents and capitals included — even though matching happened on a
simplified version. That is what lets "cherche des idées de repas sur Google"
actually search for `des idées de repas`.

### Destructive actions

Anything irreversible must go through a confirmation:

```python
if not ctx.confirm("Voulez-vous vraiment tout supprimer ?"):
    return Response(text="Annulé.")
```

---

## Architecture

```
alma/
├── main.py                 console entry point and CLI options
├── gui.py                  voice application (animated orb, Tkinter)
├── diagnostic_micro.py     level meter to check the microphone
├── creer_raccourci.py      creates the Windows shortcut with icon
├── build_exe.py            builds dist/Alma.exe (PyInstaller)
├── make_icon.py            generates assets/alma.ico
├── config.py               configuration (defaults built in)
├── config.yaml.example     documented configuration to copy
│
├── core/
│   ├── assistant.py        wires everything together; single handle() entry point
│   ├── router.py           intent routing engine (NO AI)
│   ├── registry.py         command registry (@command)
│   ├── context.py          Utterance / CommandContext / Response
│   ├── text_utils.py       aligned normalisation and fuzzy matching
│   ├── input_sources.py    input sources (text, voice, gestures later)
│   ├── wake.py             wake word and listening state machine
│   ├── desktop.py          screens, windows and focus
│   ├── browser_tabs.py     reads and activates browser tabs (UI Automation)
│   ├── media_control.py    per-application playback control
│   ├── interaction.py      continuous scrolling and clicking on screen
│   ├── tts.py              speech synthesis (neural, SAPI5 fallback)
│   ├── voice_neural.py     edge-tts neural voice
│   ├── stt.py              speech recognition and microphone level metering
│   ├── scheduler.py        reminders and timers
│   ├── storage.py          JSON storage (atomic writes)
│   ├── win_utils.py        Windows helpers (volume, screenshots…)
│   ├── ai_fallback.py      AI fallback facade — INACTIVE by default
│   └── providers/
│       └── claude_code_provider.py   delegation to the Claude Code CLI
│
├── commands/               one module per task category
│   ├── apps.py             open and close applications
│   ├── websites.py         open websites
│   ├── search.py           Google, YouTube, Wikipedia, Claude, translation
│   ├── system.py           volume, brightness, session, screenshots, folders
│   ├── productivity.py     notes, reminders, timers, clipboard
│   ├── info.py             time, date, weather
│   ├── media.py            music control
│   ├── smalltalk.py        greetings, jokes
│   └── misc.py             help, history, repeat, exit
│
├── data/                   notes.json, reminders.json, history.json
├── screenshots/            timestamped captures
└── tests/                  pytest suite
```

### How a request flows

```
      keyboard text ─┐
       microphone ───┼──► Utterance(raw, norm, source)
   gestures (later) ─┘              │
                                    ▼
                         Router.resolve()          ← regex, then keywords
                                    │
                   ┌────────────────┴────────────────┐
                 match                            no match
                   │                                 │
                   ▼                                 ▼
           handler(ctx) ──► Response          ai_fallback (polite message)
                   │
                   ▼
           display + speech synthesis + history
```

**The key point:** all three input sources produce the same `Utterance` object
and go through the same router. Business logic exists in exactly one place.

### Aligned normalisation

`core/text_utils.normalize()` returns a string of **identical length** to the
original (lowercase, accents folded, punctuation turned into spaces). Captured
group positions therefore remain valid in the original string, which is what
allows simple matching **without losing** the accents and capitalisation of the
arguments.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

251 tests cover:

- normalisation and fuzzy matching (`test_text_utils.py`);
- **routing**: every sentence must reach the right handler, including the
  ambiguous cases (`ouvre Chrome` → application, `ouvre YouTube` → website,
  `quitte Spotify` → close Spotify rather than quit ALMA) — `test_router.py`;
- command behaviour: notes, reminders, confirmations, history, resilience to a
  failing handler (`test_commands.py`);
- **the wake word**: name plus command, name alone, expiry of the receptive
  window, transcription variants, and above all **no triggering** on ambient
  conversation (`test_wake.py`);
- **the "no AI without your consent" guarantee**: with `enabled: false`, an
  unrecognised request gets a polite message **without ever launching `claude`**
  and without any network call (`test_ai_fallback.py`);
- **screen targeting**: with two players running on two screens, only the one
  on the requested screen is paused; the keyboard fallback is used when no media
  session exists (`test_desktop_media.py`);
- **naming a target**: "la vidéo Interstellar" searches for *Interstellar*,
  the kind restricts the search, and English labels are matched
  (`test_interaction.py`);
- **scrolling and clicking**: default direction, cursor restored afterwards,
  "arrête" stops the scroll instead of closing the session, and the ambiguous
  verbs "monte"/"descends" still reach volume and brightness
  (`test_interaction.py`);
- **the session**: it lasts through several exchanges, the countdown restarts
  when you speak, "stop" closes it at once, and nothing runs afterwards without
  the wake word (`test_wake.py`);
- **conversation follow-up**: "va sur YouTube" then "recherche Damso" searches
  YouTube; the context moves with the last site named and expires with the
  session (`test_site_search.py`);
- **tab reuse**: a background tab is activated rather than duplicated, showing
  a site never reloads it, and searching does navigate (`test_site_search.py`);
- **site search**: query not truncated at the first "sur", and
  Wikipedia still handled by its dedicated summary-reading command
  (`test_site_search.py`);
- **loose phrasings**: "je voudrais que tu montes le son" must work, while
  "il fait beau aujourd'hui" must still trigger nothing (`test_router.py`);
- **the Claude Code provider**: exact call arguments, mandatory `working_dir`,
  absence of permission flags, `ANTHROPIC_API_KEY` detection, timeout and error
  handling (`test_claude_code_provider.py`).

One test also runs **every example shown in the help** to check that it actually
works: the documentation cannot drift from the code.

---

## Why no AI, and how to add one later

Routing is done by local rules: **free, instant, offline and predictable**. No
network call is made to understand a request.

When no rule matches, the router calls
`core/ai_fallback.handle_with_ai(query)`. By default
(`ai_fallback.enabled: false`) that function simply replies politely and
suggests `aide` — no network, no subprocess, no cost.

### The Claude Code fallback (implemented, disabled by default)

The only real provider is `ClaudeCodeProvider`
([core/providers/claude_code_provider.py](core/providers/claude_code_provider.py)).
Once enabled, it **delegates the request to the Claude Code CLI already
installed on your machine**:

```
claude -p "your request" --output-format text
```

In other words, ALMA becomes a voice remote control for Claude Code.

| Aspect | Behaviour |
|---|---|
| **Capabilities** | exactly those of Claude Code — no more, no less. Whatever you could do by typing the command yourself. |
| **Permissions** | those configured for Claude Code on the machine. ALMA **adds no flags** (`--allowedTools`, `--dangerously-skip-permissions`…) and does not invent its own list. A test verifies this. |
| **Billing** | your Claude subscription quota, as long as no `ANTHROPIC_API_KEY` is set. |
| **`ANTHROPIC_API_KEY`** | ALMA **never** sets or modifies it. If it detects one, it warns you (log plus a header on the reply) so you are not billed for API usage by surprise. |
| **Scope** | bounded by `working_dir`, which is **mandatory**: while it is empty the provider refuses to run and tells you why. |
| **Safety** | the request is passed as an argument, never through a shell: nothing you dictate can be interpreted as a command. |

To enable it, in `config.yaml`:

```yaml
ai_fallback:
  enabled: true              # ← your decision
  provider: claude_code
  claude_code:
    command: claude
    working_dir: C:/Users/me/projects/sandbox   # mandatory
    timeout_seconds: 120     # the call is blocking
```

> **This is the only AI entry point in the project.** There is no second channel
> to any API: `PROVIDERS` contains only `none` and `claude_code`, and a test
> scans the source to forbid any hardcoded AI API URL.

### Adding another provider

Create a module in `core/providers/` exposing `generate(query) -> str`, then add
an entry to `PROVIDERS` in `core/ai_fallback.py`. Nothing else in the code
changes.

> The only network calls made by default are: Open-Meteo (weather, free, no
> key), the Wikipedia REST API (free), the edge-tts voice service (free, no
> key), and Google speech recognition **only if** you use voice mode without
> Vosk.

---

## Planned extensions

### Camera and gestures (not implemented)

The architecture is ready: `Utterance` carries a `source` field and
`SOURCE_GESTURE` is reserved. A future `core/gesture.py` (OpenCV plus MediaPipe
Hands, both local and free) will run in its own thread and send text commands to
the **same router** — closed fist to pause, thumbs up for volume, a "V" sign for
a screenshot. An air-drawing mode will track the index fingertip (landmark 8) on
an overlay canvas.

No existing command will need rewriting: they already accept `source="gesture"`,
and a test verifies it.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Impossible d'ouvrir X" | Wrong path. Set the full path in `config.yaml` under `applications.X.paths`. |
| Volume does not change | `pip install pycaw comtypes`. Without pycaw, ALMA falls back to media keys. |
| Brightness does not change | Common on **external monitors**, which do not expose DDC/CI control. |
| `pip install PyAudio` fails | You are probably in WSL. Install from Windows, where a prebuilt wheel is used. |
| ALMA does not speak | `pip install -r requirements-voice.txt`, then check `voice.speak_responses` in `config.yaml`. |
| The voice sounds robotic | The neural voice needs internet; ALMA fell back to SAPI5. Check your connection. |
| The microphone hears nothing | Run `python diagnostic_micro.py` — it measures your actual level and tells you what to set. |
| ALMA ignores you | Check the text shown under the orb. If your sentence appears but nothing happens, the wake word was not recognised: add the spelling you see to `general.wake_variants`. |
| Accents display wrongly | Use Windows Terminal rather than the legacy `cmd.exe` console. |
| A command is not recognised | Type `aide` for the exact phrasing, or add a `pattern` to the command. |

---

## Licence

MIT — see [LICENSE](LICENSE). Free to use, modify and redistribute.
