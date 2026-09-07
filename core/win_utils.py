"""
Utilitaires systeme Windows.

Toutes les fonctions sont defensives : si une dependance optionnelle manque
(pycaw, Pillow...), on renvoie un message d erreur lisible plutot que de
faire planter l'assistant. Les imports lourds sont faits a l interieur des
fonctions pour garder le demarrage rapide et les tests portables.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform.startswith("win")

# Codes des touches multimedia virtuelles Windows.
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def expand(path: str) -> str:
    """Developpe les variables d environnement et le ~."""
    return os.path.expandvars(os.path.expanduser(str(path)))


def launch(candidates) -> tuple[bool, str]:
    """
    Essaie de lancer le premier candidat valide.
    Un candidat peut être un chemin complet, un exe du PATH, ou une URI shell.
    Retourne (succes, candidat_utilise_ou_message).
    """
    if isinstance(candidates, str):
        candidates = [candidates]
    errors = []
    for raw in candidates:
        target = expand(raw)
        try:
            # 1) chemin existant sur le disque
            if os.path.exists(target):
                os.startfile(target)  # type: ignore[attr-defined]
                return True, target
            # 2) executable trouve dans le PATH
            found = shutil.which(target)
            if found:
                os.startfile(found)  # type: ignore[attr-defined]
                return True, found
            # 3) URI shell (ms-settings:, spotify:...)
            if ":" in target and not os.path.splitdrive(target)[0]:
                os.startfile(target)  # type: ignore[attr-defined]
                return True, target
            # 4) dernier recours : "start" resout les App Paths du registre
            result = subprocess.run(
                ["cmd", "/c", "start", "", target],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                return True, target
            errors.append(target + " (" + (result.stderr or "introuvable").strip() + ")")
        except AttributeError:
            # os.startfile n existe pas hors Windows
            errors.append(target + " (os.startfile indisponible sur cette plateforme)")
        except Exception as exc:
            errors.append(target + " (" + str(exc) + ")")
    return False, " ; ".join(errors) if errors else "aucun chemin configure"


def kill_process(process_name: str) -> tuple[bool, str]:
    """Ferme une application par son nom de processus (taskkill)."""
    if not process_name:
        return False, "aucun nom de processus configure"
    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0:
            return True, process_name
        return False, (result.stdout or result.stderr or "").strip()
    except Exception as exc:
        return False, str(exc)


def press_key(vk_code: int) -> bool:
    """Simule l appui sur une touche virtuelle (touches multimedia/volume)."""
    try:
        import ctypes

        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # 2 = KEYEVENTF_KEYUP
        return True
    except Exception as exc:
        log.debug("press_key a echoue : %s", exc)
        return False


def lock_workstation() -> bool:
    """Verrouille la session Windows."""
    try:
        import ctypes

        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception as exc:
        log.debug("Verrouillage impossible : %s", exc)
        return False


def run_command(args, timeout: int = 20) -> tuple[bool, str]:
    """Execute une commande systeme et renvoie (succes, sortie)."""
    try:
        # errors="replace" : la sortie des outils Windows n'est pas toujours
        # decodable en cp1252, et cela ne doit jamais faire planter Alma.
        result = subprocess.run(
            args, capture_output=True, text=True, errors="replace", timeout=timeout
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


# --------------------------------------------------------------------------
# Volume (pycaw si disponible, sinon repli sur les touches multimedia)
# --------------------------------------------------------------------------
def _volume_interface():
    """
    Retourne l interface audio pycaw, ou None si indisponible.

    Compatible avec les deux generations d API pycaw :
      - recente : GetSpeakers() renvoie un AudioDevice expose EndpointVolume ;
      - ancienne : il faut activér soi-meme IAudioEndpointVolume sur le device.
    """
    try:
        from pycaw.utils import AudioUtilities

        device = AudioUtilities.GetSpeakers()
    except Exception as exc:
        log.debug("pycaw indisponible : %s", exc)
        return None

    endpoint = getattr(device, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    try:
        from comtypes import CLSCTX_ALL
        from ctypes import POINTER, cast
        from pycaw.pycaw import IAudioEndpointVolume

        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as exc:
        log.debug("Interface volume inaccessible : %s", exc)
        return None


def get_volume() -> int | None:
    """Volume principal en pourcentage, ou None si non mesurable."""
    volume = _volume_interface()
    if volume is None:
        return None
    try:
        return int(round(volume.GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None


def set_volume(percent: int) -> bool:
    """Regle le volume principal (0-100)."""
    percent = max(0, min(100, int(percent)))
    volume = _volume_interface()
    if volume is None:
        return False
    try:
        volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
        if percent > 0:
            volume.SetMute(0, None)
        return True
    except Exception:
        return False


def change_volume(delta: int) -> int | None:
    """Monte/baisse le volume de `delta` points. Retourne le nouveau niveau."""
    current = get_volume()
    if current is None:
        # Repli : plusieurs appuis sur les touches volume (2 points par appui).
        key = VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN
        for _ in range(max(1, abs(delta) // 2)):
            press_key(key)
        return None
    target = max(0, min(100, current + delta))
    return target if set_volume(target) else None


def set_mute(muted: bool) -> bool:
    """Coupe ou retablit le son."""
    volume = _volume_interface()
    if volume is None:
        return press_key(VK_VOLUME_MUTE)
    try:
        volume.SetMute(1 if muted else 0, None)
        return True
    except Exception:
        return False


def is_muted() -> bool | None:
    volume = _volume_interface()
    if volume is None:
        return None
    try:
        return bool(volume.GetMute())
    except Exception:
        return None


# --------------------------------------------------------------------------
# Luminosité
# --------------------------------------------------------------------------
def get_brightness() -> int | None:
    try:
        import screen_brightness_control as sbc

        values = sbc.get_brightness()
        return int(values[0]) if values else None
    except Exception:
        ok, out = run_command(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"]
        )
        if ok and out.strip().split():
            try:
                return int(out.strip().split()[0])
            except ValueError:
                return None
        return None


def set_brightness(percent: int) -> bool:
    """Regle la luminosité de l'écran (0-100)."""
    percent = max(0, min(100, int(percent)))
    try:
        import screen_brightness_control as sbc

        sbc.set_brightness(percent)
        return True
    except Exception:
        ok, _ = run_command(
            ["powershell", "-NoProfile", "-Command",
             "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
             ".WmiSetBrightness(1," + str(percent) + ")"]
        )
        return ok


