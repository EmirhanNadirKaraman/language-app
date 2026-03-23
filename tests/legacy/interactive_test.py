from phrase_finder import extract_german_logic, find_best_match, load_verb_dictionary, trigram_similarity

def test_sentence(sentence):
    """Test a sentence and show detailed analysis"""
    print(f"\n{'='*70}")
    print(f"Testing: {sentence}")
    print('='*70)

    analysis = extract_german_logic(sentence)

    for item in analysis:
        phrase = ' '.join(item['sentence_phrase'])
        print(f"\n  📝 Phrase: {phrase}")
        print(f"  🔍 Logic:  {item['logic']}")
        print(f"  📖 Dict:   {item['dictionary_entry']}")
        if 'match_type' in item:
            print(f"  ✓ Match:  {item['match_type']}")

def test_word_similarity(word1, word2):
    """Test similarity between two words"""
    similarity = trigram_similarity(word1, word2)
    print(f"\n{word1} ↔ {word2}")
    print(f"Similarity: {similarity:.3f} ({'✓ Good match' if similarity >= 0.6 else '✗ Below threshold'})")

def test_dictionary_lookup(word):
    """Test finding best match in dictionary for a word"""
    verb_map = load_verb_dictionary("final_result.txt")
    match, score = find_best_match(word, verb_map, threshold=0.6)

    print(f"\n🔎 Looking up: '{word}'")
    if match:
        print(f"✓ Found: {match} (score: {score:.3f})")
    else:
        # Try with lower threshold to see what would match
        match_low, score_low = find_best_match(word, verb_map, threshold=0.0)
        print(f"✗ No match above threshold")
        if match_low:
            print(f"  Best candidate: {match_low} (score: {score_low:.3f})")

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  TRIGRAM MATCHING TEST SUITE")
    print("="*70)

    # Test 1: Sentences with exact matches
    print("\n\n1️⃣  SENTENCES WITH EXACT MATCHES")
    test_sentence("Ich gebe dir das Buch")
    test_sentence("Sie nimmt den Apfel")

    # Test 2: Word similarity examples
    print("\n\n2️⃣  WORD SIMILARITY SCORES")
    test_word_similarity("geben", "geben")
    test_word_similarity("geben", "leben")
    test_word_similarity("sprechen", "sprachen")
    test_word_similarity("geben", "nehmen")

    # Test 3: Dictionary lookup with fuzzy matching
    print("\n\n3️⃣  DICTIONARY LOOKUPS")
    test_dictionary_lookup("geben")      # exact match
    test_dictionary_lookup("leben")      # should find similar word
    test_dictionary_lookup("sprechen")   # exact match
    test_dictionary_lookup("spricht")    # conjugated form

    print("\n" + "="*70)
    print("  TEST COMPLETE")
    print("="*70 + "\n")
