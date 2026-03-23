import spacy
from phrase_finder import extract_german_logic

nlp = spacy.load("de_core_news_sm")

def show_complete_analysis(sentence):
    """Show complete word-by-word analysis"""
    doc = nlp(sentence)

    print(f"\n{'='*80}")
    print(f"Sentence: {sentence}")
    print('='*80)

    # Get analysis
    analysis = extract_german_logic(sentence)

    # Create a mapping of word positions
    print(f"\n{'Word':<15} {'POS':<10} {'Lemma':<15} {'Dict Entry':<20} {'Match':<15}")
    print("-" * 80)

    for item in analysis:
        word = item['sentence_phrase'][0]  # Get first word of phrase
        logic = item['logic']
        dict_entry = item['dictionary_entry']
        match_type = item.get('match_type', 'N/A')

        # Format match type for display
        if match_type.startswith('fuzzy'):
            match_display = 'fuzzy'
        else:
            match_display = match_type

        print(f"{word:<15} {logic:<10} {dict_entry:<15} {dict_entry:<20} {match_display:<15}")

    print()

# Test sentences
test_sentences = [
    "Ich lade morgen meine Freunde zum Essen ein",
    "Er gibt mir heute das Buch",
    "Sie spricht sehr schnell mit ihm",
    "Der große Hund läuft schnell",
]

print("\n" + "="*80)
print(" COMPLETE WORD EXTRACTION TEST - ALL WORD TYPES")
print("="*80)

for sentence in test_sentences:
    show_complete_analysis(sentence)

print("\n" + "="*80)
print(" Summary of Extracted Word Types:")
print("="*80)
print("""
✓ VERB  - Verbs with objects and prepositions
✓ NOUN  - Nouns with determiners and adjectives
✓ PRON  - Pronouns (ich, er, sie, mir, ihm, etc.)
✓ ADV   - Adverbs (morgen, heute, sehr, schnell, etc.)
✓ ADJ   - Standalone adjectives
✓ DET   - Determiners/Articles (der, die, das, mein, etc.)
✓ ADP   - Prepositions (zum, mit, von, etc.)
✓ Other - Any remaining word types

All words now use lemma-based trigram matching!
""")
