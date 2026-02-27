import json

import config
from memory import compression, working_memory


def _seed_default(channel: str, thread_ts: str, idx: int, entry_type: str, **kwargs):
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=kwargs.get("user_id", "U1"),
        entry_type=entry_type,
        content=kwargs.get("content", f"entry-{idx}"),
        metadata=kwargs.get("metadata"),
        display_name=kwargs.get("display_name"),
        verb=kwargs.get("verb"),
        region=kwargs.get("region", "default"),
    )


def test_partition_by_priority_rules():
    entries = [
        {"entry_type": "daimonicIntuition", "content": "intuition", "metadata": None},
        {"entry_type": "onboardingStep", "content": "step", "metadata": None},
        {"entry_type": "memorySummary", "content": "summary", "metadata": None},
        {"entry_type": "decision", "content": "inject model?", "metadata": {"result": True}},
        {"entry_type": "mentalQuery", "content": "state changed?", "metadata": json.dumps({"result": True})},
        {"entry_type": "decision", "content": "inject dossiers?", "metadata": {"result": False}},
        {"entry_type": "userMessage", "content": "hello", "metadata": None},
    ]

    must_preserve, compressible = compression.partition_by_priority(entries)
    preserve_types = [e["entry_type"] for e in must_preserve]
    compress_types = [e["entry_type"] for e in compressible]

    assert preserve_types == [
        "daimonicIntuition",
        "onboardingStep",
        "memorySummary",
        "decision",
        "mentalQuery",
    ]
    assert compress_types == ["decision", "userMessage"]


def test_heuristic_compress_contains_speakers_topics_and_verbatim():
    entries = [
        {"entry_type": "userMessage", "display_name": "Tom", "user_id": "U1", "content": "Can we review deployment logs and failover behavior?"},
        {"entry_type": "decision", "content": "Inject user model?", "metadata": {"result": False}},
        {"entry_type": "daimonicIntuition", "content": "Slow down before merging risky migrations."},
    ]

    summary = compression.heuristic_compress(entries, soul_name="Claudius")

    assert "Memory compression summary for Claudius." in summary
    assert "Speakers: Tom." in summary
    assert "Can we review deployment logs and failover behavior?"[:50] in summary
    assert '"Inject user model?"' in summary
    assert '"Slow down before merging risky migrations."' in summary


def test_llm_compress_uses_llm_client(monkeypatch):
    called = {}

    def fake_call(prompt: str, provider: str = "", model: str = "") -> str:
        called["prompt"] = prompt
        called["provider"] = provider
        called["model"] = model
        return "LLM summary"

    monkeypatch.setattr(compression.llm_client, "call_llm", fake_call)
    result = compression.llm_compress(
        [{"entry_type": "userMessage", "content": "hello", "metadata": None}],
        soul_name="Claudius",
        provider="groq",
        model="m1",
    )

    assert result == "LLM summary"
    assert "You are Claudius" in called["prompt"]
    assert "reflecting on a conversation" in called["prompt"]
    assert called["provider"] == "groq"
    assert called["model"] == "m1"


def test_store_summary_replaces_prior_summary():
    _seed_default("C1", "T1", 1, "memorySummary", content="old summary", region="summary")
    _seed_default("C1", "T1", 2, "userMessage", content="still here")

    compression.store_summary(
        channel="C1",
        thread_ts="T1",
        summary="new summary",
        original_count=12,
        time_range={"start": 1.0, "end": 2.0},
        method="heuristic",
    )

    summary_entries = working_memory.get_region("C1", "T1", "summary", limit=10)
    assert len(summary_entries) == 1
    assert summary_entries[0]["entry_type"] == "memorySummary"
    assert summary_entries[0]["content"] == "new summary"

    meta = json.loads(summary_entries[0]["metadata"])
    assert meta["original_count"] == 12
    assert meta["time_range"]["start"] == 1.0
    assert meta["method"] == "heuristic"

    default_entries = working_memory.get_region("C1", "T1", "default", limit=10)
    assert [e["content"] for e in default_entries] == ["still here"]


def test_archive_and_delete_archives_all_passed(monkeypatch):
    """archive_and_delete archives+deletes ALL entries it receives.

    Keep-recent trimming happens in compress_thread() before calling this.
    """
    monkeypatch.setattr(config, "COMPRESSION_ARCHIVE", True)

    for i in range(5):
        _seed_default("C1", "T1", i, "userMessage", content=f"m{i}")

    entries = working_memory.get_region("C1", "T1", "default", limit=20)
    # Simulate compress_thread's keep-recent trim: pass only first 3
    to_archive = entries[:3]
    deleted = compression.archive_and_delete(
        entries=to_archive,
        channel="C1",
        thread_ts="T1",
        time_range={"start": 0.0, "end": 10.0},
        compression_trace_id="trace123",
    )

    assert deleted == 3
    remaining = working_memory.get_region("C1", "T1", "default", limit=20)
    assert [e["content"] for e in remaining] == ["m3", "m4"]

    conn = working_memory._get_conn()
    count = conn.execute(
        "SELECT COUNT(*) as n FROM working_memory_archive WHERE channel = ? AND thread_ts = ?",
        ("C1", "T1"),
    ).fetchone()["n"]
    assert count == 3


def test_compress_thread_orchestration_heuristic(monkeypatch):
    monkeypatch.setattr(config, "COMPRESSION_THRESHOLD", 5)
    monkeypatch.setattr(config, "COMPRESSION_KEEP_RECENT", 1)
    monkeypatch.setattr(config, "COMPRESSION_USE_LLM", False)
    monkeypatch.setattr(config, "SOUL_NAME", "Claudius")
    monkeypatch.setattr(config, "COMPRESSION_ARCHIVE", True)

    _seed_default("C1", "T1", 1, "userMessage", content="u1", display_name="Tom")
    _seed_default("C1", "T1", 2, "mentalQuery", content="update model?", metadata={"result": False})
    _seed_default("C1", "T1", 3, "decision", content="Inject user model?", metadata={"result": True})
    _seed_default("C1", "T1", 4, "onboardingStep", content="Asked user name.")
    _seed_default("C1", "T1", 5, "userMessage", content="u2", display_name="Tom")
    _seed_default("C1", "T1", 6, "userMessage", content="u3", display_name="Tom")

    result = compression.compress_thread("C1", "T1", trace_id="compress-trace")

    assert result["compressed_count"] == 3
    assert result["method"] == "heuristic"
    assert result["trace_id"] == "compress-trace"

    default_entries = working_memory.get_region("C1", "T1", "default", limit=20)
    assert [e["entry_type"] for e in default_entries] == ["decision", "onboardingStep", "userMessage"]
    assert [e["content"] for e in default_entries] == ["Inject user model?", "Asked user name.", "u3"]

    summary_entries = working_memory.get_region("C1", "T1", "summary", limit=10)
    assert len(summary_entries) == 1
    assert summary_entries[0]["entry_type"] == "memorySummary"

    meta = json.loads(summary_entries[0]["metadata"])
    assert meta["original_count"] == 3
    assert meta["method"] == "heuristic"


def test_compress_thread_threshold_not_met(monkeypatch):
    monkeypatch.setattr(config, "COMPRESSION_THRESHOLD", 3)
    _seed_default("C1", "T1", 1, "userMessage", content="a")
    _seed_default("C1", "T1", 2, "userMessage", content="b")

    result = compression.compress_thread("C1", "T1")

    assert result["compressed_count"] == 0
    assert result["reason"] == "threshold_not_met"
