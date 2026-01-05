# write all verbs into file
with open('data/gemini_answer.txt', 'r') as f: 
    with open('data/final_result.txt', 'w+') as write_file:
        lines = f.readlines()

        for line in lines[1:]: 
            if len(line.split(',')) <= 1:
                continue

            first, second = line.split(',')
            first = first.strip()
            second = second.strip()
            
            if second == '---':
                second = ''

            write_file.write(f'{first}\t{second} {first}\n')

# write all non-verb words into file
with open('data/words_4000_old.txt', 'r') as all_words: 
    with open('data/final_result.txt', 'a+') as write_file:
        lines = all_words.readlines()
        for line in lines: 
            parts = [x for x in line.split('\t\t') if x]
            if 'verb' not in parts[1:]:
                write_file.write(f'{parts[0]}\t{parts[0]}\n')
                