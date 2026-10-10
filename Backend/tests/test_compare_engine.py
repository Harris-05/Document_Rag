import asyncio
import json
import re
import time
from collections.abc import Callable

import pytest

from app.compare import prompts
from app.compare.engine import compare_documents
from app.config import get_settings
from app.rag.llm import LLMError

from .fakes import FakeLLM

OLD = """1. Services

The Supplier shall provide the consulting services described in Schedule 1.

2. Payment

The Customer shall pay each undisputed invoice within thirty (30) days of receiving a valid invoice.

3. Termination

Either party may terminate this Agreement for convenience by giving ninety (90) days written notice to the other party.

4. Limitation of Liability

The Supplier's aggregate liability under this Agreement shall not exceed AED 100,000 in any contract year.

5. Confidentiality

Each party shall keep the other party's Confidential Information secret and use it only to perform this Agreement.

6. Governing Law

This Agreement is governed by the laws of England and Wales."""

NEW = """1. Services

The Supplier shall provide the consulting services that are described in Schedule 1.

2. Payment

The Customer shall pay each undisputed invoice within thirty (30) days of receiving a valid invoice.

3. Termination

Either party may terminate this Agreement for convenience by giving sixty (60) days written notice to the other party.

4. Limitation of Liability

The Supplier's aggregate liability under this Agreement shall not exceed AED 1,000,000 in any contract year.

7. Data Protection

Each party shall comply with all applicable data protection laws when processing personal data under this Agreement.

8. Governing Law

This Agreement is governed by the laws of England and Wales."""


def pages(text: str) -> list[tuple[int, str]]:
    return [(1, text)]


def run(old=OLD, new=NEW, llm=None, **overrides):
    settings = get_settings().model_copy(update=overrides)
    events: list[tuple[str, int, int | None]] = []
    result = asyncio.run(
        compare_documents(pages(old), pages(new), llm, settings, lambda stage, done, total: events.append((stage, done, total)))
    )
    return result, events


def by_title(result, fragment: str) -> dict:
    def haystack(change: dict) -> str:
        side = change["new"] or change["old"]
        return " ".join([change["title"], side["heading"], side["text"]]).lower()

    return next(c for c in result["changes"] if fragment.lower() in haystack(c))


def items_in(prompt: str) -> list[tuple[int, str, str]]:
    return [(int(i), kind, body) for i, kind, body in re.findall(r"\[item (\d+)\] change type: (\w+)\n(.*?)(?=\n\n\[item |\Z)", prompt, re.S)]


def scripted(decide: Callable[[str, str], tuple[str, str, str, str]], overview: dict | None = None) -> FakeLLM:
    """A model that rates each item with `decide(change_type, text) -> (significance, category, title, summary)`."""

    def handle(system: str, user: str) -> dict:
        if system == prompts.RATE_SYSTEM:
            rated = []
            for number, kind, body in items_in(user):
                significance, category, title, summary = decide(kind, body)
                rated.append({"id": number, "significance": significance, "category": category, "title": title, "summary": summary})
            return {"items": rated}
        return overview if overview is not None else {"headline": "Two clauses changed in substance.", "key_points": ["The liability cap rose."]}

    return FakeLLM(json_handler=handle)


def sensible(kind: str, body: str) -> tuple[str, str, str, str]:
    if "AED 1,000,000" in body:
        return "critical", "liability", "Limitation of liability", "The liability cap rose from AED 100,000 to AED 1,000,000."
    if "sixty (60) days" in body:
        return "major", "termination", "Termination for convenience", "The notice period fell from ninety to sixty days."
    if kind == "removed":
        return "major", "confidentiality", "Confidentiality", "The confidentiality clause was removed."
    if kind == "added":
        return "major", "data_protection", "Data protection", "A new data protection clause was added."
    return "cosmetic", "scope_services", "Services", "The wording changed but the meaning is the same."


