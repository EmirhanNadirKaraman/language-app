from phrase_finder import extract_german_logic

# Add your own test sentences here:
my_sentences = [
    "Ich gebe dir das Buch",
    "Er spricht mit seinen Freunden",
    # Add more sentences below:

]

print("Testing your sentences:\n")
for sentence in my_sentences:
    print(f"📝 {sentence}")
    print("-" * 60)

    results = extract_german_logic(sentence)

    for item in results:
        phrase = ' '.join(item['sentence_phrase'])
        print(f"  Phrase: {phrase}")
        print(f"  Dict:   {item['dictionary_entry']}")
        if 'match_type' in item:
            print(f"  Match:  {item['match_type']}")
        print()

    print()
