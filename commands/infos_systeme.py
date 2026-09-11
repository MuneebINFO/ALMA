"""
Informations sur la machine : batterie, disque, reseau, corbeille.
"""

from __future__ import annotations

from core import win_utils
from core.context import CommandContext, Response
from core.registry import command


@command(
    name="batterie",
    informatif=True,
    patterns=[r"(?:niveau|etat|combien)\s+(?:de\s+|d\s+)?batterie",
              r"^batterie$", r"(?:il\s+me\s+reste|reste)\s+combien\s+de\s+batterie",
              r"(?:je\s+suis|suis\s+je)\s+charge",
              r"(?:battery\s+level|how\s+much\s+battery)", r"^battery$"],
    keywords=[["batterie"], ["battery"]],
    category="Informations",
    description="Connaître le niveau de batterie",
    examples=["niveau de batterie", "battery level"],
    priority=92,
)
def batterie(ctx: CommandContext) -> Response:
    """Niveau et état de charge, via psutil."""
    try:
        import psutil

        etat = psutil.sensors_battery()
    except Exception:
        etat = None
    if etat is None:
        return Response.error("Je ne vois pas de batterie sur cette machine.")

    niveau = int(round(etat.percent))
    if etat.power_plugged:
        return Response(text="Batterie à " + str(niveau) + " pour cent, en charge.")
    reste = ""
    if etat.secsleft and etat.secsleft > 0:
        heures, minutes = divmod(int(etat.secsleft) // 60, 60)
        reste = ", environ " + (str(heures) + " heures " if heures else "") \
            + str(minutes) + " minutes d'autonomie"
    return Response(text="Batterie à " + str(niveau) + " pour cent" + reste + ".")


@command(
    name="espace_disque",
    informatif=True,
    patterns=[r"(?:espace|place)\s+(?:libre\s+)?(?:sur\s+le\s+)?disque",
              r"(?:combien|reste)\s+(?:de\s+)?(?:place|espace)",
              r"^disque\s+dur$",
              r"(?:free\s+)?disk\s+space", r"how\s+much\s+(?:disk\s+)?space",
              r"^hard\s+drive$"],
    keywords=[["espace", "disque"], ["place", "disque"], ["disk", "space"]],
    category="Informations",
    description="Connaître l'espace disque disponible",
    examples=["espace libre sur le disque", "free disk space"],
    priority=92,
)
def espace_disque(ctx: CommandContext) -> Response:
    """Espace restant sur le disque système."""
    try:
        import shutil

        total, _utilise, libre = shutil.disk_usage("C:/")
    except Exception as exc:
        return Response.error("Je n'ai pas pu lire le disque : " + str(exc))
    libre_go = libre / (1024 ** 3)
    total_go = total / (1024 ** 3)
    pourcent = int(round(libre / total * 100))
    return Response(
        text="Il reste " + ("%.0f" % libre_go) + " gigaoctets libres sur "
        + ("%.0f" % total_go) + ", soit " + str(pourcent) + " pour cent."
    )


@command(
    name="adresse_ip",
    informatif=True,
    patterns=[r"(?:quelle?\s+est\s+)?(?:mon|l)\s+adresse\s+ip",
              r"^(?:adresse\s+)?ip$", r"(?:quelle?\s+est\s+)?mon\s+ip",
              r"(?:what\s+is|what\s+s)?\s*my\s+ip(?:\s+address)?", r"^ip\s+address$"],
    keywords=[["adresse", "ip"], ["ip", "address"]],
    category="Informations",
    description="Donner l'adresse IP locale",
    examples=["mon adresse IP", "what's my ip address"],
    priority=93,
)
def adresse_ip(ctx: CommandContext) -> Response:
    """Adresse locale de la machine sur le réseau."""
    import socket

    try:
        prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        prise.settimeout(1.0)
        # Aucune donnee n est envoyee : c est le moyen usuel de connaitre
        # l interface que le systeme utiliserait pour sortir.
        prise.connect(("8.8.8.8", 80))
        adresse = prise.getsockname()[0]
        prise.close()
    except Exception:
        try:
            adresse = socket.gethostbyname(socket.gethostname())
        except Exception:
            return Response.error("Je n'ai pas pu déterminer l'adresse IP.")
    return Response(text="Votre adresse IP locale est " + adresse + ".")


@command(
    name="vider_corbeille",
    patterns=[r"(?:vide|vider|nettoie)\s+(?:la\s+)?corbeille",
              r"empty\s+(?:the\s+)?(?:recycle\s+bin|trash)"],
    keywords=[["vide", "corbeille"], ["empty", "trash"]],
    category="Système",
    description="Vider la corbeille (confirmation demandée)",
    examples=["vide la corbeille", "empty the recycle bin"],
    priority=94,
)
def vider_corbeille(ctx: CommandContext) -> Response:
    """Suppression definitive : confirmation obligatoire."""
    if not ctx.confirm("Vider définitivement la corbeille ?"):
        return Response(text="Corbeille conservée.")
    ok, sortie = win_utils.run_command([
        "powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction Stop"
    ])
    if ok:
        return Response(text="Corbeille vidée.")
    if "vide" in sortie.lower() or "empty" in sortie.lower():
        return Response(text="La corbeille était déjà vide.")
    return Response.error("Je n'ai pas pu vider la corbeille : " + sortie[:80])
