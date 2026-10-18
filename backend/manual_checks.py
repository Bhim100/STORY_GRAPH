import json
import urllib.request

CHECKS = [
    {
        "num": 1,
        "title": "Check 1: Entity profile for Mara Voss at Chapter 1",
        "question": "Tell me about Mara Voss",
        "chapter": 1
    },
    {
        "num": 2,
        "title": "Check 2: Collection query for Thorne household at Chapter 1",
        "question": "Who is in the Thorne household?",
        "chapter": 1
    },
    {
        "num": 3,
        "title": "Check 3: Manor residence query vs household distinction",
        "question": "Who lives at Thorne Manor?",
        "chapter": 1
    },
    {
        "num": 4,
        "title": "Check 4: Entity profile for Dr. Halden at Chapter 1 (zero culprit leaks)",
        "question": "Describe Dr. Halden",
        "chapter": 1
    }
]

def run_checks():
    for c in CHECKS:
        print(f"\n=======================================================")
        print(f"=== {c['title']} ===")
        print(f"Question: \"{c['question']}\" (Chapter: {c['chapter']})")
        
        payload = json.dumps({"question": c["question"], "chapter": c["chapter"]}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/ask",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"HTTP Status: {resp.status}")
                print(f"Status Field: {data.get('status')}")
                print(f"Question Type: {data.get('question_type')}")
                print(f"Answer:\n{data.get('answer')}")
                if data.get("members"):
                    print(f"\nMembers ({len(data['members'])}):")
                    for m in data["members"]:
                        print(f"  - {m['name']} ({m.get('role', '')}): {m.get('relationship')} (Claim: {m.get('claim_id')})")
                if data.get("relationships"):
                    print(f"\nRelationships ({len(data['relationships'])}):")
                    for r in data["relationships"]:
                        if isinstance(r, dict):
                            print(f"  - {r.get('source', r.get('target_name'))} -> {r.get('relationship', r.get('type'))} (Claim: {r.get('claim_id')})")
                if data.get("evidence"):
                    print(f"\nEvidence ({len(data['evidence'])} items):")
                    for ev in data["evidence"]:
                        print(f"  - [{ev.get('evidence_id')}] ({ev.get('kind')}, src ch {ev.get('source_chapter')}, rev ch {ev.get('reveal_chapter')}): \"{ev.get('excerpt')}\"")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_checks()
