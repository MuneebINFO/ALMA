"""
Alma - application vocale.

Interface entierement pilotee a la voix : Alma ecoute des le lancement,
mais reste passif jusqu a ce qu on prononce son nom.

  - « Alma, quelle heure est-il »  -> la commande est executee
  - « Alma » seul                  -> il repond « Oui ? » et attend la suite
  - toute autre phrase               -> ignoree

La fenetre occupe TOUT l ecran sur lequel elle se trouve, sur un fond presque
noir, et ne montre qu une chose : l orbe, grand et centre, sous le sigle
A.L.M.A. C est le retour visuel qui montre que la voix est captee -- anneau
d onde deforme par le niveau du micro, couronne de barres, arcs en rotation,
poussiere en orbite, halo, et un noyau fait d un amas d etoiles. Au lancement,
la fenetre apparait en fondu et l orbe pousse un bref sursaut.

L historique des echanges existe mais ne s affiche pas : un bouton le fait
GLISSER depuis la droite, et l orbe retrecit en consequence pendant le
mouvement. Le bouton indique au passage combien de messages ont ete manques.

Raccourcis : Echap rend la fenetre ordinaire puis, une fois hors plein
ecran, remet Alma en veille. F11 revient au plein ecran, M coupe ou rallume
le micro, F1 montre l aide, la barre d espace rendort ou reveille -- comme un
clic sur l orbe.
"""

from __future__ import annotations

import math
import queue
import random
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

# Ambiance assombrie : un fond presque noir plutot que le bleu nuit d avant.
FOND = "#03050a"
FOND_CARTE = "#0a101a"
TEXTE = "#e6edf7"
TEXTE_DOUX = "#6b7d99"
BORDURE = "#141c2b"

# Largeur du panneau d historique, en pixels. Assez pour une phrase complete
# sans amputer l orbe.
LARGEUR_HISTORIQUE = 520

# Part du demi-cote qu occupe l orbe. Le reste est la marge qui empeche les
# graduations exterieures de sortir du cadre.
MARGE_ORBE = 0.94

# Animation d entree (fondu de la fenetre) et de glissement de l historique :
# nombre d images et intervalle entre chacune.
PAS_ENTREE = 20
PERIODE_ENTREE_MS = 16      # ~ 320 ms au total

PAS_HISTORIQUE = 16
PERIODE_HISTORIQUE_MS = 14  # ~ 220 ms au total


def _assouplir(progres: float) -> float:
    """Ease-out cubique : depart rapide, arrivee en douceur. Sert aux deux glissements."""
    return 1 - (1 - progres) ** 3


# Une couleur et un libelle par etat.
ETATS = {
    "demarrage":   ("#8b5cf6", "Démarrage..."),
    "calibration": ("#8b5cf6", "Calibration du micro..."),
    "veille":      ("#2b4a6f", "Dites « {nom} »"),
    "passif":      ("#2b4a6f", "Dites « {nom} »"),
    "voix":        ("#38bdf8", "Voix captée..."),
    "arme":        ("#22c55e", "Je vous écoute"),
    "reflexion":   ("#fbbf24", "Un instant..."),
    "execution":   ("#fbbf24", "Exécution..."),
    "reponse":     ("#a78bfa", "..."),
    "erreur":      ("#f87171", "Erreur"),
    "arret":       ("#3f4c63", "Micro coupé"),
}


def sigle(nom: str) -> str:
    """
    « ALMA » -> « A.L.M.A » : le monogramme affiche sous la barre du haut.

    Il etait ecrit en dur, ce qui allait tant que l assistant ne pouvait pas
    etre renomme. Un nom deja pointe ou deja espace est laisse tel quel :
    l utilisateur a alors ecrit ce qu il voulait voir.
    """
    nom = (nom or "").strip()
    if not nom or "." in nom or " " in nom:
        return nom.upper()
    return ".".join(nom.upper())


def melanger(couleur_a: str, couleur_b: str, facteur: float) -> str:
    """Interpole deux couleurs (sert aux transitions douces et au halo)."""
    a = couleur_a.lstrip("#")
    b = couleur_b.lstrip("#")
    canaux = []
    for i in (0, 2, 4):
        depart = int(a[i:i + 2], 16)
        arrivee = int(b[i:i + 2], 16)
        canaux.append(max(0, min(255, int(depart + (arrivee - depart) * facteur))))
    return "#%02x%02x%02x" % tuple(canaux)