class TestWhatIsFound:
    def test_unchanged_renumbered_clauses_are_not_reported(self):
        result, _ = run(llm=scripted(sensible))
        stats = result["stats"]

        assert stats["unchanged"] == 2  # payment, and governing law (renumbered 6 to 8)
        assert (stats["modified"], stats["added"], stats["removed"], stats["moved"]) == (3, 1, 1, 0)
        assert all("Governing Law" not in c["title"] for c in result["changes"])

    def test_changes_are_in_reading_order_with_the_removed_clause_where_it_used_to_be(self):
        result, _ = run(llm=scripted(sensible))
        order = [c["type"] + ":" + c["title"] for c in result["changes"]]

        assert order == [
            "modified:Services",
            "modified:Termination for convenience",
            "modified:Limitation of liability",
            "removed:Confidentiality",
            "added:Data protection",
        ]

    def test_changed_figures_are_extracted_by_code_as_old_to_new(self):
        result, _ = run(llm=scripted(sensible))

        assert by_title(result, "liability")["figures"] == [{"kind": "money", "old": "AED 100,000", "new": "AED 1,000,000"}]
        assert by_title(result, "termination")["figures"] == [{"kind": "duration", "old": "ninety (90) days", "new": "sixty (60) days"}]
        assert by_title(result, "Services")["figures"] == []

    def test_each_change_carries_both_texts_page_positions_and_a_word_diff(self):
        result, _ = run(llm=scripted(sensible))
        liability = by_title(result, "liability")

        assert "AED 100,000" in liability["old"]["text"] and "AED 1,000,000" in liability["new"]["text"]
        assert liability["old"]["ranges"][0]["page"] == 1 and liability["new"]["ranges"][0]["end"] > liability["new"]["ranges"][0]["start"]
        ops = {(s["op"], s["text"]) for s in liability["diff"]}
        assert ("delete", "100,000") in ops and ("insert", "1,000,000") in ops

    def test_a_removed_clause_has_only_an_old_side_and_an_added_one_only_a_new_side(self):
        result, _ = run(llm=scripted(sensible))

        removed, added = by_title(result, "Confidentiality"), by_title(result, "Data Protection")
        assert removed["new"] is None and removed["old"] is not None
        assert added["old"] is None and added["new"] is not None and added["diff"] == []

    def test_identical_versions_have_no_changes(self):
        result, _ = run(OLD, OLD, llm=scripted(sensible))

        assert result["changes"] == []
        assert result["stats"]["unchanged"] == 6
        assert result["summary"]["headline"]  # the overview is still produced

    def test_a_clause_that_only_moved_is_reported_as_moved_and_cosmetic(self):
        old = "First paragraph about delivery of the goods to the Customer.\n\nSecond paragraph about the payment of the fees by the Customer.\n\nThird paragraph about the insurance cover held by the Supplier.\n\nFourth paragraph about audit rights of the Customer over the records."
        new = "First paragraph about delivery of the goods to the Customer.\n\nThird paragraph about the insurance cover held by the Supplier.\n\nFourth paragraph about audit rights of the Customer over the records.\n\nSecond paragraph about the payment of the fees by the Customer."
        result, _ = run(old, new, llm=scripted(sensible))

        assert [(c["type"], c["significance"]) for c in result["changes"]] == [("moved", "cosmetic")]
        assert "moved" in result["changes"][0]["summary"].lower()

    def test_a_change_split_across_a_page_break_is_still_one_clause(self):
        old_pages = [(1, "Either party may terminate this Agreement for convenience by giving not less than ninety (90)"), (2, "days written notice, provided that all sums then due have been paid.")]
        new_pages = [(1, "Either party may terminate this Agreement for convenience by giving not less than sixty (60)"), (2, "days written notice, provided that all sums then due have been paid.")]
        settings = get_settings()
        result = asyncio.run(compare_documents(old_pages, new_pages, scripted(sensible), settings))

        assert len(result["changes"]) == 1
        assert [r["page"] for r in result["changes"][0]["old"]["ranges"]] == [1, 2]


