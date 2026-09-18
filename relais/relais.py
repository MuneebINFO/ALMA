"""
Le relais d abonnement d ALMA.

CE QU IL EST. Un petit serveur, deploye chez vous, qui se tient entre
l application et l API d Anthropic. Il existe pour une seule raison : la cle
d API ne peut pas voyager dans l application. Un .msix est une archive, on en
sort l executable, on y cherche des chaines -- et meme obfusquee, la cle doit
etre en clair en memoire au moment de l appel. Une cle livree est une cle
publiee, et c est votre compte qui paie.

    ALMA  --(jeton signe par Microsoft)-->  CE RELAIS  --(votre cle)-->  Anthropic

CE QU IL N EST PAS. Il ne conserve ni les questions, ni les images, ni les
reponses. Ce qu il garde, c est un COMPTEUR par abonne -- le strict necessaire
pour faire respecter un quota. PRIVACY.md en fait la promesse aux
utilisateurs ; ce fichier est l endroit ou cette promesse se tient ou se
trahit, et il n y a pas d entre-deux.

TROIS CHOSES A PROVISIONNER AVANT DE DEPLOYER (voir README.md) :

  ANTHROPIC_API_KEY   votre cle. Jamais dans le depot, jamais dans l image.
  AZURE_CLIENT_ID     l application Azure AD associee a votre compte
  AZURE_CLIENT_SECRET Partner Center, qui autorise le relais a demander a
                      Microsoft si un abonnement est actif.

Sans les deux dernieres, le relais demarre en MODE DEVELOPPEMENT : il accepte
un jeton d essai et refuse tout le reste. Cela permet de tout eprouver avant
d avoir provisionne Azure -- et le mode se voit dans les journaux a chaque
demarrage, pour qu il ne parte jamais en production par inadvertance.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager, closing

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("alma.relais")

# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------
CLE_ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
AZURE_TENANT = os.environ.get("AZURE_TENANT_ID", "common")

# Le jeton accepte en mode developpement. Ne vaut QUE si Azure n est pas
# configure : en production il n ouvre rien.
JETON_ESSAI = os.environ.get("ALMA_JETON_ESSAI", "essai-local")

# Le quota mensuel, annonce dans la fiche du Store. Il n est pas la pour
# brider : il est la pour qu un seul utilisateur qui enchaine les analyses
# d image n efface pas la marge de dix autres.
QUOTA_MENSUEL = int(os.environ.get("ALMA_QUOTA_MENSUEL", "300"))

# Interroger Microsoft a chaque requete ajouterait un aller-retour a chaque
# phrase prononcee. On garde donc la reponse quelques heures -- assez pour
# que la latence ne se paie qu une fois, assez peu pour qu une resiliation
# soit prise en compte dans la journee.
DUREE_CACHE_ABONNEMENT = int(os.environ.get("ALMA_CACHE_SECONDES", "43200"))

BASE = os.environ.get("ALMA_BASE", "relais.db")
AMONT = "https://api.anthropic.com"
DELAI_AMONT = 60.0

# Ce que le relais laisse passer vers Anthropic. Volontairement court : tout
# en-tete non liste est jete. Un relais qui transmet aveuglement devient le
# proxy ouvert de quelqu un d autre.
ENTETES_TRANSMISES = ("content-type", "anthropic-version", "anthropic-beta")


def mode_developpement() -> bool:
    """Azure n est pas configure : le relais n ouvre que sur le jeton d essai."""
    return not (AZURE_CLIENT_ID and AZURE_CLIENT_SECRET)


# --------------------------------------------------------------------------
# Le compteur
# --------------------------------------------------------------------------
# Une seule table, trois colonnes, et RIEN du contenu des requetes. La forme
# du schema est elle-meme la garantie : il n y a pas de colonne ou ranger une
# question, donc il n y a pas de question rangee.
SCHEMA = """
CREATE TABLE IF NOT EXISTS consommation (
    abonne   TEXT NOT NULL,
    periode  TEXT NOT NULL,          -- « 2026-09 »
    compte   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (abonne, periode)
);
CREATE TABLE IF NOT EXISTS abonnements (
    abonne   TEXT PRIMARY KEY,
    valide   INTEGER NOT NULL,
    verifie  INTEGER NOT NULL         -- horodatage de la derniere verification
);
"""


def connexion():
    lien = sqlite3.connect(BASE)
    lien.executescript(SCHEMA)
    return lien


def periode_courante() -> str:
    return time.strftime("%Y-%m")


def consommation(abonne: str) -> int:
    with closing(connexion()) as lien:
        ligne = lien.execute(
            "SELECT compte FROM consommation WHERE abonne=? AND periode=?",
            (abonne, periode_courante())).fetchone()
    return ligne[0] if ligne else 0


def compter_une_requete(abonne: str) -> int:
    """Incremente et rend le nouveau total."""
    with closing(connexion()) as lien:
        lien.execute(
            "INSERT INTO consommation (abonne, periode, compte) VALUES (?, ?, 1) "
            "ON CONFLICT(abonne, periode) DO UPDATE SET compte = compte + 1",
            (abonne, periode_courante()))
        lien.commit()
        ligne = lien.execute(
            "SELECT compte FROM consommation WHERE abonne=? AND periode=?",
            (abonne, periode_courante())).fetchone()
    return ligne[0] if ligne else 0


# --------------------------------------------------------------------------
# Verifier qu un abonnement est actif
# --------------------------------------------------------------------------
def _cache_lire(abonne: str):
    with closing(connexion()) as lien:
        ligne = lien.execute(
            "SELECT valide, verifie FROM abonnements WHERE abonne=?",
            (abonne,)).fetchone()
    if not ligne:
        return None
    valide, verifie = ligne
    if time.time() - verifie > DUREE_CACHE_ABONNEMENT:
        return None
    return bool(valide)


def _cache_ecrire(abonne: str, valide: bool) -> None:
    with closing(connexion()) as lien:
        lien.execute(
            "INSERT INTO abonnements (abonne, valide, verifie) VALUES (?, ?, ?) "
            "ON CONFLICT(abonne) DO UPDATE SET valide=excluded.valide, "
            "verifie=excluded.verifie",
            (abonne, int(valide), int(time.time())))
        lien.commit()


async def _demander_a_microsoft(jeton: str) -> bool:
    """
    Microsoft confirme-t-il que ce jeton correspond a un abonnement actif ?

    ATTENTION, A CONFIRMER AVANT MISE EN PRODUCTION. Les adresses ci-dessous
    sont celles du service de collections du Store, et Microsoft les fait
    evoluer. Elles sont isolees ici exprès : c est le seul endroit a corriger
    si elles changent, et le seul a verifier contre la documentation a jour.

    Le principe, lui, ne change pas : le relais s authentifie aupres d Azure
    AD avec l application liee au compte Partner Center, echange ce jeton
    contre un jeton du Store, puis demande la collection de l utilisateur.
    """
    jeton_azure = await _jeton_azure()
    if not jeton_azure:
        return False
    async with httpx.AsyncClient(timeout=20.0) as client:
        reponse = await client.post(
            "https://collections.mp.microsoft.com/v6.0/collections/query",
            headers={"Authorization": "Bearer " + jeton_azure,
                     "Content-Type": "application/json"},
            json={"beneficiaries": [{"identitytype": "b2b",
                                     "identityValue": jeton,
                                     "localTicketReference": ""}]},
        )
    if reponse.status_code != 200:
        log.warning("Microsoft a refuse la verification : %s", reponse.status_code)
        return False
    for article in reponse.json().get("items", []):
        if article.get("productId") and article.get("status") == "Active":
            return True
    return False


async def _jeton_azure() -> str:
    """Un jeton d acces Azure AD pour le service de collections."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            reponse = await client.post(
                "https://login.microsoftonline.com/" + AZURE_TENANT + "/oauth2/v2.0/token",
                data={"grant_type": "client_credentials",
                      "client_id": AZURE_CLIENT_ID,
                      "client_secret": AZURE_CLIENT_SECRET,
                      "scope": "https://onestore.microsoft.com/.default"},
            )
        if reponse.status_code != 200:
            log.warning("Azure a refuse le jeton : %s", reponse.status_code)
            return ""
        return reponse.json().get("access_token", "")
    except httpx.HTTPError as exc:
        log.warning("Azure injoignable : %s", exc)
        return ""


