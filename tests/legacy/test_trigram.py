import spacy
from phrase_finder import generate_trigrams, trigram_similarity, find_best_match, load_verb_dictionary

# Test trigram generation
print("=== Trigram Generation Test ===")
test_word = "geben"
trigrams = generate_trigrams(test_word)
print(f"Word: {test_word}")
print(f"Trigrams: {sorted(trigrams)}")
print()

# Test similarity calculation
print("=== Trigram Similarity Test ===")
word_pairs = [
    ("geben", "geben"),      # identical
    ("geben", "gaben"),      # similar
    ("geben", "leben"),      # somewhat similar
    ("geben", "nehmen"),     # different
    ("einladen", "einladen"), # identical
    ("einladen", "einladen"), # identical with typo simulation
    ("sprechen", "sprachen"), # conjugation variation
]

for word1, word2 in word_pairs:
    similarity = trigram_similarity(word1, word2)
    print(f"{word1:15} vs {word2:15} => {similarity:.3f}")
print()

# Test best match finding
print("=== Best Match Test ===")
verb_map = load_verb_dictionary("final_result.txt")

test_verbs = ["geben", "nehmen", "sprechen", "einladen", "gaben", "gibst", "spricht"]
for verb in test_verbs:
    # Try with default threshold
    match, score = find_best_match(verb, verb_map, threshold=0.6)
    if match:
        print(f"Query: {verb:15} => Match: {match:30} (score: {score:.3f})")
    else:
        # Try with lower threshold to see what the best match would be
        match_low, score_low = find_best_match(verb, verb_map, threshold=0.0)
        if match_low:
            print(f"Query: {verb:15} => Best match: {match_low:25} (score: {score_low:.3f}) [below threshold]")
        else:
            print(f"Query: {verb:15} => No match found")