# --------------------------------------------------------------------------
# Capture d'écran, notifications, presse-papiers
# --------------------------------------------------------------------------
def take_screenshot(directory) -> tuple[bool, str]:
    """Capture l'écran et enregistre le PNG horodaté. Retourne (ok, chemin)."""
    from datetime import datetime

    folder = Path(expand(str(directory)))
    folder.mkdir(parents=True, exist_ok=True)
    filename = "capture_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".png"
    target = folder / filename
    try:
        from PIL import ImageGrab

        ImageGrab.grab(all_screens=True).save(target)
        return True, str(target)
    except ImportError:
        pass
    except Exception as exc:
        return False, "capture impossible : " + str(exc)
    try:
        import pyautogui

        pyautogui.screenshot().save(target)
        return True, str(target)
    except ImportError:
        return False, "installez Pillow (pip install -r requirements.txt) pour les captures d'écran"
    except Exception as exc:
        return False, "capture impossible : " + str(exc)


def beep(frequency: int = 880, duration_ms: int = 400) -> None:
    """Petit signal sonore (winsound fait partie de la lib standard Windows)."""
    try:
        import winsound

        winsound.Beep(frequency, duration_ms)
    except Exception:
        print("\a", end="", flush=True)


def notify(title: str, message: str, popup: bool = True, sound: bool = True) -> None:
    """
    Notification Windows : bip + fenêtre non bloquante.
    La fenêtre est ouverte dans un thread pour ne pas figer l'assistant.
    """
    import threading

    if sound:
        threading.Thread(target=beep, daemon=True).start()
    if not popup:
        return

    def _popup() -> None:
        try:
            import ctypes

            # 0x40 = icone info, 0x1000 = fenêtre au premier plan
            ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x40 | 0x1000)
        except Exception as exc:
            log.debug("Popup impossible : %s", exc)

    threading.Thread(target=_popup, daemon=True).start()


