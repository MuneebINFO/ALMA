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

## Running the tests

```bash
.venv\Scripts\python.exe -m pytest -q
```

No test should depend on the real desktop's state (open windows, monitor
layout, installed apps) unless it explicitly mocks that state — see any
`monkeypatch.setattr(desktop, "fenetres", ...)` in the existing tests for
the pattern.
