---
name: sonder-alma
description: Essayer des phrases sur ALMA pour de vrai, sans rien laisser sur la machine. À utiliser avant toute exécution de assistant.handle(), et pour lancer l'application ou nettoyer ce qu'une sonde a ouvert.
---

# Sonder ALMA sans rien laisser derrière

`assistant.handle("...")` **exécute vraiment** la commande, sur la machine de
quelqu'un qui est en train de travailler dessus. Une sonde de vingt phrases a
déjà ouvert douze onglets Chrome sur son écran de travail, écrasé son
presse-papiers, rempli `screenshots/` et vidé `data/souvenirs.json`.

Neutraliser vaut toujours mieux que nettoyer.

## Le squelette d'une sonde

À écrire dans le dossier scratchpad, jamais dans le dépôt.

```python
import pathlib, sys, tempfile
RACINE = r"C:\Users\rehma\projets\Jarvis"
sys.path.insert(0, RACINE); sys.path.insert(0, RACINE + r"\tests")
TMP = pathlib.Path(tempfile.mkdtemp())

from conftest import FakeIO, config_de_test          # configuration D'ORIGINE
from core.assistant import Assistant
from commands import websites
from core import win_utils

# Les sorties, coupees a la racine.
websites.open_url = lambda *a, **k: True
win_utils.set_clipboard = lambda *a, **k: True
win_utils.launch = lambda *a, **k: (False, "sonde")
win_utils.take_screenshot = lambda *a, **k: (True, "sonde.png")

class SilentTTS:
    available = False; voices = []; error = ""; moteur_actif = "aucun"
    def say(self, t, blocking=False, cacher=False): pass
    def wait(self, timeout=None): pass
    def list_voices(self): return []
    def reconfigurer(self): return False
    def shutdown(self): pass

c = config_de_test()
for cle in ("notes", "reminders", "history", "memory", "preferences"):
    c.set("paths." + cle, str(TMP / (cle + ".json")))
a = Assistant(config=c, io=FakeIO(), tts=SilentTTS())

for phrase in [...]:
    print("%-40r -> %s" % (phrase, a.handle(phrase).text))
```

Lancer avec `PYTHONIOENCODING=utf-8` : sans cela la console Windows casse sur les
accents et la sonde s'arrête au milieu.

**Ne jamais essayer** sur la vraie configuration : « oublie tout », « efface mes
notes », « vide la corbeille », « supprime ... ». Ces phrases détruisent des
données que git ne suit pas — `data/*.json` est ignoré.

## Vérifier seulement le routage

Quand la question est « quelle commande est atteinte », ne pas exécuter du tout :

```python
from core.context import Utterance
u = Utterance.parse(phrase, wake_words=["alma"])
resolution = a.router.resolve(u, assistant=a)
print(resolution.command.name if resolution else "AUCUNE")
```

C'est plus rapide, et rigoureusement sans effet.

## Lancer l'application

```bash
.venv\Scripts\python.exe gui.py --sans-micro   # silencieux, n'ecoute pas
.venv\Scripts\python.exe gui.py                # vrai lancement
```

Elle s'ouvre **en plein écran** sur un des écrans : le dire avant de la lancer.
`--sans-micro` évite de couper ce que l'utilisateur écoute.

Pour rejouer le premier lancement : supprimer `data/preferences.json`, où vit le
drapeau `general.setup_done`.

## Si une sonde a quand même ouvert des onglets

Les fermer dans la même session, par le bouton de fermeture propre à chaque
onglet — cela marche sans passer la fenêtre au premier plan, donc sans déranger.

```python
from commands.fenetres import _fermer_onglet
from core import browser_tabs, desktop

MIENS = ("gift ideas - Recherche Google", "...")   # les titres exacts, rien d'autre

for _ in range(40):                                # borne dure
    cible = None
    for f in desktop.fenetres():
        if f.processus.lower() != "chrome.exe":
            continue
        for o in browser_tabs.onglets(f):
            if any(o.nom.replace("\u00a0", " ").startswith(t) for t in MIENS):
                cible = o
                break
        if cible:
            break
    if cible is None or not _fermer_onglet(cible):
        break
```

Chrome écrit « Google Maps » avec une **espace insécable** : sans le
`replace("\u00a0", " ")`, aucun titre ne correspond.

Ré-énumérer après chaque fermeture (l'arbre UI Automation change), et relancer la
boucle jusqu'à zéro — un passage n'en ferme jamais la totalité.

## Ce qui peut être récupéré

`data/history.json` garde chaque commande avec son texte et son horodatage. Des
notes ou des souvenirs effacés par accident s'y reconstruisent souvent.
