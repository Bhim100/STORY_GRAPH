"""Manual verification script for natural-language investigation queries.

Checks:
1. Exact question: "Who is investigating the case?" at Chapter 1 for Silver Blaze.
2. Confirms result is 'collection_query' and NOT 'unresolved_entity'.
3. Confirms Inspector Gregory (Police Detective Inspector) and Sherlock Holmes (Consulting Detective)
   are identified with their respective roles and source evidence.
4. Checks Chapter 2 to confirm expanded investigation evidence.
5. Checks Glass Orchard to confirm reusable, unhardcoded handling across different books.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import current_graph_name
from app.llm.agent import answer_question
from app.llm.router import route_question


def run_check():
    print("=" * 80)
    print("MANUAL CHECK: Natural-Language Question Routing: 'Who is investigating the case?'")
    print("=" * 80)

    # 1. Routing classification check
    print("\n[Step 1] Routing Classification Check:")
    route = route_question("Who is investigating the case?", chapter=1)
    print(f"  Question Type: {route.get('question_type')}")
    print(f"  Status: {route.get('status')}")
    print(f"  Unresolved Entities: {route.get('unresolved_entities')}")
    assert route.get("question_type") == "collection_query", "Expected collection_query"
    assert route.get("status") == "ok", "Expected status ok"
    assert "investigating the case" not in route.get("unresolved_entities", []), "Must not be entity lookup"
    print("  -> PASSED: Query is classified as a role/collection query, not entity lookup.")

    # 2. Silver Blaze Chapter 1 check
    print("\n[Step 2] Silver Blaze (Chapter 1) Investigation Query:")
    current_graph_name.set("story_i_silver_blaze")
    res_ch1 = answer_question("Who is investigating the case?", chapter=1)
    status_ch1 = res_ch1.get("status")
    print(f"  Response Status: {status_ch1}")
    assert status_ch1 != "unresolved_entity", "Must NOT return 'unresolved_entity'!"
    assert status_ch1 == "collection_query", f"Expected 'collection_query', got {status_ch1}"

    nodes_ch1 = res_ch1.get("nodes", [])
    names_ch1 = [n["name"] for n in nodes_ch1]
    print(f"  Identified Investigators ({len(nodes_ch1)}):")
    for n in nodes_ch1:
        print(f"    - {n['name']} (Role: {n.get('role')})")

    assert "Inspector Gregory" in names_ch1, "Inspector Gregory must be named!"
    assert "Sherlock Holmes" in names_ch1, "Sherlock Holmes must be named!"

    gregory = next(n for n in nodes_ch1 if n["name"] == "Inspector Gregory")
    assert "Inspector" in gregory.get("role", ""), "Inspector Gregory role must reflect police inspector"

    holmes = next(n for n in nodes_ch1 if n["name"] == "Sherlock Holmes")
    assert "Detective" in holmes.get("role", ""), "Sherlock Holmes role must reflect detective"

    print(f"\n  Supporting Evidence Excerpts ({len(res_ch1.get('evidence', []))}):")
    for ev in res_ch1.get("evidence", []):
        print(f"    - [Ch. {ev.get('source_chapter')} {ev.get('kind')}]: \"{ev.get('excerpt')}\"")

    print("\n  Full Answer Output:")
    print("  " + "-" * 60)
    for line in res_ch1.get("answer", "").split("\n"):
        print("  " + line)
    print("  " + "-" * 60)

    # 3. Silver Blaze Chapter 2 progression check
    print("\n[Step 3] Silver Blaze (Chapter 2) Progression Check:")
    res_ch2 = answer_question("Who is investigating the case?", chapter=2)
    ev_ch2 = res_ch2.get("evidence", [])
    print(f"  Total Evidence in Chapter 2: {len(ev_ch2)} items (expanded from Chapter 1's {len(res_ch1.get('evidence', []))})")
    assert len(ev_ch2) >= len(res_ch1.get("evidence", [])), "Chapter 2 should retain or expand evidence"

    # 4. Cross-book check on Glass Orchard
    print("\n[Step 4] Cross-Book Check on 'glass_orchard' (Zero Hardcoding):")
    current_graph_name.set("glass_orchard")
    res_go = answer_question("Who is investigating the case?", chapter=1)
    print(f"  Response Status: {res_go.get('status')}")
    print(f"  Identified Investigators: {[n['name'] for n in res_go.get('nodes', [])]}")
    print(f"  Answer: {res_go.get('answer')[:120]}...")
    assert res_go.get("status") != "unresolved_entity"
    assert len(res_go.get("nodes", [])) == 0, "Glass Orchard should have 0 investigators at Chapter 1"
    print("  -> PASSED: Generic graph-driven logic returns zero investigators for stories without detective roles.")

    print("\n" + "=" * 80)
    print("ALL CHECKS PASSED: 'Who is investigating the case?' correctly resolved!")
    print("=" * 80)


if __name__ == "__main__":
    run_check()
