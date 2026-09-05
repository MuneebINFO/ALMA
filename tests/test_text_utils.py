"""Tests de la normalisation de texte."""

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
