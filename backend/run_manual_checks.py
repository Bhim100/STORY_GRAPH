import urllib.request
import json

def ask(question: str, chapter: int):
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/ask",
        data=json.dumps({"question": question, "chapter": chapter}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=" * 70)
print("1. 'What happened at the greenhouse?' (Chapter 1)")
print("=" * 70)
r1 = ask("What happened at the greenhouse?", 1)
print(f"Status: {r1.get('status')}")
print(f"Question Type: {r1.get('question_type')}")
print(f"Events count: {len(r1.get('events', []))}")
print(f"Answer:\n{r1.get('answer')}\n")

print("=" * 70)
print("2. 'What happened at the greenhouse?' (Chapter 2)")
print("=" * 70)
r2 = ask("What happened at the greenhouse?", 2)
print(f"Status: {r2.get('status')}")
print(f"Question Type: {r2.get('question_type')}")
print(f"Events: {[e.get('title') for e in r2.get('events', [])]}")
print(f"Evidence Excerpts: {[e.get('excerpt') for e in r2.get('evidence', [])]}")
print(f"Answer:\n{r2.get('answer')}\n")

print("=" * 70)
print("3. 'Why was Jonas suspected?' (Chapter 1)")
print("=" * 70)
r3 = ask("Why was Jonas suspected?", 1)
print(f"Status: {r3.get('status')}")
print(f"Question Type: {r3.get('question_type')}")
print(f"Claims: {[c.get('text') for c in r3.get('claims', [])]}")
print(f"Validation: {[c.get('validation') for c in r3.get('claims', [])]}")
print(f"Evidence: {[e.get('excerpt') for e in r3.get('evidence', [])]}")
print(f"Answer:\n{r3.get('answer')}\n")

print("=" * 70)
print("4a. 'What evidence implicates Halden?' (Chapter 4)")
print("=" * 70)
r4a = ask("What evidence implicates Halden?", 4)
print(f"Status: {r4a.get('status')}")
print(f"Question Type: {r4a.get('question_type')}")
print(f"Evidence count: {len(r4a.get('evidence', []))}")
print(f"Answer:\n{r4a.get('answer')}\n")

print("=" * 70)
print("4b. 'What evidence implicates Halden?' (Chapter 7)")
print("=" * 70)
r4b = ask("What evidence implicates Halden?", 7)
print(f"Status: {r4b.get('status')}")
print(f"Question Type: {r4b.get('question_type')}")
print(f"Evidence: {[e.get('excerpt') for e in r4b.get('evidence', [])]}")
print(f"Claims: {[c.get('text') for c in r4b.get('claims', [])]}")
print(f"Answer:\n{r4b.get('answer')}\n")
