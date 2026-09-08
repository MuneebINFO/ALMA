"""
Registre des commandes.

Chaque module de `commands/` declare ses handlers avec le decorateur @command.
Le routeur consomme ensuite ce registre : pas de gros if/elif monolithique,
ajouter une commande = ajouter une fonction decoree.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from dataclasses import dataclass
from typing import Callable, Sequence

from core.context import SOURCE_GESTURE, SOURCE_TEXT, SOURCE_VOICE, CommandContext, Response

Handler = Callable[[CommandContext], Response]
Guard = Callable[[CommandContext], bool]

ALL_SOURCES = (SOURCE_TEXT, SOURCE_VOICE, SOURCE_GESTURE)


@dataclass
class Command:
    """Une commande enregistrée et ses declencheurs."""

    name: str
    handler: Handler
    patterns: tuple = ()
    keywords: tuple = ()
    category: str = "Divers"
    description: str = ""
    examples: tuple = ()
    priority: int = 50
    guard: Guard | None = None
    sources: tuple = ALL_SOURCES
    hidden: bool = False
    # True quand la commande ne se declenche que si un contexte existe
    # (« recherche Damso » n a de sens qu apres « va sur YouTube »).
    contextuel: bool = False
    # True quand la commande REPOND quelque chose : une heure, une meteo, une
    # blague, la liste des notes. Ce sont les seules a etre lues a voix haute
    # quand tout se passe bien. Une action reussie se voit -- la commenter
    # ferait perdre du temps a l utilisateur et couvrirait ce qu il regarde.
    informatif: bool = False

    def accepts_source(self, source: str) -> bool:
        return source in self.sources


_REGISTRY: list = []
_LOADED = False


def command(
    name: str,
    patterns: Sequence = (),
    keywords: Sequence = (),
    category: str = "Divers",
    description: str = "",
    examples: Sequence = (),
    priority: int = 50,
    guard: Guard | None = None,
    sources: Sequence = ALL_SOURCES,
    hidden: bool = False,
    contextuel: bool = False,
    informatif: bool = False,
):
    """
    Decorateur d enregistrement d'une commande.

    - patterns : expressions regulieres testees sur la phrase NORMALISEE
      (minuscules, sans accents ni ponctuation).
    - keywords : groupes de mots ; un groupe matche si TOUS ses mots sont
      presents (avec tolerance aux fautes). Filet de securite si aucun regex
      ne colle.
    - priority : les commandes les plus specifiques doivent avoir la priorite
      la plus haute (elles sont testees en premier).
    - guard : predicat optionnel ; s il renvoie False, le routeur continue de
      chercher (permet a "ouvre X" d essayer les apps puis les sites web).
    - sources : d ou la commande peut être declenchee (texte, voix, gestes).
    - informatif : la commande repond quelque chose (heure, meteo, blague).
      Les autres executent une action, dont le resultat se voit : elles ne
      sont pas lues a voix haute quand elles reussissent.
    """

    def decorator(func: Handler) -> Handler:
        doc = (func.__doc__ or "").strip()
        first_line = doc.splitlines()[0] if doc else ""
        cmd = Command(
            name=name,
            handler=func,
            patterns=tuple(re.compile(p, re.IGNORECASE) for p in patterns),
            keywords=tuple(tuple(group) for group in keywords),
            category=category,
            description=description or first_line,
            examples=tuple(examples),
            priority=priority,
            guard=guard,
            sources=tuple(sources),
            hidden=hidden,
            contextuel=contextuel,
            informatif=informatif,
        )
        _REGISTRY.append(cmd)
        func.command = cmd
        return func

    return decorator


def all_commands() -> list:
    """Toutes les commandes, triees par priorite decroissante."""
    return sorted(_REGISTRY, key=lambda c: (-c.priority, c.name))


def by_category() -> dict:
    """Commandes visibles regroupees par catégorie (pour l'aide)."""
    groups: dict = {}
    for cmd in all_commands():
        if cmd.hidden:
            continue
        groups.setdefault(cmd.category, []).append(cmd)
    return groups


def find(name: str):
    for cmd in _REGISTRY:
        if cmd.name == name:
            return cmd
    return None


def clear() -> None:
    """Vide le registre (utile pour les tests)."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False


def discover_command_modules() -> list:
    """Modules presents dans commands/ (decouverte sur le disque)."""
    import commands as commands_pkg

    return sorted(
        info.name
        for info in pkgutil.iter_modules(commands_pkg.__path__)
        if not info.name.startswith("_")
    )


def load_commands(force: bool = False) -> list:
    """
    Importe tous les modules de commands/ pour declencher les @command.

    On part de la liste explicite commands.MODULES : elle fonctionne aussi
    dans un executable empaquete, ou la decouverte sur disque ne trouve rien.
    La decouverte reste utilisee en complement pendant le developpement.
    """
    global _LOADED
    if _LOADED and not force:
        return all_commands()
    import commands as commands_pkg

    noms = list(getattr(commands_pkg, "MODULES", ()))
    try:
        for trouve in discover_command_modules():
            if trouve not in noms:
                noms.append(trouve)
    except Exception:
        pass  # pas de dossier reel (executable empaquete) : la liste suffit

    for nom in noms:
        importlib.import_module("commands." + nom)
    _LOADED = True
    return all_commands()
