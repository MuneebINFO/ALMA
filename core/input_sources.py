"""
Sources d entree et sorties de l'assistant.

Toutes les sources produisent la MEME chose : une phrase + une etiquette de
source, envoyees au meme routeur. C est ce qui permettra d ajouter plus tard
une source "gesture" (camera + MediaPipe) sans dupliquer une seule ligne de
logique metier : il suffira de creer une classe qui herite de InputSource,
renvoie une commande textuelle et declare source = SOURCE_GESTURE.
"""

from __future__ import annotations

from core.context import SOURCE_TEXT, SOURCE_VOICE


class InputSource:
    """Interface commune a toutes les sources d entree."""

    source = SOURCE_TEXT
    name = "generique"

    def read(self, prompt: str = "") -> str:
        """Retourne la prochaine demande utilisateur (chaine vide si rien)."""
        raise NotImplementedError

    def write(self, text: str) -> None:
        """Affiche une reponse."""
        print(text)

    def ask(self, question: str) -> str:
        """Pose une question et attend'une reponse (confirmations)."""
        return self.read(question)

    def close(self) -> None:
        pass


class TextInput(InputSource):
    """Mode par defaut : saisie clavier dans le terminal."""

    source = SOURCE_TEXT
    name = "texte"

    def __init__(self, prompt: str = "Vous > ") -> None:
        self.prompt = prompt

    def read(self, prompt: str = "") -> str:
        try:
            return input(prompt or self.prompt)
        except (EOFError, KeyboardInterrupt):
            return "quitte"

    def ask(self, question: str) -> str:
        return self.read(question + " ")


class VoiceInput(InputSource):
    """
    Mode voix : micro pour l entree, synthese vocale pour la sortie.

    En cas d echec de reconnaissance, on retombe sur le clavier plutot que de
    bloquer l'utilisateur (`allow_text_fallback`).
    """

    source = SOURCE_VOICE
    name = "voix"

    def __init__(self, stt, tts, allow_text_fallback: bool = True) -> None:
        self.stt = stt
        self.tts = tts
        self.allow_text_fallback = allow_text_fallback

    def read(self, prompt: str = "") -> str:
        if not self.stt or not self.stt.available:
            if self.allow_text_fallback:
                return input(prompt or "Vous (clavier) > ")
            return ""
        print("[micro] Je vous ecoûte...")
        heard = self.stt.listen()
        if heard:
            print("Vous (voix) > " + heard)
        return heard

    def write(self, text: str) -> None:
        print(text)

    def ask(self, question: str) -> str:
        self.write(question)
        if self.tts is not None:
            self.tts.say(question, blocking=True)
        answer = self.read()
        if not answer and self.allow_text_fallback:
            answer = input("(repondez au clavier) > ")
        return answer
