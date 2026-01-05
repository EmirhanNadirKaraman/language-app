from phrase_finder import extract_german_logic

# Test sentences with various verbs
test_sentences = [
    "Ich gebe dir das Buch",
    "Er spricht mit seinen Freunden",
    "Sie nimmt den Apfel",
    "Wir verstehen die Aufgabe",
    "Sie setzt sich auf den Stuhl",
]

print("\n" + "="*80)
print("VERB MATCHING TEST")
print("="*80)

for sentence in test_sentences:
    print(f"\n📝 Sentence: {sentence}")
    print("-" * 80)

    results = extract_german_logic(sentence)

    for item in results:
        phrase = ' '.join(item['sentence_phrase'])
        logic = item['logic']

        # Only show verbs
        if '->' in logic or logic == 'VERB':
            print(f"  Verb Phrase: {phrase:25}")
            print(f"  Logic:       {logic:25}")
            print(f"  Dictionary:  {item['dictionary_entry']:25}")
            print(f"  Match Type:  {item['match_type']}")
            print()

print("\n" + "="*80)