class Orbe(tk.Canvas):
    """
    Orbe animé, qui occupe toute la place qu'on lui laisse.

    Rien n'est en pixels fixes : tout est exprimé en fraction du rayon
    disponible, si bien que l'orbe grandit avec la fenêtre au lieu de flotter
    au milieu d'un grand vide.

    Sept couches, du fond vers l'avant :

      1. un halo diffus, cercles concentriques fondus dans le fond ;
      2. une poussière d'étoiles en orbite lente, à distances et vitesses
         différentes -- c'est ce qui donne de la profondeur ;
      3. un anneau d'onde déformé par l'HISTORIQUE des niveaux sonores :
         l'onde tourne, et l'on voit passer ce qu'on vient de dire ;
      4. une contre-onde, plus fine, tournant à l'envers ;
      5. une couronne de barres radiales, un spectre qui bat avec la voix ;
      6. des arcs en rotation, gradués, à vitesses et sens différents ;
      7. le NOYAU : non pas un disque plein, mais un amas d'étoiles -- la
         boule elle-même est faite d'étoiles, plus denses vers le centre,
         chacune scintillant à son rythme, avec un point brillant au milieu
         pour que la couleur d'état reste lisible même de loin.

    Le niveau et la couleur sont lissés à chaque image : aucun changement
    brusque, ce qui donne un rendu fluide. Au lancement, une brève poussée
    d'amplitude fait flamber puis retomber l'orbe entier -- l'animation
    d'entrée, cousue directement dans ce que le niveau sonore fait déjà.
    """

    # 180 points SANS lissage : mesure faite, le lissage de Tk coute 9,7 ms
    # par image pour 132 points, contre 1,2 ms pour 180 points sans lui -- et
    # a ce rayon on ne voit pas la difference, les segments faisant deux
    # degres. Huit millisecondes gagnees sur un budget de vingt-cinq.
    POINTS = 180         # résolution de l'anneau d'onde
    HISTORIQUE = 64      # mémoire des niveaux, répartie autour du cercle
    # Couronne et poussiere exterieure allegees : l amas du noyau apporte
    # desormais l essentiel de la densite, la ou le regard se pose.
    BARRES = 38          # couronne de spectre
    ETOILES = 22         # poussiere en orbite, autour de l orbe
    # Amas du noyau. Mesure faite a plein ecran : une image coute une
    # douzaine de millisecondes autour de ce nombre, sur un budget de 33.
    ETOILES_COEUR = 80

    # Poussee d amplitude au demarrage, qui retombe d elle-meme : c est
    # l animation d entree. DECROISSANCE proche de 1 = extinction lente.
    INTRO_DEPART = 1.0
    INTRO_DECROISSANCE = 0.91
    INTRO_SEUIL = 0.01
    # 30 images par seconde : mesure faite, une image coute une douzaine de
    # millisecondes a cette taille. A 40 images par seconde, l orbe mangeait
    # les trois quarts d un coeur en permanence -- sur une machine qui doit
    # aussi ecouter le micro et transcrire.
    PERIODE_MS = 33

    def __init__(self, master) -> None:
        super().__init__(master, bg=FOND, highlightthickness=0)
        self.etat = "demarrage"
        self.couleur_courante = ETATS["demarrage"][0]
        self.niveau = 0.0
        self.niveau_lisse = 0.0
        self.phase = 0.0
        self.rotation = 0.0
        self.historique = [0.0] * self.HISTORIQUE
        self.largeur = 0
        self.hauteur = 0
        # Les étoiles gardent leur place d'une image à l'autre : les tirer au
        # hasard à chaque fois donnerait du grésillement, pas une orbite.
        self.etoiles = [
            (random.uniform(0, 2 * math.pi),        # angle de départ
             random.uniform(0.58, 1.00),            # distance, en rayons
             random.uniform(0.15, 0.55),            # vitesse propre
             random.uniform(0.35, 1.0))             # éclat
            for _ in range(self.ETOILES)
        ]
        # Meme principe pour l amas du noyau, mais la distance est elevee a
        # une puissance : cela concentre les points pres du centre, ce qui
        # donne l illusion d un volume plutot que d un nuage plat.
        self.etoiles_coeur = [
            (random.uniform(0, 2 * math.pi),
             random.uniform(0.0, 1.0) ** 2.2,       # serre l amas vers le centre
             random.uniform(0.10, 0.42),            # deriver lentement, sans tournoyer
             random.uniform(0.4, 1.0))
            for _ in range(self.ETOILES_COEUR)
        ]
        self.intro = self.INTRO_DEPART
        self._tache = None
        self.bind("<Configure>", self._redimensionner)
        self._animer()

    # -- pilotage -------------------------------------------------------------
    def definir_etat(self, etat: str) -> None:
        if etat in ETATS:
            self.etat = etat

    def definir_niveau(self, niveau: float) -> None:
        self.niveau = max(0.0, min(1.0, float(niveau)))

    def _redimensionner(self, evenement) -> None:
        self.largeur = evenement.width
        self.hauteur = evenement.height

    def arreter(self) -> None:
        """Interrompt l animation. Sans cela une image reste en vol."""
        if self._tache is not None:
            try:
                self.after_cancel(self._tache)
            except Exception:
                pass
            self._tache = None

    # -- rendu ----------------------------------------------------------------
    def _animer(self) -> None:
        # Lissage asymétrique : réaction vive à la voix, retombée douce.
        cible = self.niveau
        facteur = 0.45 if cible > self.niveau_lisse else 0.10
        self.niveau_lisse += (cible - self.niveau_lisse) * facteur

        self.historique.append(self.niveau_lisse)
        del self.historique[:-self.HISTORIQUE]

        self.phase += 0.055
        self.rotation += 0.9

        # Transition douce vers la couleur de l'état courant.
        couleur_cible = ETATS[self.etat][0]
        self.couleur_courante = melanger(self.couleur_courante, couleur_cible, 0.12)

        self.delete("all")
        if self.largeur > 20 and self.hauteur > 20:
            centre_x = self.largeur / 2.0
            centre_y = self.hauteur / 2.0
            # Le rayon de référence : tout le reste en découle. La marge
            # n'est pas décorative -- les graduations extérieures montent à
            # 1,02 rayon, et sans elle l'orbe était rogné en haut et en bas.
            rayon = min(self.largeur, self.hauteur) * 0.5 * MARGE_ORBE
            actif = self.etat in ("voix", "arme", "reflexion", "execution", "reponse")
            # Respiration lente au repos, amplitude sonore quand la voix parle.
            respiration = 0.10 + 0.05 * math.sin(self.phase * 0.6)
            amplitude = respiration + self.niveau_lisse * (0.85 if actif else 0.45)

            self._halo(centre_x, centre_y, rayon, amplitude)
            self._etoiles(centre_x, centre_y, rayon, amplitude)
            self._anneau_onde(centre_x, centre_y, rayon, amplitude)
            self._contre_onde(centre_x, centre_y, rayon, amplitude)
            self._barres(centre_x, centre_y, rayon, amplitude)
            self._arcs(centre_x, centre_y, rayon, amplitude)
            self._coeur(centre_x, centre_y, rayon, amplitude)
            self._flash_entree(centre_x, centre_y, rayon)

        self._tache = self.after(self.PERIODE_MS, self._animer)

    def _flash_entree(self, cx: float, cy: float, rayon: float) -> None:
        """
        Le sursaut au lancement : un anneau qui s'étend puis s'efface.

        Volontairement ISOLÉ de `amplitude` : la mélanger aux formules qui
        dépendent du niveau sonore aurait faussé leur mesure au tout premier
        appel, avant même que le vrai niveau n'ait été lu -- l'orbe « calme »
        d'un test aurait alors paru plus gonflé que l'orbe « fort ».
        """
        if self.intro <= 0:
            return
        progres = 1.0 - self.intro
        r = rayon * (0.30 + progres * 0.68)
        self.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=melanger(FOND, self.couleur_courante, self.intro * 0.9),
            fill="", width=max(1, round(3 * self.intro)), tags="entree",
        )
        self.intro = self.intro * self.INTRO_DECROISSANCE if self.intro > self.INTRO_SEUIL else 0.0

    def _halo(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """Dégradé radial simulé par des cercles de plus en plus sombres."""
        rayon_max = rayon * (0.56 + amplitude * 0.26)
        couches = 9
        for i in range(couches, 0, -1):
            r = rayon_max * (i / float(couches))
            couleur = melanger(FOND, self.couleur_courante, 0.03 + 0.058 * (couches - i))
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=couleur,
                             outline="", tags="halo")

    def _etoiles(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """
        Poussière en orbite : c'est elle qui donne la profondeur.

        Chaque point garde sa distance et sa vitesse, et scintille à son
        propre rythme -- sans quoi la couronne battrait d'un seul bloc.
        """
        for angle0, distance, vitesse, eclat in self.etoiles:
            angle = angle0 + self.phase * vitesse * 0.5
            r = rayon * distance * (0.72 + amplitude * 0.16)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            scintillement = 0.55 + 0.45 * math.sin(self.phase * 2.2 + angle0 * 5)
            taille = rayon * 0.006 * (0.6 + eclat) * (0.8 + amplitude)
            self.create_oval(
                x - taille, y - taille, x + taille, y + taille,
                fill=melanger(FOND, self.couleur_courante,
                              0.20 + 0.55 * eclat * scintillement),
                outline="", tags="etoiles",
            )

    def _rayon_onde(self, angle: float, base: float, echelle: float,
                    memoire: float) -> float:
        """Rayon de l'onde à cet angle : quatre harmoniques et la mémoire."""
        ondulation = (
            math.sin(angle * 4 + self.phase * 1.5) * 0.42
            + math.sin(angle * 7 - self.phase * 1.0) * 0.30
            + math.sin(angle * 11 + self.phase * 0.7) * 0.18
            + math.sin(angle * 16 - self.phase * 0.5) * 0.10
        )
        return base + ondulation * echelle + memoire

    def _anneau_onde(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """Anneau déformé par l'historique des niveaux : l'onde semble tourner."""
        base = rayon * (0.62 + amplitude * 0.085)
        echelle = rayon * (0.030 + amplitude * 0.080)
        points = []
        for i in range(self.POINTS):
            angle = 2 * math.pi * i / self.POINTS
            memoire = self.historique[int(i / self.POINTS * self.HISTORIQUE) - 1]
            r = self._rayon_onde(angle, base, echelle, memoire * rayon * 0.055)
            points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])
        self.create_polygon(points, outline=melanger(FOND, self.couleur_courante, 0.85),
                            fill="", width=2, tags="onde")

    def _contre_onde(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """Une seconde onde, plus fine, qui tourne à l'envers du premier."""
        base = rayon * (0.53 + amplitude * 0.06)
        echelle = rayon * (0.018 + amplitude * 0.048)
        points = []
        for i in range(self.POINTS):
            angle = 2 * math.pi * i / self.POINTS
            ondulation = (
                math.sin(angle * 5 - self.phase * 1.2) * 0.5
                + math.sin(angle * 9 + self.phase * 0.8) * 0.3
            )
            r = base + ondulation * echelle
            points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])
        self.create_polygon(points, outline=melanger(FOND, self.couleur_courante, 0.38),
                            fill="", width=1, tags="contre_onde")

    def _barres(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """
        Couronne de barres radiales : le spectre de ce qu'on vient de dire.

        Chaque barre lit un instant différent de l'historique, donc la vague
        se propage autour du cercle au lieu de battre d'un seul bloc.
        """
        interieur = rayon * 0.71
        for i in range(self.BARRES):
            angle = 2 * math.pi * i / self.BARRES
            memoire = self.historique[int(i / self.BARRES * self.HISTORIQUE) - 1]
            battement = 0.5 + 0.5 * math.sin(angle * 3 + self.phase * 1.1)
            longueur = rayon * (0.016 + 0.11 * memoire + 0.028 * amplitude * battement)
            debut = interieur
            fin = interieur + longueur
            self.create_line(
                cx + debut * math.cos(angle), cy + debut * math.sin(angle),
                cx + fin * math.cos(angle), cy + fin * math.sin(angle),
                fill=melanger(FOND, self.couleur_courante, 0.25 + 0.50 * memoire),
                width=2, tags="barres",
            )

    def _arcs(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """Arcs concentriques en rotation, à vitesses et sens différents."""
        for index, (part, etendue, vitesse, epaisseur) in enumerate(
            ((0.76, 70, 1.0, 2), (0.86, 44, -0.62, 2), (0.95, 22, 0.35, 1))
        ):
            r = rayon * (part + amplitude * 0.035)
            depart = (self.rotation * vitesse + index * 120) % 360
            self.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=depart, extent=etendue, style="arc",
                outline=melanger(FOND, self.couleur_courante, 0.55 - index * 0.11),
                width=epaisseur, tags="arcs",
            )
        # Graduations fixes : elles donnent une échelle à la rotation, qui
        # sinon glisse sans qu'on voie sur quoi.
        for i in range(12):
            angle = 2 * math.pi * i / 12
            interieur = rayon * 0.995
            exterieur = rayon * (1.0 if i % 4 else 1.02)
            self.create_line(
                cx + interieur * math.cos(angle), cy + interieur * math.sin(angle),
                cx + exterieur * math.cos(angle), cy + exterieur * math.sin(angle),
                fill=melanger(FOND, self.couleur_courante, 0.16 if i % 4 else 0.34),
                width=1, tags="arcs",
            )

    def _coeur(self, cx: float, cy: float, rayon: float, amplitude: float) -> None:
        """
        Le noyau : un amas d'étoiles, pas un disque plein.

        Une lueur très atténuée sert d'ancre -- sans elle, la couleur d'état
        se lirait mal de loin, diluée par le vide entre les points -- et
        l'amas porte tout le mouvement : chaque étoile dérive et scintille à
        son propre rythme, plus grosse et plus vive près du centre pour
        donner l'illusion d'un volume plutôt que d'un nuage plat.
        """
        r = rayon * (0.28 + amplitude * 0.085)

        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=melanger(FOND, self.couleur_courante, 0.30),
                         outline="", tags="coeur")

        for angle0, distance, vitesse, eclat in self.etoiles_coeur:
            angle = angle0 + self.phase * vitesse
            # Bornées à l'intérieur de la lueur : l'amas se tient DANS le
            # noyau, il n'en déborde pas -- et la mesure du noyau reste
            # celle de la lueur seule, sans bruit d'étoiles.
            d = distance * r * 0.9
            x = cx + d * math.cos(angle)
            y = cy + d * math.sin(angle)
            scintillement = 0.5 + 0.5 * math.sin(self.phase * 2.6 + angle0 * 7)
            proximite = 1.0 - distance
            taille = rayon * (0.006 + 0.020 * proximite) * (0.6 + eclat)
            melange = min(0.92, 0.35 + 0.55 * eclat * scintillement + 0.25 * proximite)
            self.create_oval(
                x - taille, y - taille, x + taille, y + taille,
                fill=melanger(self.couleur_courante, "#ffffff", melange),
                outline="", tags="coeur",
            )

        # Un point net au centre : le seul repère fixe, pour que l'œil
        # retrouve toujours l'orbe même quand l'amas scintille fort.
        centre = r * 0.16 * (0.8 + 0.2 * math.sin(self.phase * 1.7))
        self.create_oval(cx - centre, cy - centre, cx + centre, cy + centre,
                         fill=melanger(self.couleur_courante, "#ffffff", 0.85),
                         outline="", tags="coeur")


