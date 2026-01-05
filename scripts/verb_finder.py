with open('words_4000_old.txt', 'r', encoding='utf-8') as f: 
    lines = f.readlines()
    verb_set = set()
    verbs = list()

    for line in lines: 
        parts = line.strip().split('\t')
        for part in parts:
            if part.strip() == 'verb':
                if parts[0] not in verb_set:
                    verb_set.add(parts[0])
                    verbs.append(parts[0])

    with open('verbs.txt', 'w+') as verb_file:
        for verb in verbs: 
            verb_file.write(verb + '\n')
