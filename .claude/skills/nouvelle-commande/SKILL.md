---
name: nouvelle-commande
description: Ajouter une commande à ALMA, ou en corriger une qui ne se déclenche pas. À utiliser dès qu'il s'agit d'un @command dans commands/*.py — nouvelle capacité, formulation à faire reconnaître, conflit de routage entre deux commandes.
---

# Ajouter une commande à ALMA

C'est la tâche la plus fréquente du projet, et celle où les mêmes erreurs
reviennent. Suivre l'ordre ci-dessous : chaque étape a déjà été oubliée au moins
une fois, et le bug qui suit est toujours silencieux.

## 1. Regarder d'abord si la place est prise

```bash
.venv\Scripts\python.exe -c "from core.registry import load_commands, all_commands; load_commands(); [print('%3d %-28s %s' % (c.priority, c.name, c.description)) for c in sorted(all_commands(), key=lambda c: -c.priority)]"
```

Une commande nouvelle entre presque toujours en concurrence avec une existante.
Repérer celles dont les motifs partagent un verbe (`ouvre`, `arrête`, `mets`) et
décider **laquelle est la plus spécifique** : c'est elle qui prend la priorité la
plus haute.

## 2. Écrire les motifs, dans les deux langues

Les deux formulations dès la création, jamais après coup. Le plus souvent deux
chaînes séparées : l'ordre des mots change (« onglet suivant » / « next tab »).

Les motifs s'appliquent à la phrase **normalisée** — minuscules, sans accents,
apostrophes et ponctuation devenues des espaces.

```python
@command(
    name="ma_commande",
    patterns=[
        r"^(?:ouvre|ouvrir)\s+(?:le\s+)?machin\s+(.+)$",
        r"^open\s+(?:the\s+)?thing\s+(.+)$",
    ],
    keywords=[["ouvre", "machin"], ["open", "thing"]],   # repli, facultatif
    category="...",
    description="Ce que ça fait, en une ligne",
    examples=["ouvre le machin truc", "open the thing truc"],
    priority=90,
)
def ma_commande(ctx: CommandContext) -> Response:
    ...
```

Les pièges, tous déjà payés :

- **Jamais de `'s` littéral** : `"what's"` est normalisé en `"what s"`. Écrire
  `(?:is\s+|s\s+)?`.
- **`ctx.arg` vaut `group(1)`** : tout groupe capturant ajouté ailleurs décale
  l'argument en silence. Utiliser `(?:...)`.
- **Un groupe nommé lu par le handler doit exister dans TOUS les motifs**, sinon
  un motif sur deux lève à l'exécution.
- **Le décorateur va sur le handler**, pas sur l'utilitaire juste au-dessus.
- **`guard`** permet au routeur de continuer à chercher quand il renvoie False.
- Les accents ne servent à rien dans un motif : écrire `arrete`, pas `arrête`.

## 3. Écrire les réponses dans les deux langues

```python
return ctx.reponse("C'est fait.", "Done.")
return ctx.erreur("Je ne trouve pas « " + nom + " ».", 'I can\'t find "' + nom + '".')
if not ctx.confirm("Vraiment ?", "Really?"):
    ...
```

Jamais un `Response(text=...)` nu. Écrire l'anglais, ne pas le traduire : heure sur
douze heures avec am/pm, « 1920 by 1080 », des blagues qui sont d'autres blagues.

`speak=False` pour une action réussie dont le résultat se voit à l'écran ;
`informatif=True` sur la commande quand elle répond quelque chose (heure, météo).

## 4. Si la commande change un réglage

Passer par `ctx.assistant.personnaliser({chemin: valeur})`, et inscrire le chemin
dans `CATALOGUE` (`core/preferences.py`). Voir la règle 3 de `CLAUDE.md`.

## 5. Vérifier le routage AVANT d'écrire les tests

```bash
.venv\Scripts\python.exe -c "
from core.context import CommandContext, Utterance
from core.registry import load_commands
from core.router import Router
from config import load_config
load_commands(); r = Router(); c = load_config()
for p in ['ouvre le machin truc', 'open the thing truc']:
    u = Utterance.parse(p, wake_words=c.get('general.wake_words'))
    res = r.resolve(u, None)
    if res is None:
        print('%-34r -> AUCUNE' % p); continue
    ctx = CommandContext(u, None, match=res.match, command=res.command)
    print('%-34r -> %-24s ctx.arg=%r' % (p, res.command.name, ctx.arg))
"
```

Passer par un `CommandContext` et non par `match.group(1)` : le motif s'applique
à la chaîne normalisée et rendrait `'youtube'`, là où `ctx.arg` — ce que le
handler reçoit réellement — rend `'YouTube'`, casse et accents intacts.

Vérifier aussi qu'une phrase **voisine** ne tombe pas dans la nouvelle commande.
C'est le risque symétrique, et il ne se voit qu'en le cherchant.

## 6. Les tests

- `tests/test_anglais.py` : la phrase anglaise route vers la même commande que la
  française.
- `tests/test_reponses_anglaises.py` : la réponse anglaise ne contient aucun mot
  exclusivement français.
- Le fichier de la famille concernée : le comportement réel, et **les phrases
  voisines qui ne doivent PAS y aboutir**.

Ne rien mettre dans un test qui dépende des écrans branchés ou de ce qui joue :
`monkeypatch.setattr(desktop, "fenetres", ...)`.

## 7. Inscrire l'action dans `commandes.json`

C'est la spécification parlée du projet, et un test exige que chaque phrase qui
y figure atteigne la commande annoncée par sa `description`.

## 8. La suite complète

```bash
.venv\Scripts\python.exe -m pytest -q
```

Elle doit passer **entièrement**. Si un échec semble venir de la machine, c'est
presque toujours que le test la touche ou la suppose : le corriger, ne pas
l'excuser.
