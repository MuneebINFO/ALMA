"""Tests de la normalisation de texte."""

import pytest

from core import text_utils


def test_normalisation_preserve_la_longueur():
    """L alignement raw/norm est la base de l extraction des arguments."""
    for phrase in ["Alma, ouvre Chrome !", "Éàçüö", "cherche l'IA sur Google"]:
        assert len(text_utils.normalize(phrase)) == len(phrase)


def test_normalisation_replie_accents_et_ponctuation():
    assert text_utils.normalize("Éléphant, ça va ?") == "elephant  ca va  "


def test_mot_de_reveil_retire_en_gardant_alignement():
    raw = "Alma, ouvre Chrome"
    norm = text_utils.normalize(raw)
    raw2, norm2 = text_utils.strip_wake_word(raw, norm)
    assert raw2 == "ouvre Chrome"
    assert norm2 == "ouvre chrome"
    assert len(raw2) == len(norm2)


def test_fuzzy_tolere_les_fautes_de_frappe():
    tokens = ["ouvre", "calculatrice"]
    assert text_utils.fuzzy_in("calculatrice", tokens)
    assert text_utils.fuzzy_in("calculatrise", tokens)   # faute de frappe
    assert not text_utils.fuzzy_in("navigateur", tokens)


def test_best_match_choisit_le_bon_candidat():
    candidats = ["chrome", "firefox", "bloc note"]
    assert text_utils.best_match("gogle chrome", candidats) == "chrome"
    assert text_utils.best_match("bloc notes", candidats) == "bloc note"
    assert text_utils.best_match("xyzabc", candidats) is None


# --------------------------------------------------------------------------
# Balisage Markdown
# --------------------------------------------------------------------------
@pytest.mark.parametrize("texte,attendu", [
    ("Il y a **1 seul fichier** ici", "Il y a 1 seul fichier ici"),
    ("le fichier `LISEZ-MOI.md`", "le fichier LISEZ-MOI.md"),
    ("## Titre\n- un\n- deux", "Titre\nun\ndeux"),
    ("un *mot* en italique", "un mot en italique"),
    ("voir [la doc](https://exemple.com/a) pour la suite", "voir la doc pour la suite"),
])
def test_le_balisage_disparait_avant_la_lecture(texte, attendu):
    """« **1 seul fichier** » se lirait « astérisque astérisque 1 seul fichier »."""
    assert text_utils.sans_balisage(texte) == attendu


@pytest.mark.parametrize("texte", [
    "calcul : 3 * 4 * 5 = 60",
    "le fichier mon_fichier_test.py",
    "5 * 3 fait 15",
])
def test_ce_qui_ressemble_a_du_balisage_sans_en_etre_est_laisse(texte):
    """Une multiplication et un souligné de nom de fichier ne sont pas du Markdown."""
    assert text_utils.sans_balisage(texte) == texte
