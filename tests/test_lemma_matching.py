from phrase_finder import extract_german_logic

# Test sentences with various forms
test_sentences = [
    "Ich lade morgen meine Freunde zum Essen ein",
    "Er gibt mir das Buch",
    "Sie nimmt den Apfel",
    "Wir sprechen über das Wetter",
]

print("=== Lemma-based Trigram Matching Test ===\n")

for sentence in test_sentences:
    print(f"Sentence: {sentence}")
    print("-" * 60)

    analysis = extract_german_logic(sentence)

    for item in analysis:
        phrase = ' '.join(item['sentence_phrase'])
        print(f"  Phrase: {phrase:20} | Logic: {item['logic']:20}")
        print(f"  Dict:   {item['dictionary_entry']}")
        if 'match_type' in item:
            print(f"  Match:  {item['match_type']}")
        print()

    print()
