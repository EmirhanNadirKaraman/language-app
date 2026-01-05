import spacy
import csv
import os

# Load German model
nlp = spacy.load("de_core_news_sm")

def load_verb_dictionary(file_path):
    """
    Loads the CSV dictionary where:
    Key: base verb (e.g., 'geben' or 'einladen')
    Value: The full blueprint (e.g., 'geben jdm. etw.')

    When duplicate keys exist, keeps the longer/more detailed value.
    """

    word_map = dict()

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f.readlines():
            key, value = line.split('\t')
            value = value.strip()  # Remove trailing newlines

            # If key already exists, keep the longer value (more detailed pattern)
            if key in word_map:
                if len(value) > len(word_map[key]):
                    word_map[key] = value
            else:
                word_map[key] = value

    return word_map


verb_blueprint_map = load_verb_dictionary("data/final_result.txt")

def generate_trigrams(word):
    """
    Generate trigrams from a word.
    Adds padding at the beginning and end to capture edge trigrams.
    """
    if len(word) < 3:
        return set([word])

    padded_word = f"  {word}  "
    trigrams = set()
    for i in range(len(padded_word) - 2):
        trigrams.add(padded_word[i:i+3])
    return trigrams

def trigram_similarity(word1, word2):
    """
    Calculate similarity between two words using trigram overlap (Dice coefficient).
    Returns a value between 0 and 1, where 1 is identical.
    """
    trigrams1 = generate_trigrams(word1.lower())
    trigrams2 = generate_trigrams(word2.lower())

    if not trigrams1 or not trigrams2:
        return 0.0

    intersection = len(trigrams1 & trigrams2)
    dice = (2.0 * intersection) / (len(trigrams1) + len(trigrams2))
    return dice

def find_best_match(target_word, dictionary_map, threshold=0.6):
    """
    Find the best matching word from the dictionary using trigram similarity.
    Returns (best_match, similarity_score) or (None, 0.0) if no match above threshold.
    """
    # Common German articles to skip
    articles = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'einer', 'eines'}

    best_match = None
    best_score = 0.0

    for dict_word in dictionary_map.keys():
        # Extract the main word, skipping articles
        words = dict_word.split()
        if len(words) > 1:
            # Skip the first word if it's an article
            base_word = words[1] if words[0].lower() in articles else words[0]
        else:
            base_word = dict_word

        score = trigram_similarity(target_word, base_word)
        if score > best_score:
            best_score = score
            best_match = dict_word

    if best_score >= threshold:
        return best_match, best_score
    return None, 0.0

def get_object_token(child):
    """Maps spaCy dependency labels to jdn./jdm./etw. tokens."""
    # Check if person vs thing
    is_person = child.pos_ in ["PRON", "PROPN"] or child.ent_type_ == "PER"
    
    # da = dative object, oa = accusative object
    if child.dep_ == "da":
        return "jdm." if is_person else "etw."
    if child.dep_ in ["oa", "obj"]:
        return "jdn." if is_person else "etw."
    return "etw."

