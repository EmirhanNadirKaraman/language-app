import spacy

nlp = spacy.load("de_core_news_sm")

sentence = "Ich gebe dir heute das Buch"
doc = nlp(sentence)

print(f"\nSentence: {sentence}\n")
print(f"{'Index':<8} {'Word':<15} {'POS':<10} {'Dep':<15} {'Head':<15} {'Children':<30}")
print("=" * 100)

for token in doc:
    children = [child.text for child in token.children]
    print(f"{token.i:<8} {token.text:<15} {token.pos_:<10} {token.dep_:<15} {token.head.text:<15} {', '.join(children):<30}")

print("\n" + "=" * 100)
print("\nVerb 'gebe' children details:")
print("=" * 100)

for token in doc:
    if token.text == "gebe":
        for child in token.children:
            print(f"\nChild: {child.text} (dep: {child.dep_}, pos: {child.pos_})")
            for grandchild in child.children:
                print(f"  - Grandchild: {grandchild.text} (dep: {grandchild.dep_}, pos: {grandchild.pos_})")
