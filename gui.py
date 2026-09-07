"""
Alma - application vocale.

Interface entierement pilotee a la voix : Alma ecoute des le lancement,
mais reste passif jusqu a ce qu on prononce son nom.

  - « Alma, quelle heure est-il »  -> la commande est executee
  - « Alma » seul                  -> il repond « Oui ? » et attend la suite
  - toute autre phrase               -> ignoree

L orbe central est anime en continu : anneau d onde deforme par le niveau du
micro, arcs en rotation et halo. C est le retour visuel qui montre que la voix
est captee.
"""

from __future__ import annotations

import math
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

FOND = "#070b12"
FOND_CARTE = "#101724"
TEXTE = "#e6edf7"
TEXTE_DOUX = "#6b7d99"
BORDURE = "#1b2536"

# Une couleur et un libelle par etat.
ETATS = {
    "demarrage":   ("#8b5cf6", "Démarrage..."),
    "calibration": ("#8b5cf6", "Calibration du micro..."),
    "veille":      ("#2b4a6f", "Dites « {nom} »"),
    "passif":      ("#2b4a6f", "Dites « {nom} »"),
    "voix":        ("#38bdf8", "Voix captée..."),
    "arme":        ("#22c55e", "Je vous écoute"),
    "reflexion":   ("#fbbf24", "Un instant..."),
    "execution":   ("#fbbf24", "Exécution..."),
    "reponse":     ("#a78bfa", "..."),
    "erreur":      ("#f87171", "Erreur"),
    "arret":       ("#3f4c63", "Micro coupé"),
}


def melanger(couleur_a: str, couleur_b: str, facteur: float) -> str:
    """Interpole deux couleurs (sert aux transitions douces et au halo)."""
    a = couleur_a.lstrip("#")
    b = couleur_b.lstrip("#")
    canaux = []
    for i in (0, 2, 4):
        depart = int(a[i:i + 2], 16)
        arrivee = int(b[i:i + 2], 16)
        canaux.append(max(0, min(255, int(depart + (arrivee - depart) * facteur))))
    return "#%02x%02x%02x" % tuple(canaux)


