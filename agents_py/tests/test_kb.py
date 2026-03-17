from f1_agents_service.kb import JsonlKnowledgeBase


def test_kb_add_and_search(tmp_path):
    kb = JsonlKnowledgeBase(str(tmp_path / "kb.jsonl"))
    kb.add(namespace="f1", text="Ferrari uses Ferrari power unit", metadata={"team": "Ferrari"})
    kb.add(namespace="f1", text="Red Bull uses Red Bull/Ford power unit", metadata={"team": "Red Bull"})

    hits = kb.search("Ferrari", namespace="f1")
    assert len(hits) == 1
    assert "Ferrari" in hits[0].text
