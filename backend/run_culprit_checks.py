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

chapters = [1, 4, 5, 7]

print("=" * 80)
print("MANUAL CHECKS: 'Who killed Elias Thorne?' at Chapters 1, 4, 5, and 7")
print("=" * 80)

for ch in chapters:
    print(f"\n>>> QUERY AT CHAPTER {ch}: 'Who killed Elias Thorne?'")
    res = ask("Who killed Elias Thorne?", ch)
    print(f"Status: {res.get('status')}")
    print(f"Culprit Status: {res.get('culprit_status')}")
    print(f"Culprit: {res.get('culprit')}")
    print(f"Path Returned: {res.get('path') is not None}")
    if res.get("path"):
        print(f"Path Nodes: {[n['name'] for n in res['path']['nodes']]}")
        print(f"Path Relationships: {[r['type'] for r in res['path']['relationships']]}")
    print(f"Cited Claims ({len(res.get('claims', []))}):")
    for cl in res.get("claims", []):
        print(f"  - [{cl.get('id')}] ({cl.get('validation')}): {cl.get('text')}")
    print(f"Cited Evidence ({len(res.get('evidence', []))}):")
    for ev in res.get("evidence", []):
        print(f"  - [{ev.get('evidence_id')}] (Kind: {ev.get('kind')}, Src Ch: {ev.get('source_chapter')}, Rev Ch: {ev.get('reveal_chapter')}): \"{ev.get('excerpt')}\"")
    print("\nFormatted Answer:")
    print("-" * 50)
    print(res.get("answer"))
    print("-" * 50)
