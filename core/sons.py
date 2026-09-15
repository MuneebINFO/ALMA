"""
Les bruitages : quatre signes, et pas un de plus.

Un assistant qui tinte a chaque geste devient fatigant en une demi-journee.
Ceux-la ne marquent que ce qui ne se dit pas autrement :

  reveil   je vous ecoute        -- deux notes qui montent
  veille   je me retire          -- deux notes qui descendent
  ok       c est fait            -- une note breve, la ou RIEN n est dit
  erreur   ca n a pas marche     -- deux notes basses

Le troisieme est le plus utile : une action reussie ne se commente pas a
voix haute (voir `informatif` dans core/registry.py), et le silence qui
suit ne se distingue pas d une commande perdue.

La lecture passe par `winsound`, de la bibliotheque standard Windows, en
mode ASYNCHRONE : un bruitage ne doit jamais retarder ce qu il accompagne.
Les fichiers sont fabriques par outils/generer_sons.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

NOMS = ("reveil", "veille", "ok", "erreur")


def dossier() -> Path:
    """Ou vivent les .wav. Suit l application, empaquetee ou non."""
    from config import ROOT

    livre = Path(__file__).resolve().parent.parent / "assets" / "sons"
    # En developpement les deux chemins coincident ; une fois empaquete,
    # ROOT est le dossier de donnees et les assets restent pres du code.
    return livre if livre.is_dir() else ROOT / "assets" / "sons"


class Bruitages:
    """
    Joue les bruitages, ou ne joue rien.

    Volontairement tolerant : pas de fichier, pas de winsound, pas de carte
    son -- rien ne doit jamais remonter. Un bruitage manquant n est pas une
    panne, c est un silence.
    """

    def __init__(self, config=None) -> None:
        self.config = config
        self._dossier = dossier()

    @property
    def actifs(self) -> bool:
        if self.config is None:
            return True
        return bool(self.config.get("sound.enabled", True))

    def chemin(self, nom: str) -> Path | None:
        fichier = self._dossier / (nom + ".wav")
        return fichier if fichier.is_file() else None

    def jouer(self, nom: str) -> bool:
        """
        Joue un bruitage. Retourne True s il est parti.

        Rendre la main tout de suite est essentiel : ce son accompagne une
        action, il ne la precede pas.
        """
        if not self.actifs:
            return False
        fichier = self.chemin(nom)
        if fichier is None:
            return False
        try:
            import winsound

            winsound.PlaySound(
                str(fichier),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            return True
        except Exception as exc:
            log.debug("Bruitage %s non joué : %s", nom, exc)
            return False
