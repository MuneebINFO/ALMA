"""
La camera : l allumer, prendre une image, l eteindre.

Pas de dependance nouvelle. `winsdk` est deja la pour les sessions media
(voir core/media_control.py), et il expose aussi la capture video de
Windows. Ajouter OpenCV aurait coute trente-cinq megaoctets a l executable
-- et donc au paquet du Store -- pour le meme resultat.

DEUX PRECAUTIONS valent d etre dites.

La capture est reglee en VIDEO SEULE. Le mode par defaut de Windows prend
aussi le microphone, or c est exactement celui dont l ecoute se sert : le
lui retirer le temps d une photo rendrait Alma sourde au moment ou on lui
parle.

Et la camera est RENDUE apres chaque prise. Un temoin qui reste allume
parce qu un assistant a oublie de fermer, c est le genre de chose qui fait
desinstaller une application -- a juste titre.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

# Les camera virtuelles -- OBS, Lenovo, Teams -- s annoncent comme des
# cameras mais ne montrent souvent rien. A choisir, on prend la vraie.
MOTS_VIRTUELS = ("virtual", "virtuelle", "obs", "snap", "droidcam", "epoccam")


def _est_virtuelle(nom: str) -> bool:
    minuscule = (nom or "").lower()
    return any(mot in minuscule for mot in MOTS_VIRTUELS)


async def _lister_async() -> list:
    from winsdk.windows.devices.enumeration import DeviceClass, DeviceInformation

    trouves = await DeviceInformation.find_all_async(DeviceClass.VIDEO_CAPTURE)
    return [(trouves.get_at(i).id, trouves.get_at(i).name)
            for i in range(trouves.size)]


def lister() -> list:
    """Les cameras branchees : [(identifiant, nom)]. Vide s il n y en a pas."""
    try:
        return _executer(_lister_async())
    except Exception as exc:
        log.debug("Enumération des caméras impossible : %s", exc)
        return []


def choisir(appareils=None) -> tuple:
    """
    La camera a utiliser : (identifiant, nom), ou (\"\", \"\") s il n y en a pas.

    Une vraie camera l emporte toujours sur une virtuelle, meme si celle-ci
    est listee en premier -- ce qui arrive souvent, les pilotes virtuels
    s installant devant.
    """
    appareils = lister() if appareils is None else appareils
    if not appareils:
        return "", ""
    reelles = [a for a in appareils if not _est_virtuelle(a[1])]
    return (reelles or appareils)[0]


async def _capturer_async(identifiant: str) -> bytes:
    from winsdk.windows.media.capture import (MediaCapture,
                                              MediaCaptureInitializationSettings,
                                              MediaStreamType, StreamingCaptureMode)
    from winsdk.windows.media.mediaproperties import ImageEncodingProperties
    from winsdk.windows.storage.streams import DataReader, InMemoryRandomAccessStream

    reglages = MediaCaptureInitializationSettings()
    # VIDEO seule : le mode par defaut prendrait aussi le micro, dont
    # l ecoute a besoin au meme moment.
    reglages.streaming_capture_mode = StreamingCaptureMode.VIDEO
    if identifiant:
        reglages.video_device_id = identifiant

    capture = MediaCapture()
    await capture.initialize_async(reglages)
    try:
        flux = InMemoryRandomAccessStream()
        await capture.capture_photo_to_stream_async(
            ImageEncodingProperties.create_jpeg(), flux)
        flux.seek(0)
        lecteur = DataReader(flux.get_input_stream_at(0))
        await lecteur.load_async(flux.size)
        # `read_bytes` REMPLIT un tampon, il n en rend pas un : lui passer
        # une taille leve « a bytes-like object is required, not int ».
        tampon = bytearray(flux.size)
        lecteur.read_bytes(tampon)
        return bytes(tampon)
    finally:
        # Rendre la camera, quoi qu il arrive : un temoin laisse allume est
        # une faute, pas un detail.
        try:
            capture.close()
        except Exception as exc:
            log.debug("Caméra non refermée : %s", exc)


def _executer(coroutine):
    """
    Joue une coroutine winsdk, meme depuis un thread sans boucle.

    Alma appelle ceci depuis le thread des commandes, qui n a pas de boucle
    asyncio. `asyncio.run` en cree une et la referme proprement.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    # Une boucle tourne deja : on en ouvre une dans un thread a part plutot
    # que de s y greffer, ce qui bloquerait l appelant.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


def capturer(identifiant: str = "") -> bytes:
    """
    Une image JPEG de la camera, ou des octets vides.

    Volontairement tolerant : pas de camera, pilote absent, acces refuse
    dans les reglages de confidentialite de Windows -- rien ne doit remonter
    sous forme d exception. C est l appelant qui decide quoi dire.
    """
    if not identifiant:
        identifiant, _nom = choisir()
    try:
        return _executer(_capturer_async(identifiant))
    except Exception as exc:
        log.warning("Capture caméra impossible : %s", exc)
        return b""


def disponible() -> bool:
    """Y a-t-il une camera utilisable ?"""
    return bool(choisir()[0])


def enregistrer(image: bytes, dossier) -> tuple:
    """
    Ecrit l image dans le dossier, sous un nom horodate. Rend (ok, chemin).

    Separe de `capturer` pour la meme raison que `win_utils.take_screenshot`
    l est du reste : c est le seul endroit du projet qui POSE un fichier chez
    l utilisateur, donc le seul a neutraliser pour qu une suite de tests ne
    remplisse pas ses Images.
    """
    import os
    from datetime import datetime
    from pathlib import Path

    cible = Path(os.path.expandvars(os.path.expanduser(str(dossier))))
    nom = "photo_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
    try:
        cible.mkdir(parents=True, exist_ok=True)
        (cible / nom).write_bytes(image)
    except OSError as exc:
        return False, str(exc)
    return True, str(cible / nom)
