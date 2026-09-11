# Publier ALMA sur le Microsoft Store (version gratuite)

Ce dossier empaquette `Alma.exe` en `.msix`, au format "Desktop Bridge" : une
application Win32 normale (pas une UWP en bac à sable), ce qui lui laisse ses
droits habituels — exactement ce dont elle a besoin pour piloter d'autres
fenêtres — sans passer par la capacité restreinte `inputInjectionBrokered`
(réservée à des cas bien plus étroits : authentification bancaire, accès
d'entreprise). Voir le commentaire en tête de
[`Package.appxmanifest.template`](Package.appxmanifest.template).

**Le but pour l'instant : la version gratuite, sans abonnement.** Rien
ci-dessous ne touche à la facturation.

## Étapes manuelles (vous seul pouvez les faire)

Rien de tout ça ne peut être automatisé — ce sont votre compte et votre
identité, pas un fichier du dépôt.

1. **Compte Partner Center** : [partner.microsoft.com/dashboard/registration](https://partner.microsoft.com/dashboard/registration).
   Frais d'inscription unique (~19 $ compte individuel / ~99 $ société — les
   montants exacts changent, vérifiez sur la page).
2. **Réserver le nom de l'appli** : *Apps and games → New product → MSIX or
   PWA app*. Réservez "ALMA" (ou un nom disponible proche).
3. **Récupérer votre identité** : une fois le nom réservé, *Product
   management → App identity* affiche deux valeurs à copier :
   - **Package/Identity/Name** → `package_name`
   - **Package/Identity/Publisher** → `publisher` (commence par `CN=`)
4. **Copier `identity.example.json` en `identity.local.json`** (à côté, dans
   ce dossier) et y coller ces deux valeurs, plus votre nom d'éditeur. Ce
   fichier n'est **jamais** versionné (voir `.gitignore`) — c'est votre
   identité personnelle.
5. **Installer le Windows SDK**, pour `makeappx.exe` et `signtool.exe` :
   ```
   winget install Microsoft.WindowsSDK
   ```
   (ou via l'installateur Visual Studio, composant "Windows 10/11 SDK".)

## Construire le paquet

Depuis une invite PowerShell, à la racine du dépôt :

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File packaging\msix\build_msix.ps1
```

Ça enchaîne : `build_exe.py` (compile `Alma.exe`), génère les images du
Store à partir du même dessin que l'icône (`make_store_assets.py`), remplit
le manifeste avec votre identité (`render_manifest.py`), et empaquette le
tout avec `makeappx.exe`. Résultat : `packaging/msix/Alma.msix`.

`build_msix.ps1` construit toujours avec `.venv\Scripts\python.exe`, jamais
le `python` du PATH : sur une machine dont le Python global a d'autres
paquets installés pour autre chose, PyInstaller les embarquerait tous dans
`Alma.exe` sans raison — c'est exactement ce qui s'est passé la première
fois (427 Mo au lieu de quelques dizaines, à cause de pandas/scipy/Jupyter
installés globalement, sans rapport avec ALMA).

### Tester l'installation avant de soumettre

```powershell
powershell -ExecutionPolicy Bypass -File packaging\msix\build_msix.ps1 -Sideload
```

Ajoute un certificat de test **local** (jamais utilisé pour le Store — le
Store re-signe le paquet lui-même à la certification) et installe le
paquet sur cette machine, pour vérifier qu'ALMA se lance vraiment depuis le
`.msix` avant de le soumettre.

## Avant de soumettre : la checklist

- [ ] **Politique de confidentialité, publiée quelque part de stable et
      public.** Le contenu est déjà rédigé : [`PRIVACY.md`](../../PRIVACY.md)
      à la racine du dépôt. Deux options :
      - si le dépôt GitHub est public, son lien brut suffit
        (`https://raw.githubusercontent.com/.../PRIVACY.md` ou, mieux, une
        page GitHub Pages) ;
      - sinon, publiez-le comme page web (une page GitHub Pages reste
        l'option la plus durable et la plus conventionnelle pour une fiche
        Store).
- [ ] **Justification de `runFullTrust`** : Partner Center demande une
      explication courte à la soumission. Quelque chose comme : *"ALMA est
      un assistant de bureau qui pilote d'autres applications sur demande de
      l'utilisateur (ouvrir un site, fermer une fenêtre, cliquer un bouton) ;
      cela nécessite les API Win32 standard d'automatisation d'interface,
      identiques à celles utilisées par les lecteurs d'écran."*
- [ ] **Description de la fiche Store honnête sur ce qu'ALMA fait** :
      mentionnez explicitement le contrôle du clavier/souris et la lecture
      de l'écran — mieux vaut que la revue le sache d'emblée que le
      découvre en testant.
- [ ] **Captures d'écran** de l'appli réellement lancée (Partner Center en
      exige au moins une, en 1366×768 minimum).
- [ ] **Évaluation d'âge** : questionnaire IARC dans Partner Center
      (quelques minutes).
- [ ] **Numéro de version incrémenté** dans `identity.local.json` à chaque
      nouvelle soumission (`1.0.0.0` → `1.0.1.0`...).

## Soumission

Dans Partner Center, *Packages* → glissez `Alma.msix` → remplissez la fiche
(description, captures, politique de confidentialité, âge) → *Submit to the
Store*. Microsoft signe le paquet et le certifie (habituellement quelques
heures à quelques jours pour une appli `runFullTrust` — comptez plus large
pour la toute première soumission).

## Ce qui n'est PAS dans ce dossier (volontairement)

Aucune trace de facturation, de compte utilisateur, ou de backend — ce
n'est pas le sujet de cette étape. Voir la discussion sur la version avec
API pour la suite, le jour où elle sera construite.
