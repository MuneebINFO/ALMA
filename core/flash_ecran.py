"""
Signal visuel de changement d ecran : le contour de l ecran s illumine
brievement.

Une fenetre sans bordure, toujours au premier plan et transparente au clic,
couvre l ecran vise et n affiche qu un cadre lumineux. Elle apparait et
disparait en quelques centaines de millisecondes, puis se detruit.

Deux contraintes Windows se croisent ici :

  - Tkinter n est pilotable que depuis son thread principal ; toutes les
    fonctions d ici doivent donc etre appelees via root.after(), ce dont
    l interface se charge.
  - le cadre doit etre cree dans un contexte DPI « par moniteur », sinon
    Windows le redimensionne sur les ecrans dont l echelle differe de celle
    de l ecran principal et il ne couvre plus qu une partie de l ecran.
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


def flasher(root, index: int, couleur: str = "#38bdf8",
            duree_ms: int = DUREE_MS) -> bool:
    """
    Illumine le contour de l ecran numero `index`.

    Retourne False si la fenetre n a pas pu etre creee -- l assistant
    continue alors sans signal visuel plutot que d echouer.
    """
    try:
        import tkinter as tk

        from core import desktop

        # Tout ce qui touche aux coordonnees se fait dans le meme contexte
        # DPI : l ecran est mesure et la fenetre est posee en pixels reels.
        with desktop.dpi_par_moniteur():
            ecran = next((e for e in desktop.ecrans() if e.index == index), None)
            if ecran is None:
                return False
            gauche, haut, droite, bas = ecran.rect
            largeur, hauteur = droite - gauche, bas - haut
            if largeur <= 0 or hauteur <= 0:
                return False

            cadre = tk.Toplevel(root)
            cadre.overrideredirect(True)
            cadre.attributes("-topmost", True)
            # « +-1080 » et non « -1080 » : un signe seul designerait le bord
            # oppose de l ecran au lieu d une coordonnee negative.
            cadre.geometry("%dx%d+%d+%d" % (largeur, hauteur, gauche, haut))
            try:
                # La couleur de fond devient transparente ET laisse passer les
                # clics : le cadre ne gene donc pas ce qui se trouve dessous.
                cadre.attributes("-transparentcolor", COULEUR_TRANSPARENTE)
            except Exception:
                pass

            toile = tk.Canvas(cadre, bg=COULEUR_TRANSPARENTE,
                              highlightthickness=0)
            toile.pack(fill="both", expand=True)
            # Force la creation et le placement de la fenetre tant que le
            # contexte DPI est actif ; elle le conservera ensuite.
            cadre.update_idletasks()
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
            # On redessine d apres la taille reelle de la toile : le cadre
            # epouse l ecran meme si Windows a ajuste la fenetre.
            large = toile.winfo_width() or largeur
            haute = toile.winfo_height() or hauteur
            toile.delete("all")
            demi = epaisseur / 2
            toile.create_rectangle(demi, demi, large - demi, haute - demi,
                                   outline=couleur, width=epaisseur)
        except Exception:
            return
        debut[0] += INTERVALLE_MS
        root.after(INTERVALLE_MS, image)

    image()
    return True
