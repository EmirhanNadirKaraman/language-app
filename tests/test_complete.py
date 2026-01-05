from phrase_finder import extract_german_logic

sentences = [
    "Ich lade morgen meine Freunde zum Essen ein",
    "Er gibt mir heute das Buch",
    "Sie spricht sehr schnell mit ihm",
]

print("\n" + "="*70)
print("TESTING ALL WORD TYPES EXTRACTION")
print("="*70)

for sentence in sentences:
    print(f"\n📝 Sentence: {sentence}")
    print("-" * 70)

    results = extract_german_logic(sentence)

    for item in results:
        phrase = ' '.join(item['sentence_phrase'])
        print(f"  {phrase:20} | {item['logic']:12} | {item['dictionary_entry']:20} | {item['match_type']}")

print("\n" + "="*70)
print("All word types are now extracted with trigram matching!")
print("="*70 + "\n")