class Orbe(tk.Canvas):
    """
    Orbe anime.

    Trois couches superposees :
      1. un halo diffus (cercles concentriques melanges au fond) ;
      2. un anneau d onde dont le rayon est deforme par l historique des
         niveaux sonores -- l onde tourne, ce qui donne l effet « vivant » ;
      3. des arcs en rotation lente, a vitesses differentes.

    Le niveau et la couleur sont lisses a chaque image : aucun changement
    brusque, ce qui donne un rendu fluide.
    """

    TAILLE = 300
    POINTS = 96          # resolution de l anneau d onde
    HISTORIQUE = 48      # memoire des niveaux, repartie autour du cercle

    def __init__(self, master) -> None:
        super().__init__(master, width=self.TAILLE, height=self.TAILLE,
                         bg=FOND, highlightthickness=0)
        self.etat = "demarrage"
        self.couleur_courante = ETATS["demarrage"][0]
        self.niveau = 0.0
        self.niveau_lisse = 0.0
        self.phase = 0.0
        self.rotation = 0.0
        self.historique = [0.0] * self.HISTORIQUE
        self._animer()

    # -- pilotage -------------------------------------------------------------
    def definir_etat(self, etat: str) -> None:
        if etat in ETATS:
            self.etat = etat

    def definir_niveau(self, niveau: float) -> None:
        self.niveau = max(0.0, min(1.0, float(niveau)))

    # -- rendu ----------------------------------------------------------------
    def _animer(self) -> None:
        # Lissage asymetrique : reaction vive a la voix, retombee douce.
        cible = self.niveau
        facteur = 0.45 if cible > self.niveau_lisse else 0.10
        self.niveau_lisse += (cible - self.niveau_lisse) * facteur

        self.historique.append(self.niveau_lisse)
        del self.historique[:-self.HISTORIQUE]

        self.phase += 0.055
        self.rotation += 0.9

        # Transition douce vers la couleur de l etat courant.
        couleur_cible = ETATS[self.etat][0]
        self.couleur_courante = melanger(self.couleur_courante, couleur_cible, 0.12)

        self.delete("all")
        centre = self.TAILLE / 2
        actif = self.etat in ("voix", "arme", "reflexion", "execution", "reponse")
        # Respiration lente au repos, amplitude sonore quand la voix parle.
        respiration = 0.10 + 0.05 * math.sin(self.phase * 0.6)
        amplitude = respiration + self.niveau_lisse * (0.85 if actif else 0.45)

        self._halo(centre, amplitude)
        self._anneau_onde(centre, amplitude)
        self._arcs(centre, amplitude)
        self._coeur(centre, amplitude)

        self.after(25, self._animer)

    def _halo(self, centre: float, amplitude: float) -> None:
        """Degrade radial simule par des cercles de plus en plus sombres."""
        rayon_max = 60 + amplitude * 70
        couches = 14
        for i in range(couches, 0, -1):
            rayon = rayon_max * (i / float(couches))
            couleur = melanger(FOND, self.couleur_courante, 0.04 + 0.035 * (couches - i))
            self.create_oval(centre - rayon, centre - rayon,
                             centre + rayon, centre + rayon,
                             fill=couleur, outline="")

    def _anneau_onde(self, centre: float, amplitude: float) -> None:
        """Anneau deforme par l historique des niveaux : l onde semble tourner."""
        base = 74 + amplitude * 26
        points = []
        for i in range(self.POINTS):
            angle = 2 * math.pi * i / self.POINTS
            memoire = self.historique[int(i / self.POINTS * self.HISTORIQUE) - 1]
            ondulation = (
                math.sin(angle * 4 + self.phase * 1.5) * 0.42
                + math.sin(angle * 7 - self.phase * 1.0) * 0.30
                + math.sin(angle * 11 + self.phase * 0.7) * 0.18
                + math.sin(angle * 16 - self.phase * 0.5) * 0.10
            )
            rayon = base + ondulation * (4 + amplitude * 17) + memoire * 10
            points.extend([centre + rayon * math.cos(angle), centre + rayon * math.sin(angle)])
        self.create_polygon(
            points, outline=melanger(FOND, self.couleur_courante, 0.85),
            fill="", width=2, smooth=True,
        )

    def _arcs(self, centre: float, amplitude: float) -> None:
        """Arcs concentriques en rotation, a vitesses et sens differents."""
        for index, (rayon_base, etendue, vitesse) in enumerate(
            ((108, 70, 1.0), (124, 44, -0.62), (140, 26, 0.35))
        ):
            rayon = rayon_base + amplitude * 12
            depart = (self.rotation * vitesse + index * 120) % 360
            self.create_arc(
                centre - rayon, centre - rayon, centre + rayon, centre + rayon,
                start=depart, extent=etendue, style="arc",
                outline=melanger(FOND, self.couleur_courante, 0.55 - index * 0.13),
                width=2,
            )

    def _coeur(self, centre: float, amplitude: float) -> None:
        """Noyau lumineux, avec un liser plus clair."""
        rayon = 34 + amplitude * 16
        self.create_oval(centre - rayon, centre - rayon, centre + rayon, centre + rayon,
                         fill=self.couleur_courante, outline="")
        interne = rayon * 0.55
        self.create_oval(centre - interne, centre - interne,
                         centre + interne, centre + interne,
                         fill=melanger(self.couleur_courante, "#ffffff", 0.30), outline="")


