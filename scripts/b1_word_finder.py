with open('data/b1_unparsed.txt', 'r') as b1_words: 
    b1_words = [word.strip() for word in b1_words.readlines()]

with open('data/final_result.txt', 'r') as top_4000_words: 
    top_4000_words = top_4000_words.readlines()
    d = dict()

    for row in top_4000_words: 
        first, second = row.split('\t')
        second = second.strip()

        if first not in d: 
            d[first] = second

    print(d)
        
print(b1_words)

articles = ['der', 'die', 'das']
result = []

for word in b1_words: 
    if word in d: 
        result.append(d[word])

    else: 
        for article in articles: 
            word_with_article = article + ' ' + word
            if word_with_article in d: 
                result.append(d[word_with_article])

with open('data/b1_parsed.txt', 'w+') as file: 
    for word in result: 
        file.write(word + '\n')

print(len(result))
            