class BouleNiveau(tk.Canvas):
    """
    Une bille qui respire avec le micro.

    Elle repond a une question simple, et qu on ne peut pas se poser sans
    elle : est-ce que ma voix arrive ? Sans ce retour, « je n ai rien saisi »
    ne dit pas si le micro n a rien entendu ou si la transcription a echoue.

    Cinq couches, du fond vers l avant : un halo diffus, une couronne de
    POINTILLES graduee qui s allume avec le niveau, une poussiere d ETOILES
    en orbite, un anneau d onde deforme par l historique des niveaux -- c est
    lui qui fait voyager la vague autour du cercle au lieu de la faire
    pulser d un bloc --, et le noyau.
    """

    PERIODE_MS = 33
    GRADUATIONS = 40       # les pointilles de la couronne
    ETOILES = 14           # la poussiere en orbite
    MEMOIRE = 24           # niveaux gardes, pour l anneau d onde

    def __init__(self, parent, taille: int = 96) -> None:
        super().__init__(parent, width=taille, height=taille, bg=FOND,
                         highlightthickness=0, bd=0)
        self.taille = taille
        self.niveau = 0.0          # valeur lissee, celle qui est dessinee
        self.cible = 0.0
        self.actif = False         # une voix franchit le seuil
        self.phase = 0.0           # rotation lente de la couronne
        self.historique = [0.0] * self.MEMOIRE
        # Chaque etoile a son orbite, sa vitesse et son scintillement propres :
        # toutes identiques, elles formeraient un motif, pas de la poussiere.
        self.etoiles = [
            {
                "angle": random.uniform(0, math.tau),
                "orbite": random.uniform(0.30, 0.46),
                "vitesse": random.uniform(-0.010, 0.010),
                "eclat": random.uniform(0, math.tau),
                "taille": random.uniform(0.8, 1.8),
            }
            for _ in range(self.ETOILES)
        ]
        self._vivante = True
        self._battre()

    def definir_niveau(self, niveau: float, actif: bool = False) -> None:
        self.cible = max(0.0, min(1.0, float(niveau)))
        self.actif = bool(actif)

    def arreter(self) -> None:
        self._vivante = False

    def _battre(self) -> None:
        if not self._vivante:
            return
        # Montee franche, descente douce : c est ce qui donne l impression de
        # suivre la voix plutot que de trembler.
        poids = 0.5 if self.cible > self.niveau else 0.12
        self.niveau += (self.cible - self.niveau) * poids
        self.historique.append(self.niveau)
        del self.historique[:-self.MEMOIRE]
        self.phase += 0.012 + self.niveau * 0.05
        for etoile in self.etoiles:
            etoile["angle"] += etoile["vitesse"] * (1 + self.niveau * 3)
            etoile["eclat"] += 0.09
        try:
            self._dessiner()
            self.after(self.PERIODE_MS, self._battre)
        except tk.TclError:
            self._vivante = False

    def _dessiner(self) -> None:
        self.delete("all")
        centre = self.taille / 2
        couleur = ETATS["voix"][0] if self.actif else ETATS["veille"][0]
        base = self.taille * 0.15
        rayon = base + self.niveau * self.taille * 0.17

        self._halo(centre, rayon, couleur)
        self._couronne(centre, couleur)
        self._etoiles(centre, couleur)
        self._onde(centre, rayon, couleur)
        self.create_oval(centre - rayon, centre - rayon, centre + rayon, centre + rayon,
                         fill=couleur, outline="")

    def _halo(self, centre, rayon, couleur) -> None:
        """Deux cercles diffus : le volume, avant le detail."""
        for part, force in ((0.22, 0.30), (0.12, 0.16)):
            halo = rayon + self.taille * part * (0.5 + self.niveau)
            self.create_oval(centre - halo, centre - halo, centre + halo, centre + halo,
                             fill=melanger(FOND, couleur, force * (0.4 + self.niveau)),
                             outline="")

    def _couronne(self, centre, couleur) -> None:
        """
        Les pointilles graduees, en rotation lente.

        Un point sur quatre est plus long : sans ces reperes, la couronne
        tourne sans qu on voie qu elle tourne.
        """
        dedans = self.taille * 0.40
        for i in range(self.GRADUATIONS):
            angle = self.phase + i * math.tau / self.GRADUATIONS
            marque = (i % 4 == 0)
            longueur = self.taille * (0.055 if marque else 0.028) * (0.5 + self.niveau)
            # Les graduations s allument par vagues plutot que toutes ensemble.
            onde = 0.5 + 0.5 * math.sin(angle * 3 - self.phase * 4)
            force = 0.18 + 0.55 * self.niveau * onde + (0.1 if marque else 0)
            x1 = centre + math.cos(angle) * dedans
            y1 = centre + math.sin(angle) * dedans
            x2 = centre + math.cos(angle) * (dedans + longueur)
            y2 = centre + math.sin(angle) * (dedans + longueur)
            self.create_line(x1, y1, x2, y2, width=2 if marque else 1,
                             fill=melanger(FOND, couleur, min(1.0, force)))

    def _etoiles(self, centre, couleur) -> None:
        """La poussiere en orbite : chacune scintille pour son compte."""
        for etoile in self.etoiles:
            scintille = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(etoile["eclat"]))
            force = min(1.0, (0.16 + 0.6 * self.niveau) * scintille)
            rayon_orbite = self.taille * etoile["orbite"] * (1 + self.niveau * 0.10)
            x = centre + math.cos(etoile["angle"]) * rayon_orbite
            y = centre + math.sin(etoile["angle"]) * rayon_orbite
            demi = etoile["taille"] * (0.6 + self.niveau * 0.8)
            self.create_oval(x - demi, y - demi, x + demi, y + demi,
                             fill=melanger(FOND, couleur, force), outline="")

    def _onde(self, centre, rayon, couleur) -> None:
        """
        L anneau d onde, deforme par l HISTORIQUE des niveaux.

        Prendre le niveau courant ferait pulser le cercle d un bloc ; prendre
        les derniers fait voyager la vague autour de lui, comme une voix qui
        arrive.
        """
        points = []
        pas = math.tau / 48
        for i in range(48):
            angle = i * pas
            vieux = self.historique[i * self.MEMOIRE // 48]
            ecart = self.taille * 0.05 * vieux * math.sin(angle * 3 + self.phase * 2)
            r = rayon + self.taille * 0.075 + ecart
            points.extend((centre + math.cos(angle) * r, centre + math.sin(angle) * r))
        if points:
            self.create_polygon(points, outline=melanger(FOND, couleur,
                                                         0.25 + 0.45 * self.niveau),
                                fill="", width=1, smooth=True)


class CarteChoix(tk.Canvas):
    """
    Une reponse possible, dessinee plutot que posee.

    Tkinter ne sait pas arrondir un bouton ni l animer : sur un panneau qui
    est le premier contact avec l application, cela se voit tout de suite.
    Un Canvas, lui, dessine ce qu on veut -- un rectangle arrondi, un liseré
    qui s allume au survol, un accent a gauche quand la carte a le focus.

    Le clavier compte autant que la souris : fleches pour parcourir, Entree
    pour choisir. Personne ne devrait avoir a lacher le clavier ici.
    """

    LARGEUR = 420
    HAUTEUR = 62
    RAYON = 10

    def __init__(self, parent, texte: str, au_choix, accent: str) -> None:
        super().__init__(parent, width=self.LARGEUR, height=self.HAUTEUR,
                         bg=FOND, highlightthickness=0, bd=0, cursor="hand2")
        self.texte = texte
        self.au_choix = au_choix
        self.accent = accent
        self.survole = False
        self.vise = False          # la carte que le clavier designe
        self._dessiner()
        self.bind("<Button-1>", lambda _e: self.au_choix())
        self.bind("<Enter>", lambda _e: self._etat(survole=True))
        self.bind("<Leave>", lambda _e: self._etat(survole=False))

    def _etat(self, survole=None, vise=None) -> None:
        if survole is not None:
            self.survole = survole
        if vise is not None:
            self.vise = vise
        self._dessiner()

    def viser(self, oui: bool) -> None:
        self._etat(vise=oui)

    def _arrondi(self, x1, y1, x2, y2, r, **options) -> None:
        """Un rectangle aux coins arrondis, en polygone lisse."""
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, **options)

    def _dessiner(self) -> None:
        self.delete("all")
        eveille = self.survole or self.vise
        fond = melanger(FOND_CARTE, self.accent, 0.16 if eveille else 0.0)
        bord = self.accent if eveille else BORDURE
        self._arrondi(1, 1, self.LARGEUR - 1, self.HAUTEUR - 1, self.RAYON,
                      fill=fond, outline=bord, width=1)
        # L accent a gauche : c est lui qui dit « celle-ci », sans deplacer
        # le texte ni changer sa taille -- rien ne doit sauter au survol.
        if eveille:
            self._arrondi(1, 12, 5, self.HAUTEUR - 12, 2,
                          fill=self.accent, outline="")
        self.create_text(28, self.HAUTEUR / 2, text=self.texte, anchor="w",
                         font=tkfont.Font(family="Segoe UI", size=15),
                         fill=TEXTE if eveille else melanger(TEXTE, FOND, 0.15))


class ChampNom(tk.Frame):
    """
    Un champ de saisie sans boite : juste le texte et un trait dessous.

    La boite grise d un Entry ordinaire jure avec un fond presque noir. Le
    trait, lui, s allume quand on ecrit -- le meme signe que l accent des
    cartes, pour que les deux sortes de questions se repondent.
    """

    def __init__(self, parent, defaut: str, au_valide, accent: str) -> None:
        super().__init__(parent, bg=FOND)
        self.accent = accent
        self.saisie = tk.Entry(
            self, font=tkfont.Font(family="Segoe UI", size=26), bg=FOND,
            fg=TEXTE, insertbackground=accent, bd=0, relief="flat",
            justify="center", width=18, highlightthickness=0,
        )
        self.saisie.pack()
        if defaut:
            self.saisie.insert(0, defaut)
            self.saisie.select_range(0, "end")
        self.trait = tk.Canvas(self, height=2, width=360, bg=FOND,
                               highlightthickness=0, bd=0)
        self.trait.pack(pady=(10, 0))
        self._eclat = 0.0
        self._cible = 0.0
        self._vivant = True
        self.saisie.bind("<FocusIn>", lambda _e: self._viser(1.0))
        self.saisie.bind("<FocusOut>", lambda _e: self._viser(0.0))
        self.saisie.bind("<Return>", lambda _e: au_valide(self.saisie.get()))
        self._battre()

    def _viser(self, valeur: float) -> None:
        self._cible = valeur

    def valeur(self) -> str:
        return self.saisie.get()

    def focus_saisie(self) -> None:
        self.saisie.focus_set()
        self._viser(1.0)

    def arreter(self) -> None:
        self._vivant = False

    def _battre(self) -> None:
        if not self._vivant:
            return
        self._eclat += (self._cible - self._eclat) * 0.2
        try:
            self.trait.delete("all")
            largeur = int(self.trait.cget("width"))
            self.trait.create_line(0, 1, largeur, 1,
                                   fill=melanger(BORDURE, self.accent, self._eclat),
                                   width=2)
            self.after(33, self._battre)
        except tk.TclError:
            self._vivant = False


