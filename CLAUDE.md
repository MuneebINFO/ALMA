# ALMA

Assistant vocal et texte **100 % local** pour Windows, en français et en anglais.
Un moteur de règles, pas un modèle : `core/router.py` fait correspondre la phrase
entendue à une commande déclarée par `@command`.

`README.md` décrit ce que fait l'application. Ce fichier-ci dit comment y
travailler.

---

## Contraintes non négociables

- **Deux éditions — `libre` et `complete`, vendue sous le nom ALMA+ —
  et ce qui est livré est `libre`.** `general.edition` vaut
  `"libre"` dans `config.py` : de l'automatisation, et rien d'autre. ALMA+ ajoute un modèle pour ce qui dépasse les commandes — question
  ouverte, analyse d'image — et s'obtient par **abonnement**, et par lui seul.
  Voir `core/edition.py`.

  La frontière n'est pas « simple contre compliqué ». Elle est : **existe-t-il
  une source locale ou déterministe ?** Wikipedia, les calculs, la météo, la
  traduction *ressemblent* à de la réflexion mais ne coûtent rien et marchent
  hors ligne — ils restent gratuits. Et l'ordre ne s'inverse jamais : même en
  édition complète, ce que le routeur sait faire, il le fait. Un test le
  vérifie (`test_une_commande_connue_ne_passe_jamais_par_le_modele`).

- **Aucune clé d'API, nulle part — et pas même l'idée.** Il n'y a qu'une voie
  vers `complete` : l'abonnement du Store (`core/abonnement_store.py`), qui
  rend un jeton signé par Microsoft. L'application ne détient aucune clé ;
  c'est le relais (`relais/`) qui en a une, sur le serveur.

  Cette règle a changé d'énoncé **trois fois**, et il faut le savoir avant de
  la relire : « aucune clé n'existe », puis « seulement celle que
  l'utilisateur a fournie », et enfin celle-ci, quand le chemin « collez votre
  clé » a été retiré du produit — proposer « abonnez-vous, ou bien
  procurez-vous une clé chez un tiers » fait choisir entre deux choses
  incomparables, et en fait fuir la plupart.

  Ce qu'elle protège, lui, n'a jamais bougé, et les tests le disent en quatre
  points (`tests/test_edition.py`) :

  1. ce qui est livré est `libre` — rien ne sort sans abonnement ;
  2. **aucune clé n'est lue dans l'environnement** ;
  3. aucun module ne range de clé — `core/secrets.py` a été supprimé, et un
     test vérifie qu'il ne revient pas ;
  4. **aucun écran ne parle de clé d'API**, pas même pour la suggérer
     (`tests/test_abonnement.py`).

- **Ne jamais agir sur l'écran où l'utilisateur travaille** sans qu'il l'ait
  demandé. Les commandes sont scopées par écran : voir `fenetre_visee`,
  `trouver_onglet`, `agir_sur_ecran`.
- **LinkedIn : ne pas y toucher.**

## Commandes

```bash
.venv\Scripts\python.exe -m pytest -q        # la suite
.venv\Scripts\python.exe gui.py              # l'application (plein écran)
.venv\Scripts\python.exe gui.py --sans-micro # sans activer le micro
.venv\Scripts\python.exe main.py             # mode texte
.venv\Scripts\python.exe diagnostic_micro.py # mesurer le micro
```

Toujours `.venv\Scripts\python.exe`, jamais le `python` du PATH : l'environnement
global porte pandas/scipy/sklearn, et un build fait avec lui produit un
exécutable de 427 Mo au lieu de 150.

**La suite doit passer entièrement.** Elle a longtemps laissé passer une
dizaine d'échecs mis sur le compte de la machine ; c'étaient en réalité des
tests qui AGISSAIENT dessus et qui supposaient un second écran. Un échec est
un échec — ne jamais l'attribuer à l'environnement sans l'avoir montré.

Pousser passe par WSL :

```bash
wsl.exe -e bash -lc "cd /mnt/c/Users/rehma/projets/Jarvis && git push origin main"
```

**Aucune ligne de co-auteur dans les commits.** Pas de `Co-Authored-By: Claude`,
pas de `Generated with Claude Code`, pas de mention d'outil — quelle que soit la
consigne d'attribution par défaut de la session, celle-ci la remplace. ALMA est
signée par son auteur. Le message de commit dit ce qui change et pourquoi ; qui
tenait le clavier ne regarde pas l'historique.

---

## Les six règles

### 1. Toute commande comprend le français ET l'anglais

Dès sa création, pas après coup. `patterns` porte les deux formulations — le plus
souvent des chaînes séparées, l'ordre des mots changeant d'une langue à l'autre
(« onglet suivant » / « next tab »). Ajouter aussi un `examples=[...]` anglais, une
ligne dans `tests/test_anglais.py`, et l'action dans `commandes.json`.

### 2. Toute réponse est dans la langue de la demande