async def abonnement_actif(jeton: str) -> bool:
    """
    Ce jeton donne-t-il droit a l edition complete ?

    En mode developpement, seul le jeton d essai passe -- pas « tout le
    monde ». Un relais qui s ouvre a tous quand sa configuration est
    incomplete est exactement la panne qui coute de l argent en silence.
    """
    if not jeton:
        return False
    if mode_developpement():
        return jeton == JETON_ESSAI

    connu = _cache_lire(jeton)
    if connu is not None:
        return connu
    valide = await _demander_a_microsoft(jeton)
    _cache_ecrire(jeton, valide)
    return valide


# --------------------------------------------------------------------------
# Le service
# --------------------------------------------------------------------------
@asynccontextmanager
async def au_demarrage(_app: FastAPI):
    """
    Ce que le relais annonce en demarrant.

    Le mode est journalise a CHAQUE demarrage, exprès : un relais parti en
    production en mode developpement n ouvrirait qu au jeton d essai, et la
    panne ressemblerait a une erreur d abonnement chez tous les clients.
    """
    logging.basicConfig(level=logging.INFO)
    if not CLE_ANTHROPIC:
        log.error("ANTHROPIC_API_KEY absente : aucune requete ne pourra aboutir.")
    if mode_developpement():
        log.warning("MODE DEVELOPPEMENT : Azure n'est pas configure, seul le "
                    "jeton d'essai est accepte. Ne pas laisser ainsi en production.")
    else:
        log.info("Verification des abonnements par Microsoft : active.")
    log.info("Quota mensuel : %d requetes.", QUOTA_MENSUEL)
    yield


