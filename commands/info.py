"""
Informations pratiques : heure, date, météo.

La météo utilise Open-Météo, une API gratuite et SANS CLE. Si la machine est
hors ligne, on le dit clairement au lieu de planter.
"""

from __future__ import annotations

from datetime import datetime

from core.context import CommandContext, Response
from core.registry import command

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

# Codes météo WMO renvoyes par Open-Météo.
WMO_CODES = {
    0: "ciel dégagé", 1: "plutot dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine legere", 53: "bruine", 55: "bruine forte",
    56: "bruine verglacante", 57: "bruine verglacante forte",
    61: "pluie faible", 63: "pluie", 65: "forte pluie",
    66: "pluie verglacante", 67: "pluie verglacante forte",
    71: "neige faible", 73: "neige", 75: "forte neige", 77: "grains de neige",
    80: "averses faibles", 81: "averses", 82: "fortes averses",
    85: "averses de neige", 86: "fortes averses de neige",
    95: "orage", 96: "orage avec grele", 99: "violent orage avec grele",
}

WMO_CODES_EN = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
    99: "violent thunderstorm with hail",
}


@command(
    name="get_time",
    informatif=True,
    patterns=[
        r"(?:quelle?\s+heure\s+(?:est\s+il|il\s+est)|il\s+est\s+quelle\s+heure)",
        r"^(?:heure|l\s+heure)$",
        r"(?:donne|dis)\s*(?:moi)?\s+l\s+heure",
        r"what\s+time\s+is\s+it",
    ],
    keywords=[["quelle", "heure"]],
    category="Informations",
    description="Donner l'heure actuelle",
    examples=["quelle heure est-il"],
    priority=92,
)
def get_time(ctx: CommandContext) -> Response:
    """Annonce l'heure courante."""
    now = datetime.now()
    return ctx.reponse(
        "Il est " + now.strftime("%H") + " heures " + now.strftime("%M") + ".",
        # 12 h avec am/pm : c est ainsi qu on lit l heure en anglais.
        "It's " + now.strftime("%I:%M %p").lstrip("0") + ".",
    )


@command(
    name="get_date",
    informatif=True,
    patterns=[
        r"(?:quel\s+jour\s+(?:sommes\s+nous|est\s+on|on\s+est)|quelle?\s+est\s+la\s+date)",
        r"^(?:date|la\s+date|quel\s+jour)$",
        r"(?:on\s+est\s+quel\s+jour)",
        # « what day is it », mais aussi « what's the date » : la
        # normalisation coupe l apostrophe, d ou le « s » isole.
        r"what\s+(?:day|date)\s+is",
        r"what\s+(?:is\s+|s\s+)?(?:the\s+)?(?:day|date)",
        r"^(?:today\s+s\s+date|the\s+date)$",
    ],
    keywords=[["quel", "jour"], ["la", "date"], ["what", "date"], ["what", "day"]],
    category="Informations",
    description="Donner la date du jour",
    examples=["quelle est la date", "quel jour sommes-nous"],
    priority=92,
)
def get_date(ctx: CommandContext) -> Response:
    """Annonce la date courante en toutes lettres."""
    now = datetime.now()
    return ctx.reponse(
        "Nous sommes le " + JOURS[now.weekday()] + " " + str(now.day) + " "
        + MOIS[now.month - 1] + " " + str(now.year) + ".",
        "It's " + JOURS_EN[now.weekday()] + " " + MOIS_EN[now.month - 1] + " "
        + str(now.day) + ", " + str(now.year) + ".",
    )


def _geocode(city: str, timeout: int = 8, langue: str = "fr"):
    """
    Trouve les coordonnees d'une ville (API gratuite, sans cle).

    `langue` sert au nom rendu : « Bruxelles » en francais, « Brussels » en
    anglais. On repond dans la langue ou l on a ete interroge, noms de
    villes compris.
    """
    import requests

    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": langue, "format": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    results = (response.json() or {}).get("results") or []
    return results[0] if results else None


def _forecast(latitude: float, longitude: float, timeout: int = 8):
    """Releve météo courant + min/max du jour (API gratuite, sans cle)."""
    import requests

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json() or {}