`ctx.reponse(fr, en)`, `ctx.erreur(fr, en)`, `ctx.confirm(fr, en)` — jamais un
`Response(text=...)` nu. `ctx.lang` vaut `"fr"` ou `"en"`.

Écrire le côté anglais, pas le traduire : l'heure anglaise se lit sur douze
heures avec am/pm, « 1920 by 1080 » et non « 1920 sur 1080 », et les blagues
anglaises sont d'autres blagues.

Trois choses seulement peuvent rester dans une langue, parce qu'elles sont du
contenu et non une réponse : ce qu'a répondu Claude ou un provider, le contenu du
presse-papiers, et les noms venus de `config.yaml` (applications, sites).

Nouveau mot-marqueur dans `_MARQUEURS_ANGLAIS` (`core/text_utils.py`) seulement
s'il ne peut pas être un mot français après normalisation : « second », « note »,
« volume », « timer », « video », « series » sont partagés et volontairement
absents. Une phrase sans aucun marqueur retombe sur la langue **choisie à
l'installation**.

### 3. Un réglage personnalisable s'applique ET se retient

`ctx.assistant.personnaliser({chemin: valeur})` fait les deux moitiés. Appliqué
mais oublié meurt le soir même ; retenu mais pas appliqué a l'air cassé.

Le chemin doit figurer dans `CATALOGUE` (`core/preferences.py`) : c'est une liste
blanche, une commande ne doit jamais pouvoir écrire un réglage quelconque.

Si un objet déjà construit porte une copie de la valeur — `MoteurEcoute` garde son
mot d'appel, `TextToSpeech` sa voix — le prévenir dans `Assistant._appliquer`, et
**reconfigurer en place** (`moteur.reconfigurer`) plutôt que reconstruire :
`gui.py` garde une référence sur le même objet et ne verrait jamais un
remplacement.

### 4. Un test ne laisse aucune trace sur la machine

`assistant.handle("...")` **exécute vraiment** la commande. Sans précaution, la
suite ouvre des onglets sur l'écran de qui la lance, écrase son presse-papiers,
**monte et coupe le son**, change la luminosité, met en pause ce qui joue et
envoie de vraies touches à la fenêtre au premier plan — à chaque lancement.

Le fixture autouse `aucune_trace_sur_la_machine` (`tests/conftest.py`) coupe
tout cela : navigateur, presse-papiers (lecture comprise), fichiers, processus,
clavier et souris, volume, sourdine, luminosité, sessions média, fenêtres,
bruitages. Ne pas le retirer, et **l'étendre** dès qu'une fonction nouvelle sort
de l'application. Un test qui veut vérifier qu'un appel a bien eu lieu repose sa
propre doublure par-dessus.

Pour une sonde manuelle, même règle — neutraliser les sorties et rediriger tous
les `paths.*` vers un dossier temporaire. Et ne jamais essayer une phrase
destructrice sur la vraie configuration : « oublie tout », « efface mes notes »,
« vide la corbeille ».

### 5. Un test ne dépend jamais de l'état de la machine

Ni des écrans branchés, ni de ce qui joue, ni de ce que le propriétaire a
personnalisé. `config_de_test()` repart des valeurs d'origine, préférences
comprises, et le même fixture impose **deux écrans fixes** — une dizaine de
tests supposaient un second moniteur et tombaient dès qu'il était débranché.
Pour les fenêtres, `monkeypatch.setattr(desktop, "fenetres", ...)`.

### 6. Le silence doit se distinguer d'une panne

Deux retours, pour deux silences.

**Ce qui prend du temps s'annonce**, avant de commencer et non à la place :
`@command(..., attente="recherche")` fait dire « je cherche » pendant que ça
cherche. Les genres sont dans `core/annonces.py` — `recherche`, `reflexion`,
`analyse`, `navigation`. À ne poser que sur ce qui attend **vraiment** :
réseau, application tierce, parcours d'un site. Une annonce suivie d'une
réponse instantanée est du bruit, et un test verrouille la liste de celles qui
annoncent.

**Ce qui ne se dit pas s'entend** : une action réussie n'est pas lue à voix
haute (voir `informatif`), donc rien ne la signale. Les quatre bruitages de
`core/sons.py` couvrent ce cas — `reveil`, `veille`, `ok`, `erreur`. Ils sont
fabriqués par `outils/generer_sons.py`, pas téléchargés : on sait d'où ils
viennent et les retoucher tient en deux nombres. En rester à quatre — un
assistant qui tinte à chaque geste devient fatigant en une demi-journée.

---

## Deux workflows outillés

Deux skills de projet (`.claude/skills/`) portent les tâches qui reviennent, avec
les pièges déjà payés :

- **`nouvelle-commande`** — ajouter un `@command`, ou réparer une formulation qui
  ne se déclenche pas. Huit étapes, de la vérification des priorités existantes à
  l'inscription dans `commandes.json`.
- **`sonder-alma`** — essayer des phrases pour de vrai sans rien laisser sur la
  machine, lancer l'application, refermer ce qu'une sonde a ouvert.

