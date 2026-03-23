from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from app.learning.units import LearningUnit, LearningUnitType, _SKIP_LEMMAS
from app.learning.knowledge import KnowledgeState, UserKnowledgeStore


class LevelTier(str, Enum):
    """Self-reported proficiency tier."""
    COMPLETE_BEGINNER = "complete_beginner"
    A1 = "a1"
    A2 = "a2"
    B1 = "b1"


# ---------------------------------------------------------------------------
# Frequency-ranked lemma sets
# Each constant holds only the *additions* for that tier.
# ---------------------------------------------------------------------------

_A1_LEMMAS: frozenset[str] = frozenset({
    "sein", "haben", "werden",
    "können", "müssen", "wollen", "sollen", "dürfen", "mögen",
    "gehen", "kommen", "machen", "sagen", "sehen", "wissen",
    "denken", "finden", "nehmen", "geben", "stehen", "liegen",
    "sitzen", "essen", "trinken", "schlafen", "fahren", "lesen",
    "hören", "sprechen", "lernen", "kaufen", "heißen", "wohnen",
    "bleiben", "laufen", "schreiben", "arbeiten", "spielen",
    "bringen", "brauchen", "suchen", "fragen", "verstehen",
    "helfen", "zeigen", "leben", "legen", "stellen",
    "der", "die", "das", "ein", "kein",
    "mein", "dein", "unser",
    "dieser", "jeder", "alle",
    "in", "auf", "mit", "von", "zu", "an", "für", "aus",
    "bei", "nach", "über", "unter", "durch", "ohne",
    "gegen", "um", "bis", "seit",
    "und", "oder", "aber", "dass", "wenn", "weil", "als",
    "ob", "wie", "so", "also", "dann", "deshalb",
    "nicht", "auch", "nur", "sehr", "hier", "da",
    "jetzt", "heute", "immer", "wieder", "ganz", "wirklich",
    "natürlich", "vielleicht", "manchmal", "oft", "mehr",
    "genug", "fast", "gar", "nun",
    "man", "sich",
    "gut", "schlecht", "groß", "klein", "neu", "alt",
    "jung", "lang", "kurz", "schön", "heiß", "kalt", "warm",
    "richtig", "falsch", "schwer", "leicht", "wichtig",
    "tag", "zeit", "mann", "frau", "kind", "haus", "jahr",
    "hand", "stadt", "land", "welt", "leben", "weg", "arbeit",
    "schule", "geld", "buch", "frage", "name", "wasser",
})

_A2_ADDITIONAL_LEMMAS: frozenset[str] = frozenset({
    "erklären", "erzählen", "kennen", "glauben", "antworten",
    "treffen", "reisen", "warten", "öffnen", "schließen",
    "beginnen", "vergessen", "erinnern", "vorstellen",
    "anfangen", "aufmachen", "ankommen", "vorbereiten",
    "waschen", "zahlen", "holen", "reden", "wünschen",
    "teilen", "versuchen", "hoffen", "benutzen", "verlassen",
    "passieren", "verlieren", "verkaufen", "bezahlen",
    "empfehlen", "gehören", "meinen", "mitnehmen",
    "eins", "zwei", "drei", "vier", "fünf",
    "sechs", "sieben", "acht", "neun", "zehn",
    "zwanzig", "hundert", "tausend",
    "rot", "blau", "grün", "gelb", "schwarz", "weiß", "grau", "braun",
    "einfach", "schwierig", "billig", "teuer", "müde", "glücklich",
    "traurig", "ruhig", "laut", "frisch", "sauber", "schmutzig",
    "offen", "fertig", "nötig", "pünktlich", "nett", "toll",
    "gesund", "krank", "hungrig", "durstig", "frei", "beliebt",
    "morgen", "gestern", "abend", "nacht", "woche", "monat",
    "minute", "stunde", "sekunde",
    "vater", "mutter", "bruder", "schwester", "eltern",
    "freundin", "kollege", "lehrer", "schüler", "chef",
    "auto", "bus", "zug", "fahrrad", "flugzeug", "bahnhof",
    "straße", "platz", "ort", "hotel", "restaurant",
    "brot", "milch", "fleisch", "kaffee", "tee", "obst", "gemüse",
    "kopf", "arm", "bein", "auge", "ohr", "mund",
    "büro", "telefon", "brief", "gast", "raum", "tisch",
    "plan", "idee", "problem", "thema", "wort", "sprache",
    "unterschied", "ergebnis", "beispiel", "möglichkeit", "situation",
    "beide", "einige", "welch", "solch",
    "trotzdem", "außerdem", "deswegen", "endlich", "plötzlich",
    "sofort", "bereits", "ungefähr", "zusammen", "allein",
    "meistens", "leider", "eigentlich", "wenigstens", "kaum",
})