def get_clipboard() -> str:
    """Lit le presse-papiers (pyperclip, repli PowerShell)."""
    try:
        import pyperclip

        return pyperclip.paste() or ""
    except Exception:
        ok, out = run_command(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
        return out if ok else ""


def set_clipboard(text: str) -> bool:
    """Ecrit dans le presse-papiers (pyperclip, repli clip.exe)."""
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        try:
            process = subprocess.Popen("clip", stdin=subprocess.PIPE, shell=True)
            process.communicate(input=text.encode("utf-16-le"))
            return process.returncode == 0
        except Exception:
            return False


def open_folder(path: str) -> tuple[bool, str]:
    """Ouvre l explorateur de fichiers sur un dossier."""
    target = expand(path)
    if not os.path.exists(target):
        return False, target
    try:
        os.startfile(target)  # type: ignore[attr-defined]
        return True, target
    except Exception:
        ok, _ = run_command(["explorer", target])
        return ok, target


# --------------------------------------------------------------------------
# Combinaisons de touches et saisie de texte
# --------------------------------------------------------------------------
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_L = 0x4C
VK_V = 0x56
KEYEVENTF_KEYUP = 2


def press_combo(*codes) -> bool:
    """
    Appuie sur une combinaison (ex: Ctrl+L), puis relache dans l ordre inverse.
    """
    try:
        import ctypes

        for code in codes:
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        for code in reversed(codes):
            ctypes.windll.user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as exc:
        log.debug("press_combo a echoue : %s", exc)
        return False


def type_text(texte: str, restaurer_presse_papiers: bool = True) -> bool:
    """
    Saisit un texte via le presse-papiers (Ctrl+V).

    On passe par le presse-papiers plutot que par une frappe caractere par
    caractere : c est instantane et cela gere correctement les accents et
    les dispositions de clavier autres que QWERTY.
    """
    ancien = get_clipboard() if restaurer_presse_papiers else ""
    if not set_clipboard(texte):
        return False
    ok = press_combo(VK_CONTROL, VK_V)
    if restaurer_presse_papiers and ancien:
        # On laisse le temps au collage avant de rendre le presse-papiers.
        import threading

        threading.Timer(1.0, set_clipboard, args=(ancien,)).start()
    return ok


# --------------------------------------------------------------------------
# Table des touches, pour composer des raccourcis par leur nom
# --------------------------------------------------------------------------
TOUCHES = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "entree": 0x0D, "echap": 0x1B, "tab": 0x09, "espace": 0x20,
    "suppr": 0x2E, "retour": 0x08, "debut": 0x24, "fin": 0x23,
    "gauche": 0x25, "haut": 0x26, "droite": 0x27, "bas": 0x28,
    "page_haut": 0x21, "page_bas": 0x22,
    "plus": 0xBB, "moins": 0xBD, "zero": 0x30,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f11": 0x7A, "f12": 0x7B,
}
# Lettres a a z.
for _lettre in "abcdefghijklmnopqrstuvwxyz":
    TOUCHES[_lettre] = ord(_lettre.upper())


def raccourci(*noms) -> bool:
    """
    Envoie un raccourci designe par des noms de touches.

        raccourci("ctrl", "c")        -> copier
        raccourci("ctrl", "shift", "t")

    Retourne False si une touche est inconnue, plutot que d envoyer une
    combinaison incomplete qui pourrait declencher autre chose.
    """
    codes = []
    for nom in noms:
        code = TOUCHES.get(str(nom).lower())
        if code is None:
            log.debug("Touche inconnue : %s", nom)
            return False
        codes.append(code)
    return press_combo(*codes)