class AlmaApp:
    """Fenetre principale : orbe, statut, transcription et journal."""

    def __init__(self, root: tk.Tk, assistant) -> None:
        self.root = root
        self.assistant = assistant
        self.evenements: queue.Queue = queue.Queue()
        self.ecoute_active = threading.Event()
        self.thread_audio: threading.Thread | None = None
        self.stt = None
        self.nom = assistant.name          # nom affiche, issu de la config

        # La session d ecoute vit dans l assistant : les commandes peuvent
        # ainsi consulter le contexte (« recherche Damso » apres « va sur
        # YouTube »), et le mode texte en profite aussi.
        self.moteur = assistant.moteur
        # Renommer l assistant change ce que la fenetre affiche : le titre,
        # le sigle, le statut. Le coeur previent, l interface se remet a jour.
        assistant.signal_personnalisation = self._personnalisation_changee
        assistant.signal_attente = self._attente_annoncee

        root.title(assistant.name)
        root.configure(bg=FOND)
        root.minsize(620, 480)
        self.historique_visible = False
        self.non_lus = 0
        # Panneau du premier lancement : absent tant qu il n y a rien a demander.
        self.installation = None
        self._suite_installation = None
        self._recevoir_entendu = None
        self.boule = None          # bille de niveau du premier lancement
        self._champ = None         # champ de saisie du premier lancement
        self._cartes = []          # cartes de reponse, pour le clavier
        self._vise = 0             # celle que le clavier designe
        self._cadre_question = None
        self._ecoute_installation = None   # drapeau de l etape en cours
        self._prises_installation = 0
        self._travaux_ecoute = None        # travaux postes au service
        self._fin_ecoute = None
        self._thread_ecoute = None
        self._largeur_panneau = 0
        self._animation_historique = None

        # Invisible avant meme le premier affichage : sans quoi la fenetre
        # apparaitrait un instant a pleine opacite avant que le fondu ne
        # commence. `-alpha` est gere par le compositeur Windows, pas par ce
        # qui est dessine -- aucun cout pour l orbe.
        try:
            root.attributes("-alpha", 0.0)
        except Exception:
            pass

        self._construire()
        self._plein_ecran(True)
        # De quoi en sortir : sans barre de titre, il n y aurait plus aucune
        # prise sur la fenetre.
        root.bind("<Escape>", self._sur_echap)
        root.bind("<F11>", lambda _e: self._plein_ecran(not self.plein_ecran))
        # Le clavier remplace les boutons retires : aucun champ de saisie
        # n existe dans cette fenetre, rien d autre ne capte ces touches.
        root.bind("<Key>", self._sur_touche)
        self._brancher_sorties()
        # Le changement d ecran est signale par un cadre lumineux. Tkinter
        # n etant pilotable que depuis son thread principal, on passe par
        # root.after() : les commandes, elles, tournent dans un thread.
        assistant.signal_ecran = self.signaler_ecran
        self.root.after(40, self._traiter_evenements)
        # Un court delai pour laisser le gestionnaire de fenetres placer le
        # plein ecran pendant qu on ne le voit pas encore, puis le fondu.
        self.root.after(120, self._animer_entree)

    # -- construction ---------------------------------------------------------
    def _construire(self) -> None:
        police_sigle = tkfont.Font(family="Segoe UI", size=30, weight="bold")
        police_statut = tkfont.Font(family="Segoe UI", size=15)
        police_entendu = tkfont.Font(family="Segoe UI", size=19)
        police_texte = tkfont.Font(family="Segoe UI", size=10)
        police_journal = tkfont.Font(family="Segoe UI", size=11)

        # Une barre haute discrete : elle ne doit rien disputer a l orbe.
        entete = tk.Frame(self.root, bg=FOND)
        entete.pack(fill="x", padx=26, pady=(16, 0))
        tk.Label(entete, text="assistant vocal local", font=police_texte,
                 bg=FOND, fg=TEXTE_DOUX).pack(side="left")
        self.voyant = tk.Label(entete, text="●  hors ligne", font=police_texte,
                               bg=FOND, fg=TEXTE_DOUX)
        self.voyant.pack(side="right")

        # Le corps se partage entre la colonne centrale et l historique. Ce
        # dernier POUSSE la colonne au lieu de la recouvrir : en superposition
        # il masquait un bouton et la fin de la phrase entendue.
        self.corps = tk.Frame(self.root, bg=FOND)
        self.corps.pack(fill="both", expand=True)

        self.colonne = tk.Frame(self.corps, bg=FOND)
        self.colonne.pack(side="left", fill="both", expand=True)

        self.etiquette_sigle = tk.Label(self.colonne, text=sigle(self.nom),
                                        font=police_sigle,
                                        bg=FOND, fg=TEXTE)
        self.etiquette_sigle.pack(pady=(6, 0))

        self.orbe = Orbe(self.colonne)
        self.orbe.pack(fill="both", expand=True, padx=20, pady=6)
        # Un clic dessus reveille ou rendort : c est la sortie de secours
        # quand le micro ne comprend pas le « stop » qu on lui dit.
        self.orbe.configure(cursor="hand2")
        self.orbe.bind("<Button-1>", self.basculer_veille)

        self.etiquette_statut = tk.Label(self.colonne, text="Démarrage...",
                                         font=police_statut, bg=FOND, fg=TEXTE_DOUX)
        self.etiquette_statut.pack()

        # Ce qu Alma a compris. Deux lignes reservees : sans hauteur fixe, la
        # phrase ferait sauter l orbe a chaque mot entendu.
        self.etiquette_entendu = tk.Label(self.colonne, text="", font=police_entendu,
                                          bg=FOND, fg=TEXTE, wraplength=900, height=2)
        self.etiquette_entendu.pack(pady=(6, 4))

        # Micro et aide n'ont plus de bouton : l'un se demande a la voix
        # (« Alma, que sais-tu faire »), l'autre passe par le clavier -- voir
        # _sur_touche. Il ne reste ici que ce qui n'a pas d'autre chemin.
        boutons = tk.Frame(self.root, bg=FOND)
        boutons.pack(pady=(0, 20))
        self.bouton_historique = self._bouton(boutons, "Historique", self.basculer_historique)
        self.bouton_historique.pack(side="left", padx=5)
        self._bouton(boutons, "Quitter", self.quitter).pack(side="left", padx=5)

        # L historique existe des le depart -- il se remplit meme cache -- mais
        # il n est pas POSE tant qu on ne le demande pas.
        self.panneau = tk.Frame(self.corps, bg=BORDURE, width=0)
        # Sans cela le cadre se retrecirait sur son contenu et la largeur
        # demandee ne servirait a rien.
        self.panneau.pack_propagate(False)
        entete_panneau = tk.Frame(self.panneau, bg=FOND_CARTE)
        entete_panneau.pack(fill="x", padx=1, pady=(1, 0))
        tk.Label(entete_panneau, text="Historique", font=police_texte,
                 bg=FOND_CARTE, fg=TEXTE_DOUX).pack(side="left", padx=16, pady=10)
        tk.Button(entete_panneau, text="✕", command=self.basculer_historique,
                  bg=FOND_CARTE, fg=TEXTE_DOUX, activebackground=BORDURE,
                  activeforeground=TEXTE, bd=0, relief="flat", cursor="hand2",
                  font=police_texte, padx=14).pack(side="right")

        self.journal = tk.Text(self.panneau, bg=FOND_CARTE, fg=TEXTE, font=police_journal,
                               bd=0, padx=16, pady=14, wrap="word", state="disabled")
        self.journal.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=(0, 1))
        barre = tk.Scrollbar(self.panneau, command=self.journal.yview, bg=FOND_CARTE, bd=0)
        barre.pack(side="right", fill="y", pady=(0, 1))
        self.journal.configure(yscrollcommand=barre.set)
        self.journal.tag_configure("moi", foreground="#38bdf8")
        self.journal.tag_configure("assistant", foreground="#a78bfa")
        self.journal.tag_configure("erreur", foreground="#f87171")
        self.journal.tag_configure("corps", foreground=TEXTE)

    def basculer_historique(self) -> None:
        """
        Montre ou cache l'historique, en le faisant GLISSER plutôt que surgir.

        La colonne centrale — et l'orbe avec elle — se redimensionne à
        chaque image de l'animation : c'est ce qui fait bouger la boule en
        conséquence, sans rien lui dire de spécial, puisqu'elle écoute déjà
        son `<Configure>` pour suivre la taille qu'on lui laisse.
        """
        self.historique_visible = not self.historique_visible
        if self.historique_visible:
            # `before` compte : sans lui, la colonne centrale, qui s'étend,
            # prendrait toute la place et le panneau n'aurait plus rien.
            self.panneau.configure(width=max(1, self._largeur_panneau))
            self.panneau.pack(side="right", fill="y", before=self.colonne)
            self.journal.see("end")
            self.non_lus = 0
        self._rafraichir_bouton_historique()
        self._glisser_historique(self._largeur_panneau,
                                 LARGEUR_HISTORIQUE if self.historique_visible else 0)

    def _largeur_historique_au_pas(self, depart: int, cible: int, pas: int) -> int:
        """La largeur du panneau à cette image de l'animation. Pure : sans effet de bord."""
        progres = _assouplir(min(1.0, (pas + 1) / PAS_HISTORIQUE))
        return round(depart + (cible - depart) * progres)

    def _glisser_historique(self, depart: int, cible: int, pas: int = 0) -> None:
        """
        Anime la largeur du panneau, une image à la fois.

        Repart TOUJOURS d'où l'animation précédente en était (`depart` vient
        de `self._largeur_panneau`, mis à jour à chaque image) : interrompre
        une ouverture par un clic pour refermer ne fait donc pas sauter le
        panneau à sa largeur maximale avant de revenir en arrière.
        """
        if pas == 0 and self._animation_historique is not None:
            self.root.after_cancel(self._animation_historique)
            self._animation_historique = None

        self._largeur_panneau = self._largeur_historique_au_pas(depart, cible, pas)
        self.panneau.configure(width=max(1, self._largeur_panneau))

        if pas + 1 < PAS_HISTORIQUE:
            self._animation_historique = self.root.after(
                PERIODE_HISTORIQUE_MS,
                lambda: self._glisser_historique(depart, cible, pas + 1),
            )
        else:
            self._animation_historique = None
            if cible == 0:
                self.panneau.pack_forget()

    def _rafraichir_bouton_historique(self) -> None:
        """
        Le bouton dit combien de messages ont été manqués.

        L'historique étant caché par défaut, rien ne signalerait autrement
        qu'ALMA a répondu quelque chose pendant qu'on regardait ailleurs.
        """
        if self.historique_visible:
            libelle = "Masquer l'historique"
        elif self.non_lus:
            libelle = "Historique (" + str(self.non_lus) + ")"
        else:
            libelle = "Historique"
        self.bouton_historique.configure(text=libelle)

    def _animer_entree(self, pas: int = 0) -> None:
        """Fait apparaître la fenêtre en fondu, plutôt que d'un bloc."""
        progres = _assouplir(min(1.0, (pas + 1) / PAS_ENTREE))
        try:
            self.root.attributes("-alpha", progres)
        except Exception:
            return  # transparence indisponible : la fenetre restera opaque
        if pas + 1 < PAS_ENTREE:
            self.root.after(PERIODE_ENTREE_MS, lambda: self._animer_entree(pas + 1))

    def _plein_ecran(self, actif: bool) -> None:
        """
        Occupe tout l'écran sur lequel la fenêtre se trouve.

        Tkinter place le plein écran sur le moniteur qui porte la fenêtre :
        rien à calculer, et l'assistant suit l'écran où on l'a mis.
        """
        self.plein_ecran = bool(actif)
        try:
            self.root.attributes("-fullscreen", self.plein_ecran)
        except Exception:
            # Certains gestionnaires de fenetres refusent : on se rabat sur
            # une fenetre ordinaire plutot que de ne rien afficher.
            self.plein_ecran = False
            self.root.geometry("1000x820")

    def _bouton(self, parent, texte: str, commande) -> tk.Button:
        return tk.Button(parent, text=texte, command=commande, bg=FOND_CARTE, fg=TEXTE,
                         activebackground=BORDURE, activeforeground=TEXTE, bd=0,
                         font=tkfont.Font(family="Segoe UI", size=10),
                         padx=18, pady=9, relief="flat", cursor="hand2")

    def montrer_aide(self) -> None:
        threading.Thread(target=self._executer, args=("aide", "text"), daemon=True).start()

    def _on_ecrit(self) -> bool:
        """Le clavier appartient-il a un champ de saisie ?"""
        try:
            return isinstance(self.root.focus_get(), tk.Entry)
        except Exception:                     # pragma: no cover - defensif
            return False

    def _sur_touche(self, evenement) -> None:
        """
        M coupe ou reessaie le micro, F1 montre l'aide, Espace rendort.

        SAUF pendant qu on ecrit. La fenetre n a longtemps eu aucun champ de
        saisie, et ces raccourcis d une seule lettre etaient sans danger. Le
        panneau d installation en a introduit un -- et taper « Muneeb »
        declenchait le « m » : l ecoute continue demarrait au milieu de
        l installation, ouvrait le micro depuis son propre thread, et le
        service d installation lisait ensuite CE flux-la. PortAudio rendait
        alors des fragments (un tiers de seconde de voix, puis du silence :
        de quoi animer la bille et ne rien transcrire), puis plantait le
        processus. Une espace dans un prenom, elle, rendormait Alma.
        """
        if self._on_ecrit():
            return
        if evenement.keysym == "F1":
            self.montrer_aide()
        elif evenement.keysym == "space":
            self.basculer_veille()
        elif (evenement.char or "").lower() == "m":
            self.basculer_micro()

    def _sur_echap(self, _evenement=None) -> None:
        """
        Échap rend la main.

        D'abord le plein écran — sans barre de titre, c'est la seule prise
        qu'on ait sur la fenêtre. Ensuite seulement, la touche remet Alma en
        veille, comme la barre d'espace et le clic sur l'orbe.
        """
        if self.plein_ecran:
            self._plein_ecran(False)
            return
        self.endormir()

    # -- mise en veille -------------------------------------------------------
    def endormir(self) -> None:
        """
        Remet Alma en veille tout de suite, sans passer par la voix.

        Le chemin vocal (« stop », « mets-toi en veille », « go to sleep »)
        reste le principal, mais il dépend de la transcription d'un ordre
        très court — celui que la reconnaissance rate le plus souvent. Un
        clic, une touche : il faut que ça marche à tous les coups.
        """
        self.assistant.interrompre()
        self.assistant.interrompre_parole()
        if self.moteur.arme:
            self.assistant.bruit("veille")
        self.moteur.desarmer()
        self.assistant.oublier_contexte()
        self.evenements.put(("entendu", ""))
        self.evenements.put(("statut", (self._etat_repos(), "")))

    def basculer_veille(self, _evenement=None) -> None:
        """Le même geste dans les deux sens : réveiller, ou rendormir."""
        if not self.ecoute_active.is_set():
            return                      # micro coupé : rien à réveiller
        if self.moteur.arme:
            self.endormir()
            return
        self.moteur.armer()
        self.evenements.put(("statut", ("arme", "")))

    # -- pont assistant / interface -------------------------------------------
    def _brancher_sorties(self) -> None:
        """Redirige les sorties de l assistant vers le journal de la fenetre."""
        app = self

        class SortieGraphique:
            source = "voice"

            def read(self, prompt: str = "") -> str:
                return ""

            def write(self, texte: str) -> None:
                app.evenements.put(("journal", (app.nom, texte)))

            def ask(self, question: str) -> str:
                return app.demander(question)

            def close(self) -> None:
                pass

        self.assistant.io = SortieGraphique()

    def demander(self, question: str) -> str:
        """Confirmation modale, demandee depuis le thread audio."""
        from tkinter import messagebox

        resultat: queue.Queue = queue.Queue()
        self.root.after(0, lambda: resultat.put(
            "oui" if messagebox.askyesno(self.nom, question) else "non"
        ))
        return resultat.get()

    def journaliser(self, qui: str, texte: str, tag: str = "assistant") -> None:
        if not texte:
            return
        if not self.historique_visible:
            self.non_lus += 1
            self._rafraichir_bouton_historique()
        self.journal.configure(state="normal")
        self.journal.insert("end", qui + " : ", tag)
        self.journal.insert("end", texte.strip() + "\n\n", "corps")
        self.journal.see("end")
        self.journal.configure(state="disabled")

    def definir_statut(self, etat: str, detail: str = "") -> None:
        couleur, libelle = ETATS.get(etat, ETATS["veille"])
        # « {nom} » est remplace par le nom configure : renommer l assistant
        # ne demande de toucher a aucun libelle.
        libelle = libelle.replace("{nom}", self.nom)
        self.orbe.definir_etat(etat)
        self.etiquette_statut.configure(text=detail or libelle, fg=couleur)

    # -- boucle d evenements --------------------------------------------------
    def _traiter_evenements(self) -> None:
        """Tkinter n est pas thread-safe : seule cette boucle touche a l interface."""
        try:
            while True:
                type_evenement, charge = self.evenements.get_nowait()
                if type_evenement == "niveau":
                    niveau, etat = charge
                    self.orbe.definir_niveau(niveau)
                    if etat:
                        self.definir_statut(etat)
                elif type_evenement == "statut":
                    self.definir_statut(*charge)
                elif type_evenement == "entendu":
                    self.etiquette_entendu.configure(
                        text=("« " + charge + " »") if charge else ""
                    )
                elif type_evenement == "voyant":
                    couleur, texte = charge
                    self.voyant.configure(text="●  " + texte, fg=couleur)
                elif type_evenement == "journal":
                    qui, texte = charge
                    self.journaliser(qui, texte, "moi" if qui == "Vous" else "assistant")
                elif type_evenement == "erreur":
                    self.journaliser(self.nom, charge, "erreur")
                elif type_evenement == "installation_niveau":
                    boule = getattr(self, "boule", None)
                    if boule is not None:
                        boule.definir_niveau(*charge)
                elif type_evenement == "installation_entendu":
                    recevoir = getattr(self, "_recevoir_entendu", None)
                    if recevoir is not None:
                        recevoir(charge)
                elif type_evenement == "renomme":
                    self.root.title(charge)
                    self.etiquette_sigle.configure(text=sigle(charge))
                    self.definir_statut(self._etat_repos(), "")
                elif type_evenement == "quitter":
                    self.quitter()
                    return
        except queue.Empty:
            pass
        self._suivre_fenetre_utilisateur()
        self._rafraichir_compte_a_rebours()
        self.root.after(40, self._traiter_evenements)

    def _suivre_fenetre_utilisateur(self) -> None:
        """
        Retient la fenêtre non-Alma que l'utilisateur a devant lui.

        Quand Alma passe au premier plan -- on lui a parlé, elle est plein
        écran -- les commandes ne sauraient plus « où j'étais ». Cette mémoire,
        rafraîchie 25 fois par seconde, le leur redonne.
        """
        try:
            import ctypes

            user32 = ctypes.windll.user32
            if not self.assistant.poignee_alma:
                brut = self.root.winfo_id()
                self.assistant.poignee_alma = user32.GetAncestor(brut, 2) or brut
            self.assistant.noter_fenetre_utilisateur(user32.GetForegroundWindow())
        except Exception:
            pass

    def signaler_ecran(self, index: int) -> None:
        """Illumine brievement le contour de l ecran choisi."""
        def dessiner():
            from core import flash_ecran

            flash_ecran.flasher(self.root, index, couleur=ETATS["voix"][0])

        try:
            self.root.after(0, dessiner)
        except Exception:
            pass

    def _rafraichir_compte_a_rebours(self) -> None:
        """Affiche le temps restant de la session, tant qu elle est ouverte."""
        if self.orbe.etat != "arme":
            return
        restant = int(self.moteur.secondes_restantes())
        if restant <= 0:
            self.definir_statut("veille")
            return
        self.etiquette_statut.configure(
            text="Je vous écoute — " + str(restant) + " s", fg=ETATS["arme"][0]
        )

    # -- execution ------------------------------------------------------------
    def _executer(self, texte: str, source: str) -> None:
        """Route la demande hors du thread graphique pour ne pas figer l interface."""
        self.evenements.put(("statut", ("execution", "")))
        try:
            reponse = self.assistant.handle(texte, source=source)
        except Exception as exc:
            self.evenements.put(("erreur", "Erreur interne : " + str(exc)))
            self.evenements.put(("statut", (self._etat_repos(), "")))
            return

        # Le bruitage remplace ce qui n est pas dit. Une action reussie ne se
        # commente pas a voix haute (voir `informatif`) : sans lui, le silence
        # qui suit ne se distingue pas d une commande perdue.
        if reponse.ok and not reponse.speak:
            self.assistant.bruit("ok")
        elif not reponse.ok:
            self.assistant.bruit("erreur")

        if reponse.text:
            if reponse.ok:
                self.evenements.put(("journal", (self.nom, reponse.text)))
            else:
                self.evenements.put(("erreur", reponse.text))
            if reponse.speak and self.assistant.speaks:
                # Lecture NON bloquante : sans cela le micro reste sourd
                # pendant qu il parle, et on ne peut pas lui couper la parole.
                self.evenements.put(("statut", ("reponse", "Je réponds...")))
                self.assistant.tts.say(reponse.text)

        if reponse.should_exit:
            self.evenements.put(("quitter", None))
            return
        self.evenements.put(("statut", (self._etat_repos(), "")))

    # -- premier lancement ----------------------------------------------------
    def installation_necessaire(self) -> bool:
        """Reste-t-il les quatre questions du premier lancement a poser ?"""
        from core import premier_lancement

        return premier_lancement.est_necessaire(self.assistant.config)

    def _preparer_micro(self) -> bool:
        """
        Cree le moteur de reconnaissance sans lancer l ecoute continue.

        Le premier lancement a besoin d entendre une fois -- « dites-le a
        voix haute » -- alors que la boucle du micro n a pas encore demarre.
        """
        if getattr(self, "stt", None) is None:
            try:
                from core.stt import SpeechToText

                self.stt = SpeechToText(self.assistant.config)
                self.assistant.stt = self.stt
            except Exception:
                return False
        return bool(getattr(self.stt, "available", False))

    def montrer_installation(self, quand_fini) -> None:
        """
        Pose les questions du premier lancement, dans la fenetre elle-meme.

        Pas une boite de dialogue : c est le premier contact avec
        l application, et il doit lui ressembler. L orbe attend derriere,
        l ecoute ne demarre qu une fois fini -- sinon Alma repondrait aux
        reponses qu on lui donne.
        """
        from core import premier_lancement

        self._suite_installation = quand_fini
        self._questions = list(premier_lancement.QUESTIONS)
        self._index_question = 0
        self._travaux_ecoute = queue.Queue()
        self._fin_ecoute = threading.Event()
        self._thread_ecoute = threading.Thread(target=self._service_ecoute,
                                               name="alma-installation",
                                               daemon=True)
        self._thread_ecoute.start()
        self.colonne.pack_forget()
        self.installation = tk.Frame(self.corps, bg=FOND)
        self.installation.pack(fill="both", expand=True)
        self._poser_question()

    def _langue_installation(self) -> str:
        return str(self.assistant.config.get("general.language", "fr"))[:2]

    def _poser_question(self) -> None:
        """Dessine la question courante, ou termine s il n en reste plus."""
        self._ranger_question()
        if self._index_question >= len(self._questions):
            self._finir_installation()
            return

        question = self._questions[self._index_question]
        langue = self._langue_installation()
        anglais = langue == "en"
        accent = ETATS["arme"][0] if question.ecoute else ETATS["veille"][0]

        cadre = tk.Frame(self.installation, bg=FOND)
        cadre.place(relx=0.5, rely=0.5, anchor="center")
        self._cadre_question = cadre

        self._jalons(cadre, accent)
        tk.Label(cadre, text=question.titre(langue),
                 font=tkfont.Font(family="Segoe UI", size=28), bg=FOND, fg=TEXTE,
                 wraplength=860, justify="center").pack()
        if question.aide(langue):
            tk.Label(cadre, text=question.aide(langue),
                     font=tkfont.Font(family="Segoe UI", size=12), bg=FOND,
                     fg=TEXTE_DOUX, wraplength=640,
                     justify="center").pack(pady=(12, 0))

        corps = tk.Frame(cadre, bg=FOND)
        corps.pack(pady=(34, 0))
        if question.ecoute:
            self._poser_question_ecoutee(question, corps, cadre, anglais)
        elif question.libre:
            self._poser_question_libre(question, corps, anglais, accent)
        else:
            self._poser_question_fermee(question, corps, langue, accent)

        # Discret, mais present : personne ne doit rester coince ici.
        passer = tk.Label(cadre, text="Skip" if anglais else "Passer",
                          font=tkfont.Font(family="Segoe UI", size=10),
                          bg=FOND, fg=melanger(FOND, TEXTE_DOUX, 0.8),
                          cursor="hand2")
        passer.pack(pady=(30, 0))
        passer.bind("<Button-1>", lambda _e: self._repondre(""))
        passer.bind("<Enter>", lambda _e: passer.configure(fg=TEXTE_DOUX))
        passer.bind("<Leave>",
                    lambda _e: passer.configure(fg=melanger(FOND, TEXTE_DOUX, 0.8)))

        self.root.bind("<Up>", self._viser_precedent)
        self.root.bind("<Down>", self._viser_suivant)
        self.root.bind("<Return>", self._valider_vise)
        self._glisser_question(cadre)

    def _ranger_question(self) -> None:
        """Eteint ce qui vit encore avant de redessiner."""
        if self.boule is not None:
            self.boule.arreter()
            self.boule = None
        if self._champ is not None:
            self._champ.arreter()
            self._champ = None
        if self._ecoute_installation is not None:
            self._ecoute_installation.clear()
            self._ecoute_installation = None
        self._recevoir_entendu = None
        self._cartes = []
        self._vise = 0
        for touche in ("<Up>", "<Down>", "<Return>"):
            try:
                self.root.unbind(touche)
            except tk.TclError:
                pass
        for enfant in self.installation.winfo_children():
            enfant.destroy()

    def _jalons(self, cadre, accent: str) -> None:
        """
        Ou l on en est : un trait segmente, pas un compteur.

        « Etape 3 sur 6 » demande de lire et de compter. Un trait se voit.
        """
        total = len(self._questions)
        largeur, espace = 34, 8
        toile = tk.Canvas(cadre, width=total * (largeur + espace), height=4,
                          bg=FOND, highlightthickness=0, bd=0)
        toile.pack(pady=(0, 30))
        for rang in range(total):
            x = rang * (largeur + espace)
            if rang < self._index_question:
                couleur = melanger(FOND, accent, 0.45)
            elif rang == self._index_question:
                couleur = accent
            else:
                couleur = BORDURE
            toile.create_line(x, 2, x + largeur, 2, fill=couleur, width=3,
                              capstyle="round")

    def _poser_question_fermee(self, question, corps, langue: str,
                               accent: str) -> None:
        """Les reponses possibles, en cartes -- souris ou clavier."""
        for possible in question.choix:
            carte = CarteChoix(
                corps, possible.libelle(langue),
                (lambda valeur=possible.valeur: self._repondre(valeur)),
                accent,
            )
            carte.pack(pady=4)
            self._cartes.append(carte)
        if self._cartes:
            self._cartes[0].viser(True)

    def _poser_question_libre(self, question, corps, anglais: bool,
                              accent: str) -> None:
        """Un champ sans boite, et le bouton qui va avec."""
        self._champ = ChampNom(corps, question.defaut, self._repondre, accent)
        self._champ.pack()
        self._champ.focus_saisie()
        carte = CarteChoix(
            corps, "Continue" if anglais else "Continuer",
            lambda: self._repondre(self._champ.valeur() if self._champ else ""),
            accent,
        )
        carte.pack(pady=(26, 0))
        self._cartes.append(carte)

    # -- clavier --------------------------------------------------------------
    def _viser_suivant(self, _evenement=None) -> None:
        self._deplacer_visee(1)

    def _viser_precedent(self, _evenement=None) -> None:
        self._deplacer_visee(-1)

    def _deplacer_visee(self, pas: int) -> None:
        if self._on_ecrit() or len(self._cartes) < 2:
            return
        self._cartes[self._vise].viser(False)
        self._vise = (self._vise + pas) % len(self._cartes)
        self._cartes[self._vise].viser(True)

    def _valider_vise(self, _evenement=None) -> None:
        # Le champ gere sa propre touche Entree : la laisser passer ici
        # validerait deux fois.
        if self._on_ecrit():
            return
        if self._cartes:
            self._cartes[self._vise].au_choix()

    # -- transition -----------------------------------------------------------
    def _glisser_question(self, cadre, pas: int = 0) -> None:
        """
        La question arrive en glissant depuis la droite, et en s eclaircissant.

        Tkinter ne sait pas rendre un cadre transparent : le mouvement porte
        donc l apparition, et la couleur du titre fait le reste.
        """
        total = 14
        progres = _assouplir(min(1.0, (pas + 1) / total))
        try:
            cadre.place_configure(relx=0.5 + 0.06 * (1 - progres))
            for enfant in cadre.winfo_children():
                if (enfant.winfo_class() == "Label"
                        and enfant.cget("fg") not in (TEXTE_DOUX,)):
                    enfant.configure(fg=melanger(FOND, TEXTE, progres))
        except tk.TclError:
            return
        if pas + 1 < total:
            self.root.after(16, lambda: self._glisser_question(cadre, pas + 1))

    # Combien de formes differentes suffisent. Au-dela, on n apprend plus
    # grand-chose et on retient quelqu un devant un ecran pour rien.
    PRISES_SUFFISANTES = 3
    # Borne dure du nombre d ecoutes : sans elle, une piece bruyante ferait
    # tourner la boucle indefiniment.
    ECOUTES_MAXIMUM = 8

    def _poser_question_ecoutee(self, question, corps, cadre, anglais: bool) -> None:
        """
        Ecouter le nom, plusieurs fois, et garder CE QUI ARRIVE.

        Il n y a rien a comprendre ici. On ne cherche pas la bonne
        orthographe -- on l a deja, elle vient d etre tapee. On cherche la
        forme sous laquelle la reconnaissance vocale la rend, pour la
        reconnaitre plus tard : « Muneeb » revient en « Mounib », et c est
        « Mounib » qu il faut retenir.

        Donc aucune reponse n est mauvaise. Une transcription bizarre est
        exactement ce qu on veut. Le seul echec est le silence.

        Et AUCUN bouton pour demarrer : a partir du moment ou l on demande
        de prononcer, l ecoute doit deja tourner. Demander de parler puis
        exiger un clic avant d ecouter, c est rater la premiere fois a tous
        les coups.
        """
        attendu = str(self.assistant.config.get(
            "general.user_name" if question.echo_de == "nom_utilisateur"
            else "general.assistant_name", "") or "")
        accent = ETATS["arme"][0]

        if attendu:
            # Une PHRASE, pas le nom seul : un mot isole ne donne aucun
            # contexte a la reconnaissance vocale, et elle ne rend rien.
            #
            # `before=corps` : sans cela elle se retrouve SOUS les boutons,
            # alors qu on doit la lire avant de parler. `corps` est deja pose
            # quand on arrive ici.
            tk.Label(cadre, text=question.phrase(
                         self._langue_installation(), attendu),
                     font=tkfont.Font(family="Segoe UI", size=24),
                     bg=FOND, fg=TEXTE, wraplength=820,
                     justify="center").pack(pady=(22, 0), before=corps)

        if not self._preparer_micro():
            carte = CarteChoix(corps, "Continue" if anglais else "Continuer",
                               lambda: self._repondre(""), accent)
            carte.pack()
            self._cartes.append(carte)
            return

        self.boule = BouleNiveau(corps)
        self.boule.pack(pady=(0, 8))
        # Les formes deja captees, montrees telles quelles : c est la preuve
        # que quelque chose a ete retenu.
        prises = tk.Label(corps, text="", font=tkfont.Font(family="Segoe UI", size=14),
                          bg=FOND, fg=accent)
        prises.pack(pady=(0, 4))
        etat = tk.Label(corps, text="", font=tkfont.Font(family="Segoe UI", size=11),
                        bg=FOND, fg=TEXTE_DOUX)
        etat.pack(pady=(0, 20))

        continuer = CarteChoix(corps, "Continue" if anglais else "Continuer",
                               lambda: self._repondre(""), accent)
        continuer.pack()
        self._cartes = [continuer]
        continuer.viser(True)

        entendues: list = []
        self._prises_installation = 0

        def rendre(charge) -> None:
            from core import premier_lancement

            entendu, pic, raison = charge
            if self.boule is not None:
                self.boule.definir_niveau(0.0)

            if charge == ("", -1.0, "prete"):
                etat.configure(text="Listening…" if anglais else "J'écoute…")
                return

            forme = premier_lancement.extraire_nom(entendu, attendu)
            if forme:
                # On RETIENT tout de suite. Une forme deja connue ne compte
                # pas deux fois, mais elle n est pas un echec non plus.
                premier_lancement.repondre(self.assistant, question.cle, entendu)
                if forme not in entendues:
                    entendues.append(forme)
                self._prises_installation = len(entendues)
                prises.configure(text="  ·  ".join(entendues))
                self.assistant.bruit("ok")
                if len(entendues) >= self.PRISES_SUFFISANTES:
                    etat.configure(text="That's plenty." if anglais
                                   else "C'est largement assez.")
                    continuer.texte = "Done" if anglais else "Terminé"
                    continuer._dessiner()
                else:
                    etat.configure(text="Once more?" if anglais
                                   else "Encore une fois ?")
                return

            etat.configure(text=self._pourquoi_rien(pic, raison, anglais))

        self._recevoir_entendu = rendre
        # On ne lance PAS de thread ici : le micro appartient au service
        # d ecoute, ouvert au debut de l installation et ferme a la fin. Deux
        # threads qui lisent le meme flux PortAudio ne levent pas -- ils
        # plantent le processus.
        self._ecoute_installation = threading.Event()
        self._ecoute_installation.set()
        self._travaux_ecoute.put(self._ecoute_installation)

    def _service_ecoute(self) -> None:
        """
        L UNIQUE thread qui touche le micro pendant l installation.

        Il y a DEUX etapes d ecoute -- votre nom, puis le sien. Chacune avec
        son thread, c etait deux threads lisant tour a tour le meme flux
        PortAudio : le second plantait le processus, sans trace Python
        puisque le plantage est natif. Un service unique ouvre, lit et ferme
        le flux ; les etapes ne font que lui poster du travail.
        """
        prepare = False
        try:
            while not self._fin_ecoute.is_set():
                try:
                    actif = self._travaux_ecoute.get(timeout=0.2)
                except queue.Empty:
                    continue
                if actif is None:
                    return
                if not prepare:
                    # Le silence se mesure une fois, avant la premiere
                    # ecoute. Le mesurer pendant reviendrait a mesurer la
                    # voix qu on vient de demander.
                    try:
                        self.stt.preparer()
                    except Exception:
                        pass
                    prepare = True
                self._ecouter_pour(actif)
        finally:
            # Ferme depuis le thread qui a ouvert : c est toute la regle.
            try:
                self.stt.fermer()
            except Exception:
                pass

    def _ecouter_pour(self, actif) -> None:
        """Les prises successives d une etape, tant qu elle est affichee."""
        if not actif.is_set():
            return
        self.evenements.put(("installation_entendu", ("", -1.0, "prete")))

        for _ in range(self.ECOUTES_MAXIMUM):
            if not actif.is_set() or self._fin_ecoute.is_set():
                return
            pic = [0.0]

            def niveau(valeur, etat_audio):
                pic[0] = max(pic[0], valeur)
                self.evenements.put(
                    ("installation_niveau", (valeur, etat_audio == "parole")))

            try:
                entendu = self.stt.listen_live(
                    on_level=niveau, timeout=10.0, phrase_limit=5.0,
                    doit_continuer=actif.is_set)
            except Exception:
                entendu = ""
            if not actif.is_set():
                return
            raison = getattr(self.stt, "derniere_raison", "")
            self.evenements.put(("installation_entendu", (entendu, pic[0], raison)))
            if self._prises_installation >= self.PRISES_SUFFISANTES:
                return

    @staticmethod
    def _pourquoi_rien(pic: float, raison: str, anglais: bool) -> str:
        """
        Pourquoi rien n a ete retenu -- et donc quoi faire.

        Jamais « pas compris » : il n y a rien a comprendre. Ou la voix n est
        pas arrivee, ou le service n a pas repondu.
        """
        if raison == "injoignable":
            return ("Speech service unreachable — are you online?" if anglais else
                    "Reconnaissance injoignable — êtes-vous connecté ?")
        if pic <= 0.25:
            return ("I heard nothing — is the microphone on?" if anglais else
                    "Je n'ai rien entendu — le micro est-il actif ?")
        return ("Nothing came back. Once more?" if anglais else
                "Rien n'est revenu. Encore une fois ?")

    def _repondre(self, reponse: str) -> None:
        """Retient la reponse et passe a la suivante."""
        from core import premier_lancement

        question = self._questions[self._index_question]
        premier_lancement.repondre(self.assistant, question.cle, reponse)
        self._index_question += 1
        self._poser_question()

    def _finir_installation(self) -> None:
        """Range le panneau, rend la main a l orbe, et lance l ecoute."""
        from core import premier_lancement

        premier_lancement.terminer(self.assistant)
        # Le service rend le micro avant que l ecoute continue ne le reprenne.
        self._fin_ecoute.set()
        self._travaux_ecoute.put(None)
        self._thread_ecoute.join(timeout=3)
        self._thread_ecoute = None
        self.installation.destroy()
        self.installation = None
        # `before` n accepte pas None : le panneau d historique n est POSE que
        # lorsqu il est visible, et c est seulement alors qu il faut passer
        # devant lui.
        if self.historique_visible:
            self.colonne.pack(side="left", fill="both", expand=True,
                              before=self.panneau)
        else:
            self.colonne.pack(side="left", fill="both", expand=True)
        self.journaliser(self.assistant.name,
                         premier_lancement.bienvenue(self.assistant.name,
                                                     self._langue_installation()))
        if self._suite_installation is not None:
            suite, self._suite_installation = self._suite_installation, None
            suite()

    def _attente_annoncee(self, texte: str) -> None:
        """
        « Je cherche » s affiche pendant que ca cherche.

        Appele depuis le thread audio, comme le reste : tout passe par la
        file d evenements, Tkinter n etant pilotable que par son thread.
        """
        self.evenements.put(("statut", ("reflexion", texte)))

    def _personnalisation_changee(self) -> None:
        """
        Un reglage vient de changer sous nos pieds.

        Appele depuis le thread audio : rien n est touche directement ici --
        Tkinter n est pilotable que depuis son thread principal -- tout passe
        par la file d evenements, comme le reste.
        """
        self.nom = self.assistant.name
        self.evenements.put(("renomme", self.nom))

    def _etat_repos(self) -> str:
        """Etat affiche entre deux commandes."""
        if not self.ecoute_active.is_set():
            return "arret"
        return "arme" if self.moteur.arme else "veille"

    # -- micro ----------------------------------------------------------------
    def demarrer_ecoute(self) -> None:
        """Prepare le micro et lance l ecoute continue."""
        if self.stt is None:
            from core.stt import SpeechToText

            self.evenements.put(("statut", ("demarrage", "Préparation du micro...")))
            self.stt = SpeechToText(self.assistant.config)
            self.assistant.stt = self.stt

        if not self.stt.available:
            self.evenements.put((
                "erreur",
                "Micro indisponible : " + (self.stt.error or "aucun périphérique détecté")
                + " Lancez « python diagnostic_micro.py » pour en savoir plus, "
                  "ou appuyez sur M pour réessayer.",
            ))
            self.evenements.put(("statut", ("erreur", "Micro indisponible")))
            self.evenements.put(("voyant", (ETATS["erreur"][0], "micro absent")))
            return

        self.ecoute_active.set()
        if self.thread_audio is None or not self.thread_audio.is_alive():
            self.thread_audio = threading.Thread(target=self._boucle_micro,
                                                 name="alma-micro", daemon=True)
            self.thread_audio.start()

    def basculer_micro(self) -> None:
        if self.ecoute_active.is_set():
            self.ecoute_active.clear()
            self.moteur.desarmer()
            self.definir_statut("arret")
            self.etiquette_entendu.configure(text="")
            self.voyant.configure(text="●  micro coupé (M pour le rallumer)", fg=TEXTE_DOUX)
        else:
            self.demarrer_ecoute()

    def _boucle_micro(self) -> None:
        """
        Ecoute en continu. Alma entend tout, mais n agit que si son nom a
        ete prononce (ou s il vient d etre reveille).
        """
        from core import wake

        def sur_niveau(niveau: float, etat_audio: str) -> None:
            if etat_audio == "calibration":
                etat = "calibration"
            elif etat_audio == "parole":
                etat = "voix"
                # On coupe la parole DES LA DETECTION de la voix, pas apres
                # la transcription : attendre reviendrait a finir sa phrase
                # pendant que l utilisateur parle.
                #
                # La detection, elle, exige un niveau plus haut tant qu Alma
                # parle (voir FACTEUR_PENDANT_LA_PAROLE) : arriver ici pendant
                # qu elle parle veut donc bien dire que QUELQU UN parle.
                self.assistant.interrompre_parole()
                # Et on arrete ce qui est en cours, pour la meme raison :
                # transcrire « arrete » demande plus d une seconde, pendant
                # laquelle la page continuerait de defiler. Parler suffit.
                self.assistant.interrompre()
            else:
                etat = self._etat_repos()
            self.evenements.put(("niveau", (niveau, etat)))

        self.evenements.put(("statut", ("calibration", "Calibration du micro...")))
        seuil = self.stt.recalibrate(1.2, on_level=sur_niveau)
        self.evenements.put(("voyant", (ETATS["veille"][0], "à l'écoute")))
        self.evenements.put((
            "journal",
            (self.nom, "Je suis à l'écoute. Dites « " + self.nom + " » pour m'activer, "
                       "ou « " + self.nom + " » suivi directement de votre demande. "
                       "Pour me remettre en veille : « stop », « " + self.nom
                       + ", mets-toi en veille », « go to sleep » — ou un clic "
                         "sur l'orbe."),
        ))
        if seuil <= 0:
            self.evenements.put(("erreur", "Seuil de détection nul : le micro ne capte rien."))

        while self.ecoute_active.is_set():
            self.evenements.put(("statut", (self._etat_repos(), "")))
            try:
                texte = self.stt.listen_live(
                    on_level=sur_niveau,
                    timeout=6.0,
                    doit_continuer=self.ecoute_active.is_set,
                    voix_active=self.assistant.tts.parle,
                )
            except Exception as exc:
                self.evenements.put(("erreur", "Erreur du micro : " + str(exc)))
                break

            if not self.ecoute_active.is_set():
                break
            if not texte:
                continue           # silence, ou parole non comprise

            # On lui coupe la parole des qu on parle -- sauf si le micro a
            # simplement capte sa propre voix dans les haut-parleurs.
            if self.assistant.tts.parle():
                if self._est_son_echo(texte):
                    continue
                self.assistant.tts.arreter()

            analyse = self.moteur.analyser(texte)

            if analyse.etat == wake.IGNORE:
                # On montre quand meme ce qui a ete entendu : l utilisateur voit
                # que le micro fonctionne, meme si Alma ne reagit pas.
                self.evenements.put(("entendu", texte))
                continue

            self.evenements.put(("entendu", texte))

            if analyse.etat == wake.FIN_SESSION:
                # « arrête » pendant un défilement doit arrêter le défilement,
                # pas refermer la session. Le défilement a déjà été stoppé dès
                # qu'on a entendu une voix : `vient_d_interrompre` s'en
                # souvient, sans quoi le mot serait pris pour un adieu.
                if self.assistant.interrompre() or self.assistant.vient_d_interrompre():
                    self.moteur.armer()          # la session continue
                    self.evenements.put(("journal", ("Vous", texte)))
                    self.evenements.put(("journal", (self.nom, "J'arrête.")))
                    self.evenements.put(("statut", ("arme", "")))
                    continue
                from core import text_utils

                self.assistant.bruit("veille")
                reponse = wake.accuse_fin(text_utils.detect_language(
                    text_utils.normalize(texte)))
                self.assistant.oublier_contexte()
                self.evenements.put(("journal", ("Vous", texte)))
                self.evenements.put(("journal", (self.nom, reponse)))
                self.evenements.put(("entendu", ""))
                self.evenements.put(("statut", ("veille", "")))
                if self.assistant.speaks:
                    self._dire_jusqu_au_bout(reponse)
                continue

            if analyse.etat == wake.REVEIL_SEUL:
                self.assistant.bruit("reveil")
                reponse = wake.accuse_reception()
                self.evenements.put(("journal", ("Vous", texte)))
                self.evenements.put(("journal", (self.nom, reponse)))
                self.evenements.put(("statut", ("arme", "")))
                if self.assistant.speaks:
                    # `cacher` : la replique est pre-synthetisee, donc immediate.
                    self.assistant.tts.say(reponse, cacher=True)
                continue

            if analyse.mot_appel_detecte:
                self.assistant.bruit("reveil")
            commande = analyse.commande
            self.evenements.put(("journal", ("Vous", commande)))
            self.evenements.put(("statut", ("reflexion", "")))
            self._executer(commande, "voice")

        self.evenements.put(("niveau", (0.0, "arret")))
        self.evenements.put(("voyant", (TEXTE_DOUX, "micro coupé")))

    def _dire_jusqu_au_bout(self, replique: str) -> None:
        """
        Dit une replique COURTE sans reprendre l ecoute avant la fin.

        « Je vous ecoute », « Tres bien » : une seconde, pre-synthetisee, donc
        immediate. Rendre la main tout de suite rouvrait le micro pendant
        qu elle parlait -- et elle se coupait au milieu. Rien d utile ne se
        dit pendant ce temps : l utilisateur vient tout juste de parler.

        Les REPONSES, elles, restent non bloquantes : on doit pouvoir couper
        un long resume d un mot.
        """
        self.assistant.tts.say(replique, cacher=True)
        try:
            self.assistant.tts.wait()
        except Exception:                           # pragma: no cover - defensif
            pass

    def _est_son_echo(self, propos: str) -> bool:
        """
        Le micro a-t-il simplement capte la voix de l assistant ?

        Deliberement PRUDENT : un ordre court n est jamais considere comme un
        echo. Nos propres phrases contiennent le nom de l assistant, si bien
        qu un « Alma » lance pendant qu il parle serait sinon pris pour un
        renvoi de son haut-parleur -- et ignore.
        """
        from core import text_utils

        en_cours = text_utils.normalize(self.assistant.tts.texte_en_cours)
        if not en_cours.strip():
            return False
        if self.moteur.separer_mot_appel(propos)[0]:
            return False
        mots = [m for m in text_utils.tokenize(text_utils.normalize(propos)) if len(m) >= 4]
        if len(mots) < 3:
            return False
        communs = sum(1 for m in mots if m in en_cours)
        return communs / len(mots) >= 0.75

    # -- fermeture ------------------------------------------------------------
    def quitter(self) -> None:
        self.ecoute_active.clear()
        try:
            # Le micro reste ouvert tant qu on ecoute : il faut le rendre.
            self.stt.fermer()
        except Exception:
            pass
        try:
            self.assistant.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def _conscience_dpi() -> None:
    """
    Declare l application consciente du DPI, AVANT toute fenetre.

    Sans cela Tkinter raisonne en pixels virtuels : sur un ecran 1920x1200
    affiche a 125 %, il croit disposer de 1536x960, et le plein ecran ne
    couvre alors que les deux tiers de l ecran. core.desktop fait deja cet
    appel, mais il est importe trop tard -- la fenetre existe deja.
    """
    import ctypes

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass          # hors Windows, ou deja declare : sans consequence