def extract_german_logic(text):
    doc = nlp(text)
    result = []
    consumed = set()

    for token in doc:
        # if token.i in consumed:
        #     continue

        # --- VERB MAPPING LOGIC ---
        if token.pos_ in ["VERB", "AUX"] and token.dep_ != "aux":
            indices = [token.i]
            verb_lemma = token.lemma_.lower()
            
            # Handle Separable Prefixes (e.g., 'ein' in 'einladen')
            prefix = ""
            for child in token.children:
                if child.dep_ == "svp":
                    prefix = child.lemma_.lower()
                    indices.append(child.i)
                    consumed.add(child.i)
            
            full_verb = prefix + verb_lemma if prefix else verb_lemma
            
            # Build the "Live" Blueprint from the sentence
            components = [full_verb]
            for child in token.children:
                # Detect reflexive (sich)
                if child.dep_ == "expl:pv" or (child.lemma_.lower() == "sich"):
                    components.append("sich")
                    indices.append(child.i)
                    consumed.add(child.i)
                
                # Detect Objects (jdn/jdm/etw)
                if child.dep_ in ["oa", "da", "obj"]:
                    components.append(get_object_token(child))
                    indices.append(child.i)
                    consumed.add(child.i)

                    # Also include articles and modifiers of the object
                    for grandchild in child.children:
                        if grandchild.dep_ in ["det", "poss", "amod", "nk"]:
                            indices.append(grandchild.i)
                            consumed.add(grandchild.i)
                
                # Detect Prepositions
                if child.pos_ == "ADP":
                    prep = child.lemma_.lower()
                    indices.append(child.i)
                    consumed.add(child.i)
                    # Find the noun inside the prep phrase
                    obj_in_prep = "etw."
                    for grand in child.children:
                        if grand.dep_ in ["nk", "pobj"]:
                            indices.append(grand.i)
                            consumed.add(grand.i)
                            if grand.pos_ in ["PRON", "PROPN"]:
                                obj_in_prep = "jdm."

                            # Also include articles and modifiers of the prepositional object
                            for great_grand in grand.children:
                                if great_grand.dep_ in ["det", "poss", "amod", "nk"]:
                                    indices.append(great_grand.i)
                                    consumed.add(great_grand.i)
                    components.append(f"{prep} {obj_in_prep}")

            # Dictionary Lookup with Trigram Matching
            # First try exact match
            blueprint = verb_blueprint_map.get(full_verb)
            match_info = "exact"

            # If not found, try trigram similarity matching
            if blueprint is None:
                best_match, similarity = find_best_match(full_verb, verb_blueprint_map)
                if best_match:
                    blueprint = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    blueprint = " ".join(components)
                    match_info = "constructed"

            indices.sort()
            result.append({
                "dictionary_entry": blueprint,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": " -> ".join(components),
                "match_type": match_info,
                "indices": indices
            })

        # --- NOUN/OTHER COLLECTION ---
        elif token.pos_ == "NOUN":
            indices = [token.i]
            noun_lemma = token.lemma_.lower()

            for child in token.children:
                if child.dep_ in ["det", "poss", "amod", "nk"]:
                    indices.append(child.i)
                    consumed.add(child.i)

            # Dictionary Lookup with Trigram Matching for Nouns
            # First try exact match (without article)
            dictionary_entry = verb_blueprint_map.get(noun_lemma)
            match_info = "exact"

            # If not found, try with common articles
            if dictionary_entry is None:
                for article in ['der', 'die', 'das']:
                    article_form = f"{article} {noun_lemma}"
                    if article_form in verb_blueprint_map:
                        dictionary_entry = verb_blueprint_map[article_form]
                        match_info = "exact (with article)"
                        break

            # If still not found, try trigram similarity matching
            if dictionary_entry is None:
                best_match, similarity = find_best_match(noun_lemma, verb_blueprint_map)
                if best_match:
                    dictionary_entry = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    dictionary_entry = noun_lemma
                    match_info = "lemma"

            indices.sort()
            result.append({
                "dictionary_entry": dictionary_entry,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": "NOUN",
                "match_type": match_info,
                "indices": indices
            })

        # --- PRONOUN COLLECTION ---
        elif token.pos_ == "PRON":
            indices = [token.i]
            pronoun_lemma = token.lemma_.lower()

            # Dictionary Lookup with Trigram Matching for Pronouns
            dictionary_entry = verb_blueprint_map.get(pronoun_lemma)
            match_info = "exact"

            if dictionary_entry is None:
                best_match, similarity = find_best_match(pronoun_lemma, verb_blueprint_map)
                if best_match:
                    dictionary_entry = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    dictionary_entry = pronoun_lemma
                    match_info = "lemma"

            result.append({
                "dictionary_entry": dictionary_entry,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": "PRON",
                "match_type": match_info,
                "indices": indices
            })

        # --- ADVERB COLLECTION ---
        elif token.pos_ == "ADV":
            indices = [token.i]
            adverb_lemma = token.lemma_.lower()

            # Dictionary Lookup with Trigram Matching for Adverbs
            dictionary_entry = verb_blueprint_map.get(adverb_lemma)
            match_info = "exact"

            if dictionary_entry is None:
                best_match, similarity = find_best_match(adverb_lemma, verb_blueprint_map)
                if best_match:
                    dictionary_entry = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    dictionary_entry = adverb_lemma
                    match_info = "lemma"

            result.append({
                "dictionary_entry": dictionary_entry,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": "ADV",
                "match_type": match_info,
                "indices": indices
            })

        # --- ADJECTIVE COLLECTION ---
        elif token.pos_ == "ADJ":
            indices = [token.i]
            adj_lemma = token.lemma_.lower()

            # Dictionary Lookup with Trigram Matching for Adjectives
            dictionary_entry = verb_blueprint_map.get(adj_lemma)
            match_info = "exact"

            if dictionary_entry is None:
                best_match, similarity = find_best_match(adj_lemma, verb_blueprint_map)
                if best_match:
                    dictionary_entry = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    dictionary_entry = adj_lemma
                    match_info = "lemma"

            result.append({
                "dictionary_entry": dictionary_entry,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": "ADJ",
                "match_type": match_info,
                "indices": indices
            })

        # --- CATCH-ALL FOR OTHER WORD TYPES ---
        else:
            # Skip punctuation and whitespace
            if token.pos_ in ["PUNCT", "SPACE"]:
                continue

            indices = [token.i]
            word_lemma = token.lemma_.lower()

            # Dictionary Lookup with Trigram Matching
            dictionary_entry = verb_blueprint_map.get(word_lemma)
            match_info = "exact"

            if dictionary_entry is None:
                best_match, similarity = find_best_match(word_lemma, verb_blueprint_map)
                if best_match:
                    dictionary_entry = verb_blueprint_map[best_match]
                    match_info = f"fuzzy ({similarity:.2f}): {best_match}"
                else:
                    dictionary_entry = word_lemma
                    match_info = "lemma"

            result.append({
                "dictionary_entry": dictionary_entry,
                "sentence_phrase": [doc[i].text for i in indices],
                "logic": token.pos_,
                "match_type": match_info,
                "indices": indices
            })

    return result

