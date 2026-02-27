"""Tests focused on working-memory region behavior."""

from memory import working_memory


class TestMemoryRegions:
    def test_region_column_defaults_to_default(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "hello")

        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["region"] == "default"

    def test_get_region_filters(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "default-msg", region="default")
        working_memory.add("C1", "T1", "U1", "memorySummary", "summary-msg", region="summary")

        default_entries = working_memory.get_region("C1", "T1", "default")
        summary_entries = working_memory.get_region("C1", "T1", "summary")

        assert [entry["content"] for entry in default_entries] == ["default-msg"]
        assert [entry["content"] for entry in summary_entries] == ["summary-msg"]

    def test_get_region_names(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "a", region="default")
        working_memory.add("C1", "T1", "U1", "userMessage", "b", region="summary")
        working_memory.add("C1", "T1", "U1", "userMessage", "c", region="state")

        region_names = set(working_memory.get_region_names("C1", "T1"))
        assert region_names == {"default", "summary", "state"}

    def test_format_with_region_order(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "summary-first", region="summary")
        working_memory.add("C1", "T1", "U1", "userMessage", "default-second", region="default")

        entries = working_memory.get_recent("C1", "T1", exclude_regions=[])
        rendered = working_memory.format_for_prompt(entries, region_order=["default", "summary"])

        assert rendered.splitlines() == [
            'User said: "default-second"',
            'User said: "summary-first"',
        ]

    def test_get_recent_excludes_summary_by_default(self):
        working_memory.add("C1", "T1", "U1", "memorySummary", "summary-msg", region="summary")

        entries = working_memory.get_recent("C1", "T1")
        assert entries == []

    def test_get_recent_includes_all_when_empty_list(self):
        working_memory.add("C1", "T1", "U1", "memorySummary", "summary-msg", region="summary")
        working_memory.add("C1", "T1", "U1", "userMessage", "default-msg", region="default")

        entries = working_memory.get_recent("C1", "T1", exclude_regions=[])
        assert [entry["content"] for entry in entries] == ["summary-msg", "default-msg"]

    def test_skills_gate_not_contaminated(self):
        working_memory.add("C1", "fresh-thread", "U1", "memorySummary", "summary-only", region="summary")

        entries = working_memory.get_recent("C1", "fresh-thread", limit=1)
        assert entries == []

    def test_add_with_explicit_region(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "custom-region-entry", region="custom")

        custom_entries = working_memory.get_region("C1", "T1", "custom")
        assert len(custom_entries) == 1
        assert custom_entries[0]["content"] == "custom-region-entry"
        assert custom_entries[0]["region"] == "custom"