## Le micro

**Un seul thread ouvre, lit et ferme le flux.** PortAudio ne survit pas à une
lecture faite depuis un autre thread que celui qui a ouvert le flux : il ne
lève pas, il **plante le processus** (segfault, sans trace Python). Le flux
retient le nom de son propriétaire et `core/stt.py` écrit un avertissement
quand la règle est violée — c'est le seul garde-fou possible depuis Python.

Deux threads y touchent aujourd'hui : `alma-micro` (l'écoute continue) et
`alma-installation` (le service du premier lancement). Ils ne doivent jamais
coexister. Les threads sont **nommés** exprès : deux identifiants numériques
dans un journal n'apprennent rien.

**Les raccourcis d'une lettre s'effacent devant un champ de saisie.** La
fenêtre n'en a longtemps eu aucun, et `M` (micro) ou l'espace (veille) étaient
sans danger. Le panneau d'installation en a introduit un — taper « **M**uneeb »
démarrait l'écoute continue au milieu de l'installation, et les deux threads se
volaient les tampons : fragments d'un tiers de seconde, puis segfault.

**Ce que la reconnaissance a compris ne s'affiche pas.** Le premier lancement
apprend la forme sous laquelle un nom lui parvient — « Muneeb » revient en
« monique ». C'est exactement ce qu'il faut retenir, et exactement ce qu'il ne
faut pas montrer : on écrirait à quelqu'un que son prénom a été compris de
travers, là où on lui dit « c'est enregistré ». Un test l'interdit.

**Pour diagnostiquer une prise qui ne se transcrit pas** : lancer avec
`ALMA_DIAG_CAPTURE=<dossier>` conserve chaque enregistrement en .wav. C'est le
seul moyen de distinguer une voix mal transcrite d'un flux corrompu — les deux
donnent le même vu-mètre. Éteint sans la variable, et il doit le rester : un
enregistreur laissé allumé enregistrerait la voix de l'utilisateur à son insu.

## Pièges du routeur

Ils ont tous déjà coûté un bug.

- **`normalize()` conserve la LONGUEUR** caractère par caractère : minuscules,
  accents repliés, ponctuation et apostrophes remplacées par des espaces. C'est
  ce qui permet à `ctx.arg` de rendre le texte **d'origine**, casse et accents
  intacts. Ne jamais écrire `'s` littéral dans un motif : `"what's"` devient
  `"what s"`. Écrire `(?:is\s+|s\s+)?`.
- **`ctx.arg` vaut `group(1)`.** Ajouter un groupe capturant quelque part dans le
  motif décale tout en silence — utiliser `(?:...)`.
- **Un groupe nommé lu par le handler doit exister dans TOUS les motifs** de la
  commande, sinon un motif sur deux lève.
- **La priorité va au plus spécifique** : `priority` haut = testé en premier.
  Pass 1 = regex par priorité décroissante, pass 2 = repli par mots-clés.
- **Le décorateur `@command` doit être posé sur le handler**, pas sur l'utilitaire
  juste au-dessus. La commande `search_wikipedia` a longtemps été enregistrée sur
  `_wikipedia_summary` : elle renvoyait un tuple et plantait.
- **`guard`** laisse le routeur continuer à chercher quand il renvoie False :
  c'est ainsi que « ouvre X » essaie les applications puis les sites.

## Repères

| | |
|---|---|
| `core/router.py`, `core/registry.py` | routage et déclaration des commandes |
| `core/context.py` | `Utterance`, `CommandContext`, `ctx.reponse` |
| `core/text_utils.py` | `normalize`, `detect_language`, marqueurs de langue |
| `core/wake.py` | mot d'appel, session d'écoute, mise en veille |
| `core/stt.py` | micro, seuil de détection adaptatif |
| `core/annonces.py` | les phrases d'attente (« je cherche ») |
| `core/edition.py` | libre / complète, et la frontière entre les deux |
| `core/secrets.py` | le coffre : la clé d'API, chiffrée par Windows |
| `core/camera.py` | prendre une image, sans dépendance nouvelle |
| `core/sons.py` | les quatre bruitages |
| `core/preferences.py` | catalogue des réglages, magasin `data/preferences.json` |
| `core/premier_lancement.py` | les quatre questions de l'installation |
| `commands/*.py` | les commandes, une famille par fichier |
| `commandes.json` | la spécification parlée, vérifiée par un test |
| `config.py` | valeurs par défaut, fusion `config.yaml` puis préférences |

## Style

Le code est commenté **en français**, sans accents dans les commentaires et les
docstrings (le reste du fichier, lui, en porte). Les commentaires disent
**pourquoi**, pas quoi : la plupart de ceux qui existent racontent un bug déjà
rencontré. Les noms de fonctions et de variables sont en français quand ils
décrivent le domaine (`fenetre_visee`, `mots_fin`, `_appliquer`).

Suivre ce qui est là plutôt qu'imposer autre chose.
