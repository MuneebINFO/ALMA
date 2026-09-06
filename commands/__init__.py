"""
Modules de commandes de Alma.

MODULES liste explicitement les modules a charger. Pourquoi une liste plutot
qu une decouverte automatique seule : une fois le projet empaquete en .exe
(PyInstaller), il n y a plus de vrai dossier sur le disque et la decouverte
dynamique ne trouve rien. La liste garantit que l executable embarque bien
toutes les commandes.

La decouverte automatique reste utilisee en repli, et un test verifie que
cette liste correspond exactement aux modules presents : si vous ajoutez un
module sans l inscrire ici, le test echoue avec un message explicite.
"""

MODULES = (
    "apps",
    "calcul",
    "clavier",
    "fenetres",
    "info",
    "infos_systeme",
    "interaction",
    "media",
    "misc",
    "productivity",
    "search",
    "smalltalk",
    "system",
    "websites",
)