app = FastAPI(title="Relais ALMA", docs_url=None, redoc_url=None,
              lifespan=au_demarrage)


@app.get("/sante")
async def sante() -> dict:
    """De quoi laisser un hebergeur verifier que le service repond."""
    return {"etat": "ok",
            "mode": "developpement" if mode_developpement() else "production",
            "quota_mensuel": QUOTA_MENSUEL}


@app.post("/v1/messages")
async def messages(requete: Request,
                   x_api_key: str = Header(default="")) -> JSONResponse:
    """
    Le seul point d entree, et il a la MEME FORME que celui d Anthropic.

    C est ce qui rend le changement minuscule cote application : le SDK
    accepte une `base_url`, donc ALMA change d adresse et envoie son jeton
    d abonne la ou elle mettait une cle. Rien d autre ne bouge.
    """
    if not await abonnement_actif(x_api_key):
        # 401 et non 403 : le SDK sait deja traiter ce code, et l application
        # peut alors dire « votre abonnement n est plus actif » plutot que
        # d afficher une panne.
        raise HTTPException(status_code=401,
                            detail="Abonnement introuvable ou expiré.")

    utilise = consommation(x_api_key)
    if utilise >= QUOTA_MENSUEL:
        raise HTTPException(
            status_code=429,
            detail="Quota mensuel atteint (" + str(QUOTA_MENSUEL) + " requêtes).")

    corps = await requete.body()
    entetes = {"x-api-key": CLE_ANTHROPIC,
               "anthropic-version": "2023-06-01"}
    for nom in ENTETES_TRANSMISES:
        valeur = requete.headers.get(nom)
        if valeur:
            entetes[nom] = valeur

    try:
        async with httpx.AsyncClient(timeout=DELAI_AMONT) as client:
            reponse = await client.post(AMONT + "/v1/messages",
                                        content=corps, headers=entetes)
    except httpx.HTTPError as exc:
        log.warning("Amont injoignable : %s", exc)
        raise HTTPException(status_code=502, detail="Service momentanément indisponible.")

    # On ne compte QUE ce qui a abouti : facturer un quota pour une panne de
    # notre cote serait faire payer l utilisateur pour notre incident.
    if reponse.status_code == 200:
        compter_une_requete(x_api_key)

    # Le corps est retransmis TEL QUEL et n est jamais journalise : c est la
    # promesse de PRIVACY.md, et elle se tient ici ou nulle part.
    return JSONResponse(status_code=reponse.status_code,
                        content=reponse.json())