def main(argv=None) -> int:
    """Point d entree de l application."""
    import argparse

    parser = argparse.ArgumentParser(description="Alma - assistant vocal")
    parser.add_argument("--config", metavar="FICHIER", help="fichier de configuration")
    parser.add_argument("--mute", action="store_true", help="ne pas lire les réponses à voix haute")
    parser.add_argument("--sans-micro", action="store_true",
                        help="démarrer sans activer le micro")
    args = parser.parse_args(argv)

    from config import load_config
    from core.assistant import Assistant

    config = load_config(args.config)
    if args.mute:
        config.set("voice.speak_responses", False)

    _conscience_dpi()
    root = tk.Tk()
    assistant = Assistant(config=config)
    app = AlmaApp(root, assistant)
    root.protocol("WM_DELETE_WINDOW", app.quitter)

    def demarrer() -> None:
        moteur = getattr(assistant.tts, "moteur_actif", "aucun")
        libelle = {"neuronal": "voix neuronale", "sapi5": "voix locale"}.get(moteur, "sans voix")
        app.evenements.put((
            "voyant",
            (ETATS["veille"][0] if moteur != "aucun" else TEXTE_DOUX, libelle),
        ))
        if not args.sans_micro:
            app.demarrer_ecoute()
        else:
            app.definir_statut("arret")

    # Au tout premier lancement, les quatre questions passent avant le micro :
    # sans elles Alma repondrait aux reponses, et il ne saurait toujours pas
    # comment s appeler.
    if app.installation_necessaire():
        root.after(300, lambda: app.montrer_installation(demarrer))
    else:
        # L ecoute demarre automatiquement : l application est vocale par nature.
        root.after(300, demarrer)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