def get_words_array(text):
    """
    Extract words from text and return as a simple array.
    Returns list of dictionary entries (lemmas).
    """
    analysis = extract_german_logic(text)
    return [item['dictionary_entry'] for item in analysis]

def get_words_detailed_array(text):
    """
    Extract words from text and return as an array with details.
    Returns list of [word, lemma, pos_type, indices] tuples.
    """
    analysis = extract_german_logic(text)
    words_array = []
    for item in analysis:
        word = ' '.join(item['sentence_phrase'])
        lemma = item['dictionary_entry']
        pos = item['logic']
        indices = item['indices']
        words_array.append([word, lemma, pos, indices])
    return words_array


def main():
    # --- TEST ---
    sentence = "Ich lade morgen meine Freunde zum Essen ein"

    # Simple array output
    print("SIMPLE ARRAY:")
    words = get_words_array(sentence)
    print(words)
    print()

    # Detailed array output
    print("DETAILED ARRAY:")
    words_detailed = get_words_detailed_array(sentence)
    for word, lemma, pos, indices in words_detailed:
        print(f"['{word}', '{lemma}', '{pos}', {indices}]")
    print()

    # Full analysis (original)
    print("FULL ANALYSIS:")
    analysis = extract_german_logic(sentence)
    for item in analysis:
        print(f"Phrase:  {' '.join(item['sentence_phrase'])}")
        print(f"Logic:   {item['logic']}")
        print(f"Dict:    {item['dictionary_entry']}")
        print(f"Indices: {item['indices']}")
        if 'match_type' in item:
            print(f"Match:   {item['match_type']}")
        print()


if __name__ == '__main__': 
    main()