class TestTheRulesCannotBeTalkedDown:
    def test_a_model_that_calls_a_changed_figure_cosmetic_is_overruled(self):
        llm = scripted(lambda kind, body: ("cosmetic", "other", "Anything", "Nothing important changed."))
        result, _ = run(llm=llm)

        liability = by_title(result, "liability")
        assert liability["significance"] == "major"
        assert liability["raised_by_rules"] is True
        assert by_title(result, "termination")["significance"] == "major"

    def test_a_model_may_raise_a_rating_above_the_rules(self):
        result, _ = run(llm=scripted(sensible))

        liability = by_title(result, "liability")
        assert liability["significance"] == "critical" and liability["raised_by_rules"] is False

    def test_a_pure_rewording_with_no_figures_is_not_inflated(self):
        result, _ = run(llm=scripted(sensible))

        services = by_title(result, "Services")
        assert services["significance"] == "cosmetic"
        assert services["figures"] == []

    def test_a_difference_in_only_case_or_punctuation_is_not_reported_at_all(self):
        old = "1. The Supplier shall deliver the goods to the Customer on time and in full.\n\n2. Payment is due within thirty (30) days."
        new = "1. The Supplier SHALL deliver the goods to the Customer, on time, and in full!\n\n2. Payment is due within thirty (30) days."
        result, _ = run(old, new, llm=scripted(sensible))

        assert result["changes"] == []
        assert result["stats"]["unchanged"] == 2

    def test_a_number_written_differently_is_cosmetic_without_asking_the_model(self):
        old = "The Supplier's aggregate liability shall not exceed AED 100,000 in any contract year."
        new = "The Supplier's aggregate liability shall not exceed AED 100000 in any contract year."
        llm = scripted(sensible)
        result, _ = run(old, new, llm=llm)

        assert [(c["type"], c["significance"], c["ai_rated"], c["figures"]) for c in result["changes"]] == [("modified", "cosmetic", False, [])]
        assert llm.count(prompts.RATE_SYSTEM) == 0

    def test_a_cross_reference_renumbered_is_cosmetic(self):
        old = "The Supplier shall comply with the obligations in clause 12 and clause 12.3 at all times."
        new = "The Supplier shall comply with the obligations in clause 14 and clause 14.3 at all times."
        result, _ = run(old, new, llm=scripted(sensible))

        assert result["changes"][0]["significance"] == "cosmetic"

    def test_a_changed_shall_or_may_is_never_cosmetic(self):
        old = "The Supplier may deliver the goods to the Customer within the agreed period."
        new = "The Supplier shall deliver the goods to the Customer within the agreed period."
        result, _ = run(old, new, llm=scripted(lambda k, b: ("cosmetic", "other", "t", "s")))

        change = result["changes"][0]
        assert change["significance"] == "minor" and change["raised_by_rules"] is True
        assert {o["word"] for o in change["obligations"]} == {"may", "shall"}