class AlmaApp:
    """Fenetre principale : orbe, statut, transcription et journal."""

    def __init__(self, root: tk.Tk, assistant) -> None:
        self.root = root
        self.assistant = assistant
        self.evenements: queue.Queue = queue.Queue()
        self.ecoute_active = threading.Event()
        self.thread_audio: threading.Thread | None = None
        self.stt = None
        self.nom = assistant.name          # nom affiche, issu de la config

        # La session d ecoute vit dans l assistant : les commandes peuvent
        # ainsi consulter le contexte (« recherche Damso » apres « va sur
        # YouTube »), et le mode texte en profite aussi.
        self.moteur = assistant.moteur

        root.title(assistant.name)
        root.configure(bg=FOND)
        root.geometry("760x820")
        root.minsize(620, 720)

        self._construire()
        self._brancher_sorties()
        self.root.after(40, self._traiter_evenements)

    # -- construction ---------------------------------------------------------
    def _construire(self) -> None:
        police_titre = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        police_statut = tkfont.Font(family="Segoe UI", size=13)
        police_entendu = tkfont.Font(family="Segoe UI", size=15)
        police_texte = tkfont.Font(family="Segoe UI", size=10)

        entete = tk.Frame(self.root, bg=FOND)
        entete.pack(fill="x", padx=28, pady=(22, 0))
        tk.Label(entete, text="ALMA", font=police_titre, bg=FOND, fg=TEXTE).pack(side="left")
        tk.Label(entete, text="assistant vocal local", font=police_texte,
                 bg=FOND, fg=TEXTE_DOUX).pack(side="left", padx=(12, 0), pady=(10, 0))
        self.voyant = tk.Label(entete, text="●  hors ligne", font=police_texte,
                               bg=FOND, fg=TEXTE_DOUX)
        self.voyant.pack(side="right", pady=(10, 0))

        self.orbe = Orbe(self.root)
        self.orbe.pack(pady=(4, 0))

        self.etiquette_statut = tk.Label(self.root, text="Démarrage...", font=police_statut,
                                         bg=FOND, fg=TEXTE_DOUX)
        self.etiquette_statut.pack(pady=(0, 2))

        # Ce que Alma a compris.
        self.etiquette_entendu = tk.Label(self.root, text="", font=police_entendu,
                                          bg=FOND, fg=TEXTE, wraplength=640, height=2)
        self.etiquette_entendu.pack(pady=(4, 8))

        boutons = tk.Frame(self.root, bg=FOND)
        boutons.pack(pady=(0, 14))
        self.bouton_micro = self._bouton(boutons, "Couper le micro", self.basculer_micro)
        self.bouton_micro.pack(side="left", padx=5)
        self._bouton(boutons, "Que sais-tu faire ?", self.montrer_aide).pack(side="left", padx=5)
        self._bouton(boutons, "Quitter", self.quitter).pack(side="left", padx=5)

        cadre = tk.Frame(self.root, bg=BORDURE)
        cadre.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        self.journal = tk.Text(cadre, bg=FOND_CARTE, fg=TEXTE, font=police_texte, bd=0,
                               padx=16, pady=14, wrap="word", state="disabled", height=8)
        self.journal.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        barre = tk.Scrollbar(cadre, command=self.journal.yview, bg=FOND_CARTE, bd=0)
        barre.pack(side="right", fill="y")
        self.journal.configure(yscrollcommand=barre.set)
        self.journal.tag_configure("moi", foreground="#38bdf8")
        self.journal.tag_configure("assistant", foreground="#a78bfa")
        self.journal.tag_configure("erreur", foreground="#f87171")
        self.journal.tag_configure("corps", foreground=TEXTE)

    def _bouton(self, parent, texte: str, commande) -> tk.Button:
        return tk.Button(parent, text=texte, command=commande, bg=FOND_CARTE, fg=TEXTE,
                         activebackground=BORDURE, activeforeground=TEXTE, bd=0,
                         font=tkfont.Font(family="Segoe UI", size=10),
                         padx=18, pady=9, relief="flat", cursor="hand2")

    def montrer_aide(self) -> None:
        threading.Thread(target=self._executer, args=("aide", "text"), daemon=True).start()

    # -- pont assistant / interface -------------------------------------------
    def _brancher_sorties(self) -> None:
        """Redirige les sorties de l assistant vers le journal de la fenetre."""
        app = self

        class SortieGraphique:
            source = "voice"

            def read(self, prompt: str = "") -> str:
                return ""

            def write(self, texte: str) -> None:
                app.evenements.put(("journal", (app.nom, texte)))

            def ask(self, question: str) -> str:
                return app.demander(question)

            def close(self) -> None:
                pass

        self.assistant.io = SortieGraphique()

    def demander(self, question: str) -> str:
        """Confirmation modale, demandee depuis le thread audio."""
        from tkinter import messagebox

        resultat: queue.Queue = queue.Queue()
        self.root.after(0, lambda: resultat.put(
            "oui" if messagebox.askyesno(self.nom, question) else "non"
        ))
        return resultat.get()

    def journaliser(self, qui: str, texte: str, tag: str = "assistant") -> None:
        if not texte:
            return
        self.journal.configure(state="normal")
        self.journal.insert("end", qui + " : ", tag)
        self.journal.insert("end", texte.strip() + "\n\n", "corps")
        self.journal.see("end")
        self.journal.configure(state="disabled")

    def definir_statut(self, etat: str, detail: str = "") -> None:
        couleur, libelle = ETATS.get(etat, ETATS["veille"])
        # « {nom} » est remplace par le nom configure : renommer l assistant
        # ne demande de toucher a aucun libelle.
        libelle = libelle.replace("{nom}", self.nom)
        self.orbe.definir_etat(etat)
        self.etiquette_statut.configure(text=detail or libelle, fg=couleur)

    # -- boucle d evenements --------------------------------------------------
    def _traiter_evenements(self) -> None:
        """Tkinter n est pas thread-safe : seule cette boucle touche a l interface."""
        try:
            while True:
                type_evenement, charge = self.evenements.get_nowait()
                if type_evenement == "niveau":
                    niveau, etat = charge
                    self.orbe.definir_niveau(niveau)
                    if etat:
                        self.definir_statut(etat)
                elif type_evenement == "statut":
                    self.definir_statut(*charge)
                elif type_evenement == "entendu":
                    self.etiquette_entendu.configure(
                        text=("« " + charge + " »") if charge else ""
                    )
                elif type_evenement == "voyant":
                    couleur, texte = charge
                    self.voyant.configure(text="●  " + texte, fg=couleur)
                elif type_evenement == "journal":
                    qui, texte = charge
                    self.journaliser(qui, texte, "moi" if qui == "Vous" else "assistant")
                elif type_evenement == "erreur":
                    self.journaliser(self.nom, charge, "erreur")
                elif type_evenement == "quitter":
                    self.quitter()
                    return
        except queue.Empty:
            pass
        self._rafraichir_compte_a_rebours()
        self.root.after(40, self._traiter_evenements)

    def _rafraichir_compte_a_rebours(self) -> None:
        """Affiche le temps restant de la session, tant qu elle est ouverte."""
        if self.orbe.etat != "arme":
            return
        restant = int(self.moteur.secondes_restantes())
        if restant <= 0:
            self.definir_statut("veille")
            return
        self.etiquette_statut.configure(
            text="Je vous écoute — " + str(restant) + " s", fg=ETATS["arme"][0]
        )

    # -- execution ------------------------------------------------------------
    def _executer(self, texte: str, source: str) -> None:
        """Route la demande hors du thread graphique pour ne pas figer l interface."""
        self.evenements.put(("statut", ("execution", "")))
        try:
            reponse = self.assistant.handle(texte, source=source)
        except Exception as exc:
            self.evenements.put(("erreur", "Erreur interne : " + str(exc)))
            self.evenements.put(("statut", (self._etat_repos(), "")))
            return

        if reponse.text:
            if reponse.ok:
                self.evenements.put(("journal", (self.nom, reponse.text)))
            else:
                self.evenements.put(("erreur", reponse.text))
            if reponse.speak and self.assistant.speaks:
                # Lecture NON bloquante : sans cela le micro reste sourd
                # pendant qu il parle, et on ne peut pas lui couper la parole.
                self.evenements.put(("statut", ("reponse", "Je réponds...")))
                self.assistant.tts.say(reponse.text)

        if reponse.should_exit:
            self.evenements.put(("quitter", None))
            return
        self.evenements.put(("statut", (self._etat_repos(), "")))

    def _etat_repos(self) -> str:
        """Etat affiche entre deux commandes."""
        if not self.ecoute_active.is_set():
            return "arret"
        return "arme" if self.moteur.arme else "veille"

    # -- micro ----------------------------------------------------------------
    def demarrer_ecoute(self) -> None:
        """Prepare le micro et lance l ecoute continue."""
        if self.stt is None:
            from core.stt import SpeechToText

            self.evenements.put(("statut", ("demarrage", "Préparation du micro...")))
            self.stt = SpeechToText(self.assistant.config)
            self.assistant.stt = self.stt

        if not self.stt.available:
            self.evenements.put((
                "erreur",
                "Micro indisponible : " + (self.stt.error or "aucun périphérique détecté")
                + " Lancez « python diagnostic_micro.py » pour en savoir plus.",
            ))
            self.evenements.put(("statut", ("erreur", "Micro indisponible")))
            self.evenements.put(("voyant", (ETATS["erreur"][0], "micro absent")))
            self.bouton_micro.configure(text="Réessayer le micro")
            return

        self.ecoute_active.set()
        self.bouton_micro.configure(text="Couper le micro")
        if self.thread_audio is None or not self.thread_audio.is_alive():
            self.thread_audio = threading.Thread(target=self._boucle_micro, daemon=True)
            self.thread_audio.start()

    def basculer_micro(self) -> None:
        if self.ecoute_active.is_set():
            self.ecoute_active.clear()
            self.moteur.desarmer()
            self.bouton_micro.configure(text="Activer le micro")
            self.definir_statut("arret")
            self.etiquette_entendu.configure(text="")
            self.voyant.configure(text="●  micro coupé", fg=TEXTE_DOUX)
        else:
            self.demarrer_ecoute()

    def _boucle_micro(self) -> None:
        """
        Ecoute en continu. Alma entend tout, mais n agit que si son nom a
        ete prononce (ou s il vient d etre reveille).
        """
        from core import wake

        def sur_niveau(niveau: float, etat_audio: str) -> None:
            if etat_audio == "calibration":
                etat = "calibration"
            elif etat_audio == "parole":
                etat = "voix"
                # On coupe la parole DES LA DETECTION de la voix, pas apres
                # la transcription : attendre reviendrait a finir sa phrase
                # pendant que l utilisateur parle.
                self.assistant.interrompre_parole()
            else:
                etat = self._etat_repos()
            self.evenements.put(("niveau", (niveau, etat)))

        self.evenements.put(("statut", ("calibration", "Calibration du micro...")))
        seuil = self.stt.recalibrate(1.2, on_level=sur_niveau)
        self.evenements.put(("voyant", (ETATS["veille"][0], "à l'écoute")))
        self.evenements.put((
            "journal",
            (self.nom, "Je suis à l'écoute. Dites « " + self.nom + " » pour m'activer, "
                       "ou « " + self.nom + " » suivi directement de votre demande."),
        ))
        if seuil <= 0:
            self.evenements.put(("erreur", "Seuil de détection nul : le micro ne capte rien."))

        while self.ecoute_active.is_set():
            self.evenements.put(("statut", (self._etat_repos(), "")))
            try:
                texte = self.stt.listen_live(
                    on_level=sur_niveau,
                    timeout=6.0,
                    doit_continuer=self.ecoute_active.is_set,
                )
            except Exception as exc:
                self.evenements.put(("erreur", "Erreur du micro : " + str(exc)))
                break

            if not self.ecoute_active.is_set():
                break
            if not texte:
                continue           # silence, ou parole non comprise

            # On lui coupe la parole des qu on parle -- sauf si le micro a
            # simplement capte sa propre voix dans les haut-parleurs.
            if self.assistant.tts.parle():
                if self._est_son_echo(texte):
                    continue
                self.assistant.tts.arreter()

            analyse = self.moteur.analyser(texte)

            if analyse.etat == wake.IGNORE:
                # On montre quand meme ce qui a ete entendu : l utilisateur voit
                # que le micro fonctionne, meme si Alma ne reagit pas.
                self.evenements.put(("entendu", texte))
                continue

            self.evenements.put(("entendu", texte))

            if analyse.etat == wake.FIN_SESSION:
                # « arrête » pendant un défilement doit arrêter le défilement,
                # pas refermer la session : on interrompt d'abord l'action.
                if self.assistant.interrompre():
                    self.moteur.armer()          # la session continue
                    self.evenements.put(("journal", ("Vous", texte)))
                    self.evenements.put(("journal", (self.nom, "J'arrête.")))
                    self.evenements.put(("statut", ("arme", "")))
                    continue
                reponse = wake.accuse_fin()
                self.assistant.oublier_contexte()
                self.evenements.put(("journal", ("Vous", texte)))
                self.evenements.put(("journal", (self.nom, reponse)))
                self.evenements.put(("entendu", ""))
                self.evenements.put(("statut", ("veille", "")))
                if self.assistant.speaks:
                    self.assistant.tts.say(reponse, cacher=True)
                continue

            if analyse.etat == wake.REVEIL_SEUL:
                reponse = wake.accuse_reception()
                self.evenements.put(("journal", ("Vous", texte)))
                self.evenements.put(("journal", (self.nom, reponse)))
                self.evenements.put(("statut", ("arme", "")))
                if self.assistant.speaks:
                    # `cacher` : la replique est pre-synthetisee, donc immediate.
                    self.assistant.tts.say(reponse, cacher=True)
                continue

            commande = analyse.commande
            self.evenements.put(("journal", ("Vous", commande)))
            self.evenements.put(("statut", ("reflexion", "")))
            self._executer(commande, "voice")

        self.evenements.put(("niveau", (0.0, "arret")))
        self.evenements.put(("voyant", (TEXTE_DOUX, "micro coupé")))

    def _est_son_echo(self, propos: str) -> bool:
        """
        Le micro a-t-il simplement capte la voix de l assistant ?

        Deliberement PRUDENT : un ordre court n est jamais considere comme un
        echo. Nos propres phrases contiennent le nom de l assistant, si bien
        qu un « Alma » lance pendant qu il parle serait sinon pris pour un
        renvoi de son haut-parleur -- et ignore.
        """
        from core import text_utils

        en_cours = text_utils.normalize(self.assistant.tts.texte_en_cours)
        if not en_cours.strip():
            return False
        if self.moteur.separer_mot_appel(propos)[0]:
            return False
        mots = [m for m in text_utils.tokenize(text_utils.normalize(propos)) if len(m) >= 4]
        if len(mots) < 3:
            return False
        communs = sum(1 for m in mots if m in en_cours)
        return communs / len(mots) >= 0.75

    # -- fermeture ------------------------------------------------------------
    def quitter(self) -> None:
        self.ecoute_active.clear()
        try:
            self.assistant.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main(argv=None) -> int:
    """Point d entree de l application."""
    import argparse

    parser = argparse.ArgumentParser(description="Alma - assistant vocal")
    parser.add_argument("--config", metavar="FICHIER", help="fichier de configuration")
    parser.add_argument("--mute", action="store_true", help="ne pas lire les réponses à voix haute")
    parser.add_argument("--sans-micro", action="store_true",
                        help="démarrer sans activer le micro")
    args = parser.parse_args(argv)

    from config import load_config
    from core.assistant import Assistant

    config = load_config(args.config)
    if args.mute:
        config.set("voice.speak_responses", False)

    root = tk.Tk()
    assistant = Assistant(config=config)
    app = AlmaApp(root, assistant)
    root.protocol("WM_DELETE_WINDOW", app.quitter)

    def demarrer() -> None:
        moteur = getattr(assistant.tts, "moteur_actif", "aucun")
        libelle = {"neuronal": "voix neuronale", "sapi5": "voix locale"}.get(moteur, "sans voix")
        app.evenements.put((
            "voyant",
            (ETATS["veille"][0] if moteur != "aucun" else TEXTE_DOUX, libelle),
        ))
        if not args.sans_micro:
            app.demarrer_ecoute()
        else:
            app.definir_statut("arret")
            app.bouton_micro.configure(text="Activer le micro")

    # L ecoute demarre automatiquement : l application est vocale par nature.
    root.after(300, demarrer)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
