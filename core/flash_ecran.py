"""
Signal visuel de changement d ecran : le contour de l ecran s illumine
brievement.

Une fenetre sans bordure, toujours au premier plan et transparente au clic,
couvre l ecran vise et n affiche qu un cadre lumineux. Elle apparait et
disparait en quelques centaines de millisecondes, puis se detruit.

Contrainte : Tkinter n est pilotable que depuis son thread principal. Toutes
les fonctions d ici doivent donc etre appelees via root.after(), ce dont
l interface se charge.
"""

from __future__ import annotations

import logging
import math

log = logging.getLogger(__name__)

DUREE_MS = 650          # duree totale de l animation
INTERVALLE_MS = 16      # ~60 images par seconde
EPAISSEUR_MIN = 6
EPAISSEUR_MAX = 22
COULEUR_TRANSPARENTE = "#010203"   # teinte improbable, rendue invisible


def facteur_dpi(root) -> float:
    """
    Rapport entre pixels physiques et points logiques.

    Les rectangles d ecran viennent de l API Windows en pixels physiques,
    alors que Tkinter positionne ses fenetres en points logiques. Sur un
    ecran a 125 %, ignorer ce rapport place le cadre a cote de l ecran.
    """
    try:
        import ctypes

        largeur_physique = ctypes.windll.user32.GetSystemMetrics(0)
        largeur_logique = root.winfo_screenwidth()
        if largeur_logique > 0 and largeur_physique > 0:
            return largeur_physique / largeur_logique
    except Exception as exc:
        log.debug("Facteur DPI indeterminable : %s", exc)
    return 1.0


def flasher(root, rect, couleur: str = "#38bdf8", duree_ms: int = DUREE_MS) -> bool:
    """
    Illumine le contour d un ecran.

    `rect` est le rectangle physique (gauche, haut, droite, bas) de l ecran.
    Retourne False si la fenetre n a pas pu etre creee -- l assistant
    continue alors sans signal visuel plutot que d echouer.
    """
    try:
        import tkinter as tk

        facteur = facteur_dpi(root)
        gauche, haut, droite, bas = [int(v / facteur) for v in rect]
        largeur, hauteur = droite - gauche, bas - haut
        if largeur <= 0 or hauteur <= 0:
            return False

        cadre = tk.Toplevel(root)
        cadre.overrideredirect(True)
        cadre.attributes("-topmost", True)
        cadre.geometry("%dx%d+%d+%d" % (largeur, hauteur, gauche, haut))
        try:
            # La couleur de fond devient transparente ET laisse passer les
            # clics : le cadre ne gene donc pas ce qui se trouve dessous.
            cadre.attributes("-transparentcolor", COULEUR_TRANSPARENTE)
        except Exception:
            pass

        toile = tk.Canvas(cadre, width=largeur, height=hauteur,
                          bg=COULEUR_TRANSPARENTE, highlightthickness=0)
        toile.pack()
    except Exception as exc:
        log.debug("Cadre lumineux impossible : %s", exc)
        return False

    debut = [0]

    def image():
        avancement = debut[0] / duree_ms
        if avancement >= 1.0:
            try:
                cadre.destroy()
            except Exception:
                pass
            return
        # Montee puis descente : le cadre enfle et s efface d un seul geste.
        intensite = math.sin(math.pi * avancement)
        epaisseur = EPAISSEUR_MIN + (EPAISSEUR_MAX - EPAISSEUR_MIN) * intensite
        try:
            cadre.attributes("-alpha", max(0.05, intensite))
            toile.delete("all")
            demi = epaisseur / 2
            toile.create_rectangle(demi, demi, largeur - demi, hauteur - demi,
                                   outline=couleur, width=epaisseur)
        except Exception:
            return
        debut[0] += INTERVALLE_MS
        root.after(INTERVALLE_MS, image)

    image()
    return True