class TestWithoutOrWithFailingAI:
    def test_no_ai_still_rates_by_rules_and_is_honest_about_the_rest(self):
        result, _ = run(llm=None)
        levels = {c["title"]: c["significance"] for c in result["changes"]}

        assert by_title(result, "liability")["significance"] == "major"
        assert by_title(result, "termination")["significance"] == "major"
        assert by_title(result, "Services")["significance"] == "unrated"
        assert by_title(result, "Confidentiality")["significance"] == "unrated"
        assert by_title(result, "Data Protection")["significance"] == "unrated"
        assert result["ai_used"] is False and "not available" in result["ai_notice"]
        assert result["summary"] is None
        assert all(c["summary"] for c in result["changes"]), levels

    def test_a_model_that_fails_degrades_the_same_way(self):
        def broken(system, user):
            raise LLMError("The AI provider took too long to respond. Please try again.")

        result, _ = run(llm=FakeLLM(json_handler=broken))

        assert by_title(result, "liability")["significance"] == "major"
        assert by_title(result, "Services")["significance"] == "unrated"
        assert result["ai_used"] is False and "unavailable" in result["ai_notice"]
        assert result["summary"] is None

    def test_malformed_model_output_is_survived(self):
        result, _ = run(llm=FakeLLM(json_handler=lambda s, u: {"items": [{"id": "not a number"}]} if s == prompts.RATE_SYSTEM else {}))

        assert by_title(result, "liability")["significance"] == "major"
        assert result["ai_used"] is False

    def test_items_the_model_left_out_fall_back_while_the_rest_are_used(self):
        def partial(system, user):
            if system == prompts.RATE_SYSTEM:
                first = items_in(user)[0][0]
                return {"items": [{"id": first, "significance": "minor", "category": "other", "title": "Picked", "summary": "Only one rated."}]}
            return {"headline": "x", "key_points": []}

        result, _ = run(llm=FakeLLM(json_handler=partial))
        rated = [c for c in result["changes"] if c["ai_rated"]]

        assert len(rated) == 1
        assert "unavailable" in result["ai_notice"]

    def test_unknown_values_from_the_model_are_treated_as_unrated_and_other(self):
        llm = scripted(lambda k, b: ("catastrophic", "astrology", "t", "s"))
        result, _ = run(llm=llm)

        services = by_title(result, "Services")
        assert services["significance"] == "unrated" and services["category"] != "astrology"


class TestCostControls:
    def test_changes_are_rated_in_batches(self):
        llm = scripted(sensible)
        run(llm=llm, rate_batch_size=2)

        assert llm.count(prompts.RATE_SYSTEM) == 3  # five changes, two per request

    def test_only_changes_that_need_judgement_are_sent(self):
        llm = scripted(sensible)
        run(llm=llm, rate_batch_size=20)
        sent = items_in(llm.prompts_for(prompts.RATE_SYSTEM)[0])

        assert len(sent) == 5 and all(kind in {"modified", "added", "removed"} for _, kind, _ in sent)

    def test_the_cap_sends_the_weightiest_changes_and_the_rest_keep_rules_ratings(self):
        llm = scripted(sensible)
        result, _ = run(llm=llm, max_ai_rated_changes=2, rate_batch_size=20)
        sent = " ".join(body for _, _, body in items_in(llm.prompts_for(prompts.RATE_SYSTEM)[0]))

        assert "AED 1,000,000" in sent and "sixty (60) days" in sent  # the two with figures
        assert by_title(result, "Confidentiality")["significance"] == "unrated"
        assert "unavailable for" in result["ai_notice"]

    def test_the_ratings_use_the_steady_judging_temperature(self):
        llm = scripted(sensible)
        run(llm=llm)

        assert dict(llm.temperatures)[prompts.RATE_SYSTEM] == get_settings().temperature_judge


class TestOverviewAndProgress:
    def test_the_overview_comes_from_the_model_and_only_sees_substantive_changes(self):
        llm = scripted(sensible, overview={"headline": "The liability cap rose tenfold.", "key_points": ["Cap: AED 100,000 to AED 1,000,000.", "  ", "Notice fell to sixty days."]})
        result, _ = run(llm=llm)
        prompt = llm.prompts_for(prompts.SUMMARY_SYSTEM)[0]

        assert result["summary"] == {"headline": "The liability cap rose tenfold.", "key_points": ["Cap: AED 100,000 to AED 1,000,000.", "Notice fell to sixty days."]}
        assert "[critical]" in prompt and "[cosmetic]" not in prompt
        assert "2 clauses unchanged" in prompt

    def test_progress_is_reported_stage_by_stage(self):
        _, events = run(llm=scripted(sensible), rate_batch_size=2)
        stages = [stage for stage, _, _ in events]

        assert stages[0] == "reading" and stages[1] == "aligning" and stages[-1] == "summarising"
        assert ("rating", 3, 3) in events

    def test_counts_by_significance_add_up(self):
        result, _ = run(llm=scripted(sensible))
        by_level = result["stats"]["by_significance"]

        assert sum(by_level.values()) == len(result["changes"])
        assert by_level["critical"] == 1 and by_level["cosmetic"] == 1