_B1_ADDITIONAL_LEMMAS: frozenset[str] = frozenset({
    "entscheiden", "entwickeln", "erwarten", "erlauben",
    "fördern", "verändern", "verbessern", "vorschlagen",
    "darstellen", "beschreiben", "erreichen", "nachdenken",
    "aufhören", "bestehen", "erscheinen", "entstehen",
    "erkennen", "berichten", "betonen", "bemerken", "beachten",
    "leiten", "lösen", "führen", "gelten", "nennen",
    "steigen", "stimmen", "tragen", "unterscheiden",
    "verhindern", "zunehmen", "abnehmen", "gelingen",
    "scheitern", "bewegen", "weitermachen", "vorgehen",
    "anbieten", "aufbauen", "ausgehen",
    "bereich", "bevölkerung", "bildung", "einfluss", "entwicklung",
    "erfahrung", "gesellschaft", "gesetz", "grund", "information",
    "interesse", "lage", "lösung", "meinung", "nachricht",
    "ordnung", "politik", "recht", "regierung", "sicherheit",
    "system", "verantwortung", "verhältnis", "wirtschaft",
    "wirkung", "zusammenhang", "entscheidung", "fähigkeit",
    "folge", "grenze", "inhalt", "kosten", "leistung",
    "preis", "produkt", "programm", "projekt", "qualität",
    "reaktion", "regel", "stärke", "ursache", "verbindung",
    "zustand", "angebot", "vorteil", "nachteil", "aufgabe",
    "erklärung", "bedeutung", "einheit", "kraft",
    "struktur", "ziel", "zweck", "rahmen", "niveau",
    "aktuell", "allgemein", "ähnlich", "bedeutend", "bekannt",
    "bereit", "deutlich", "direkt", "entsprechend", "erfolgreich",
    "gemeinsam", "genau", "gewiss", "international", "möglich",
    "national", "offiziell", "persönlich", "politisch", "praktisch",
    "sozial", "stark", "typisch", "wirtschaftlich", "wissenschaftlich",
    "öffentlich", "zusätzlich", "wesentlich", "besondere",
    "allerdings", "anscheinend", "dagegen", "daher", "damals",
    "dabei", "damit", "darüber", "davon", "dazu", "gegenüber",
    "jedoch", "letztlich", "möglicherweise", "offenbar",
    "schließlich", "seitdem", "sicherlich", "stattdessen",
    "tatsächlich", "überall", "übrigens", "weitgehend",
    "zumindest", "zunächst", "zwar", "immerhin",
    "einerseits", "andererseits", "inzwischen", "jedenfalls",
    "letztendlich", "scheinbar", "offensichtlich",
})

_TIER_DELTAS: dict[LevelTier, frozenset[str]] = {
    LevelTier.COMPLETE_BEGINNER: frozenset(),
    LevelTier.A1:                _A1_LEMMAS,
    LevelTier.A2:                _A2_ADDITIONAL_LEMMAS,
    LevelTier.B1:                _B1_ADDITIONAL_LEMMAS,
}

_TIER_ORDER: tuple[LevelTier, ...] = (
    LevelTier.COMPLETE_BEGINNER,
    LevelTier.A1,
    LevelTier.A2,
    LevelTier.B1,
)


@dataclass(frozen=True)
class OnboardingResult:
    """Summary of a completed onboarding seed operation."""
    user_id: str
    seeded_count: int
    skipped_count: int
    state: KnowledgeState
    tier: Optional[LevelTier] = None


class VocabularyOnboarding:
    """
    Seeds a new user's knowledge store from a frequency-ranked vocabulary tier
    or a custom lemma list.

    All write methods are non-destructive: units the user has already
    progressed past the target state are left untouched.
    """

    def seed_from_level(
        self,
        user_id: str,
        tier: LevelTier,
        store: UserKnowledgeStore,
        state: KnowledgeState = KnowledgeState.KNOWN_PASSIVE,
    ) -> OnboardingResult:
        """Seed vocabulary for a user based on their self-reported level tier."""
        lemma_keys = self.get_tier_lemmas(tier)
        return self.seed_from_lemmas(user_id, lemma_keys, store, state=state, tier=tier)

    def seed_from_lemmas(
        self,
        user_id: str,
        lemma_keys: Iterable[str],
        store: UserKnowledgeStore,
        state: KnowledgeState = KnowledgeState.KNOWN_PASSIVE,
        tier: Optional[LevelTier] = None,
    ) -> OnboardingResult:
        """Seed an arbitrary collection of lemma keys as known for a user."""
        to_seed: list[LearningUnit] = []
        skipped = 0

        for raw_key in lemma_keys:
            key = raw_key.strip().lower()
            if not key or key in _SKIP_LEMMAS:
                continue
            unit = _make_lemma_unit(key)
            current_state = store.get_state(user_id, unit)
            if current_state >= state:
                skipped += 1
            else:
                to_seed.append(unit)

        store.seed_known_units(user_id, to_seed, state=state)
        return OnboardingResult(
            user_id=user_id,
            seeded_count=len(to_seed),
            skipped_count=skipped,
            state=state,
            tier=tier,
        )

    def mark_known(
        self,
        user_id: str,
        lemma_keys: Iterable[str],
        store: UserKnowledgeStore,
    ) -> OnboardingResult:
        """Mark specific lemma keys as KNOWN_PASSIVE for a user."""
        return self.seed_from_lemmas(
            user_id,
            lemma_keys,
            store,
            state=KnowledgeState.KNOWN_PASSIVE,
        )

    @staticmethod
    def get_tier_lemmas(tier: LevelTier) -> frozenset[str]:
        """Return the cumulative lemma set for *tier*."""
        result: set[str] = set()
        for t in _TIER_ORDER:
            result |= _TIER_DELTAS[t]
            if t == tier:
                break
        return frozenset(result)

    @staticmethod
    def tier_size(tier: LevelTier) -> int:
        return len(VocabularyOnboarding.get_tier_lemmas(tier))

    @staticmethod
    def sample_tier_lemmas(
        tier: LevelTier,
        n: int,
        above_tier: Optional[LevelTier] = None,
    ) -> list[str]:
        """Return up to *n* lemma keys from the delta above *above_tier*."""
        if above_tier is not None:
            pool = _TIER_DELTAS.get(tier, frozenset())
        else:
            pool = VocabularyOnboarding.get_tier_lemmas(tier)
        return sorted(pool)[:n]


def _make_lemma_unit(key: str) -> LearningUnit:
    """Build a LearningUnit for a raw lemma key."""
    return LearningUnit(
        unit_type=LearningUnitType.LEMMA,
        key=key,
        display_form=key,
    )