@command(
    name="weather",
    informatif=True,
    # Motifs ancres en debut de phrase : sinon "google météo Bruxelles"
    # serait capture ici au lieu de partir vers la recherche Google.
    patterns=[
        r"^(?:quel\s+temps\s+(?:fait\s+il|il\s+fait)|la\s+meteo|meteo)\s*(?:a|sur|pour|de|dans)?\s*(.*)$",
        r"^(?:il\s+fait\s+quel\s+temps)\s*(?:a)?\s*(.*)$",
        r"^(?:quelle?\s+(?:est\s+la\s+)?temperature)\s*(?:a)?\s*(.*)$",
        r"^weather\s*(?:in|at|for)?\s*(.*)$",
        r"^what\s+(?:is\s+|s\s+)?(?:the\s+)?weather\s*(?:like)?\s*(?:in|at|for)?\s*(.*)$",
        r"^how\s+(?:is\s+|s\s+)?(?:the\s+)?weather\s*(?:in|at|for)?\s*(.*)$",
        r"^what\s+(?:is\s+|s\s+)?(?:the\s+)?temperature\s*(?:in|at|for)?\s*(.*)$",
    ],
    keywords=[["meteo"], ["temps", "fait"], ["weather"]],
    category="Informations",
    description="Donner la météo d'une ville",
    examples=["quel temps fait-il a Bruxelles", "météo Paris",
              "what's the weather in London"],
    priority=90,
)
def weather(ctx: CommandContext) -> Response:
    """
    Météo via Open-Météo (gratuit, sans clé API).
    Degradation propre si requests est absent ou si la machine est hors ligne.
    """
    city = ctx.arg.strip() or str(ctx.config.get("weather.default_city", "Bruxelles"))
    anglais = ctx.lang == "en"
    try:
        import requests  # noqa: F401
    except ImportError:
        return ctx.erreur(
            "Le module requests n'est pas installe (pip install -r requirements.txt).",
            "The requests module isn't installed (pip install -r requirements.txt).",
        )
    try:
        place = _geocode(city, langue=ctx.lang)
        if place is None:
            return ctx.erreur("Je n'ai pas trouvé la ville « " + city + " ».",
                              "I couldn't find the city \"" + city + "\".")
        data = _forecast(place["latitude"], place["longitude"])
    except Exception:
        return ctx.erreur(
            "Je n'arrive pas à joindre le service météo. Vérifiez votre connexion internet.",
            "I can't reach the weather service. Check your internet connection.",
        )

    current = data.get("current") or {}
    daily = data.get("daily") or {}
    temperature = current.get("temperature_2m")
    felt = current.get("apparent_temperature")
    code = int(current.get("weather_code", -1))
    wind = current.get("wind_speed_10m")
    description = ((WMO_CODES_EN.get(code, "unknown conditions")) if anglais
                   else WMO_CODES.get(code, "conditions inconnues"))

    name = place.get("name", city)
    country = place.get("country", "")
    lieu = name + (" (" + country + ")" if country else "")
    parts = [(("In " + lieu + ": ") if anglais else ("À " + lieu + " : ")) + description]
    if temperature is not None:
        degres = str(round(float(temperature)))
        parts.append(degres + (" degrees" if anglais else " degrés"))
    if felt is not None and temperature is not None and abs(float(felt) - float(temperature)) >= 2:
        ressenti = str(round(float(felt)))
        parts.append(("feels like " + ressenti + " degrees") if anglais
                     else ("ressenti " + ressenti + " degrés"))
    try:
        mini = daily.get("temperature_2m_min", [None])[0]
        maxi = daily.get("temperature_2m_max", [None])[0]
        if mini is not None and maxi is not None:
            bas, haut = str(round(float(mini))), str(round(float(maxi)))
            parts.append((bas + " to " + haut + " degrees today") if anglais
                         else ("de " + bas + " à " + haut + " degrés aujourd'hui"))
    except (IndexError, TypeError, ValueError):
        pass
    if wind is not None:
        vent = str(round(float(wind)))
        parts.append(("wind " + vent + " kilometres per hour") if anglais
                     else ("vent " + vent + " kilomètres heure"))
    return Response(text=", ".join(parts) + ".")