class TestAtScale:
    def test_two_long_contracts_compare_quickly_and_find_the_planted_changes(self):
        def contract(cap: str, drop: int | None, extra: bool) -> str:
            clauses = []
            for n in range(1, 401):
                if n == drop:
                    continue
                body = f"The parties record obligation number {n * 17} concerning item {n} of schedule {n % 9} and the delivery of goods to site {n * 3}."
                if n == 200:
                    body = f"The Supplier's aggregate liability shall not exceed {cap} in any contract year, whatever the cause of loss {n}."
                clauses.append(f"{n}. Clause {n}\n\n{body}")
            if extra:
                clauses.append("401. Counterparts\n\nThis Agreement may be signed in counterparts, each of which is an original and all of which are one document.")
            return "\n\n".join(clauses)

        old, new = contract("AED 100,000", None, False), contract("AED 1,000,000", 50, True)
        start = time.perf_counter()
        result, _ = run(old, new, llm=None)
        elapsed = time.perf_counter() - start

        assert elapsed < 20, f"comparison took {elapsed:.1f}s"
        assert result["stats"]["unchanged"] == 398
        assert (result["stats"]["modified"], result["stats"]["added"], result["stats"]["removed"]) == (1, 1, 1)
        assert by_title(result, "aggregate liability")["figures"][0]["new"] == "AED 1,000,000"


def test_the_overview_is_valid_json_the_interface_can_store():
    result, _ = run(llm=scripted(sensible))
    assert json.loads(json.dumps(result))["stats"]["unchanged"] == 2


class TestWhatTheReaderSees:
    def test_the_diff_covers_the_clause_body_and_ignores_a_shifted_clause_number(self):
        result, _ = run(llm=scripted(sensible))
        liability = by_title(result, "liability")  # numbered 4 in the old version and 4 in the new

        changed = [(s["op"], s["text"]) for s in liability["diff"] if s["op"] != "equal"]
        assert changed == [("delete", "100,000"), ("insert", "1,000,000")]

    def test_a_clause_that_only_moved_down_a_number_shows_only_its_real_change(self):
        old = "3. Liability\n\nThe Supplier's aggregate liability shall not exceed AED 100,000 in any contract year.\n\n4. Law\n\nThis Agreement is governed by the laws of England and Wales."
        new = "3. Notices\n\nNotices must be in writing and delivered by hand or registered post to the registered office.\n\n4. Liability\n\nThe Supplier's aggregate liability shall not exceed AED 1,000,000 in any contract year.\n\n5. Law\n\nThis Agreement is governed by the laws of England and Wales."
        result, _ = run(old, new, llm=scripted(sensible))
        liability = next(c for c in result["changes"] if c["type"] == "modified")

        assert [(s["op"], s["text"]) for s in liability["diff"] if s["op"] != "equal"] == [("delete", "100,000"), ("insert", "1,000,000")]

    def test_the_heading_is_given_separately_and_the_text_is_just_the_clause(self):
        result, _ = run(llm=scripted(sensible))
        side = by_title(result, "liability")["new"]

        assert side["heading"] == "4. Limitation of Liability"
        assert side["text"].startswith("The Supplier's aggregate liability")
        assert "Limitation of Liability" not in side["text"]

    def test_the_ranges_still_cover_the_heading_and_the_clause_on_the_page(self):
        result, _ = run(llm=scripted(sensible))
        side = by_title(result, "liability")["new"]
        page_text = NEW
        covered = page_text[side["ranges"][0]["start"] : side["ranges"][0]["end"]]

        assert "Limitation of Liability" in covered and "AED 1,000,000" in covered
