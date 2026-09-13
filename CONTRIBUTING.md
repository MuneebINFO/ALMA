# Contributing to ALMA

## Every command must work in French AND English

ALMA is bilingual by design — the README says so, and users expect it. When
you add a new `@command`, its `patterns` must include a natural English
phrasing alongside the French one, not just the French. This applies to
**every** new command, no exceptions — add it at the same time you add the
command, not as a follow-up.

Practical notes, learned while retrofitting the existing commands:

- **Word order often flips.** French puts the qualifier after the noun
  ("onglet suivant"), English puts it before ("next tab"). You usually need
  a genuinely separate pattern string for the English phrasing, not just
  extra words spliced into the French verb group.
- **Shared verb groups still work when the words really are shared.**
  `commands/apps.py`'s `OPEN_VERBS`/`CLOSE_VERBS` mix French and English
  verbs in one alternation (`ouvre|...|open|launch|start`) because the
  sentence structure around them is identical in both languages. Use this
  where it fits; don't force it where word order differs.
- **Numbers and ordinals go through `core/deduction.py`.** `nombre_entendu`
  and `commands/media.py`'s `ORDINAUX` already understand English number
  words and ordinals ("first", "3rd", "third"...) — reuse them instead of
  writing a parallel English number table in your command file.
- **Apostrophes don't survive normalization.** `text_utils.normalize` turns
  `"what's"` into `"what s"` (two tokens) before any pattern sees it. Never
  write a literal `'s` in a pattern — match `s\s+` (or make it optional
  alongside `is\s+`) instead, e.g. `r"what\s+(?:is\s+|s\s+)?playing"`.
- **Add an English example** to the command's `examples=[...]`, and an
  English row to `commandes.json` if the command has one there.
- **Test it.** Add the phrase to `tests/test_anglais.py`, parametrized
  alongside the others, asserting it routes to the same command name as its
  French equivalent.

## And it must ANSWER in the language it was asked in

Routing is only half of it. A command that understands "note that ..." and
replies "C'est noté" is still wrong. Build every reply through the context,
never with a bare `Response`:

```python
return ctx.reponse("C'est noté : " + contenu, "Noted: " + contenu)
return ctx.erreur("Je ne connais pas ce site.", "I don't know that site.")
if not ctx.confirm("Vider la corbeille ?", "Empty the recycle bin?"):
    ...
```

`ctx.lang` holds `"fr"` or `"en"`, decided by `text_utils.detect_language`
from marker words in the sentence. Read it directly when a reply is built
in pieces (a list, a sentence assembled in a loop) rather than in one call.

- **Write the English side, don't translate it.** A joke, a greeting, a
  unit: say what that language actually says. English reads the clock on
  12 hours with am/pm, French on 24. "1920 by 1080", not "1920 sur 1080".
- **Only three exceptions may stay in one language**, and each is content
  rather than a reply: what Claude or an AI provider answered, what the
  clipboard contains, and names that come from `config.yaml` (application
  and site names are the user's own words).
- **A new marker word costs nothing but must be exclusive.** Add it to
  `_MARQUEURS_ANGLAIS` only if it cannot be a French word after
  normalization — "second", "note", "volume", "timer", "video", "series"
  are shared and are deliberately absent. A sentence with no marker at all
  falls back to French.
- **Test it** in `tests/test_reponses_anglaises.py`: an exact text if the
  machine doesn't change it, otherwise add the phrase to the net that
  refuses any French-only word in a reply to an English sentence.

## Adding a personalization

A setting the user can change by voice needs four things, and skipping any one
of them leaves a half-working feature:

1. **An entry in `core/preferences.py`'s `CATALOGUE`.** It is a whitelist: a
   path that is not listed cannot be written, on purpose — a command must
   never be able to reach an arbitrary config key. Set `visible=False` for a
   setting that merely follows another (the wake word follows the name, the
   listening language follows the chosen language); it is still remembered,
   just not listed twice.
2. **A command that calls `ctx.assistant.personnaliser({...})`**, never
   `config.set` alone. `personnaliser` does both halves — apply now, remember
   for later — and one without the other is useless: applied but forgotten
   dies at midnight, remembered but not applied looks broken.
3. **A live effect, if something already built holds a copy of the value.**
   Objects read the config once at construction: `MoteurEcoute` keeps its wake
   word, `TextToSpeech` its voice. `Assistant._appliquer` is where you tell
   them; add your path to the right group there, and reconfigure **in place**
   (`moteur.reconfigurer`) rather than rebuilding — the GUI holds a reference
   to the same object and would never see a replacement.
4. **Two tests** in `tests/test_reponses_anglaises.py`'s sibling
   `tests/test_personnalisation.py`: that the phrase routes (both languages),
   and that the value survives `load_config(preferences_file=...)`.

And the standing rules still apply: English patterns from the start, replies
through `ctx.reponse(fr, en)`.

## Running the tests

```bash
.venv\Scripts\python.exe -m pytest -q
```

No test should depend on the real desktop's state (open windows, monitor
layout, installed apps) unless it explicitly mocks that state — see any
`monkeypatch.setattr(desktop, "fenetres", ...)` in the existing tests for
the pattern.
