from phrase_finder import extract_german_logic, get_words_detailed_array

sentence = "Ich gebe dir heute das Buch"

print(f"\n{'='*80}")
print(f"Sentence: {sentence}")
print(f"{'='*80}\n")

# Show original sentence with indices
words = sentence.split()
print("Word positions:")
for i, word in enumerate(words):
    print(f"  [{i}] {word}")

print(f"\n{'='*80}")
print("Extracted words with indices:")
print(f"{'='*80}\n")

# Show extracted analysis with indices
analysis = extract_german_logic(sentence)

for item in analysis:
    phrase = ' '.join(item['sentence_phrase'])
    indices = item['indices']
    lemma = item['dictionary_entry']
    pos = item['logic']

    print(f"Phrase:  {phrase:25}")
    print(f"Indices: {indices}")
    print(f"Type:    {pos:25}")
    print(f"Dict:    {lemma}")
    print()

print(f"{'='*80}")
print("Array format [word, lemma, pos, indices]:")
print(f"{'='*80}\n")

words_array = get_words_detailed_array(sentence)
for item in words_array:
    print(item)
