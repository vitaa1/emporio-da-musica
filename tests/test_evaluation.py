"""Evaluation verdicts must detect wrong facts and keep failures observable."""

from types import SimpleNamespace

from emporio_da_musica.contracts.results import SmallTalkData, SmallTalkResult
from emporio_da_musica.controller import TurnResponse
from evals.suite import Scenario, check_results, load_cases, run_scenario


def test_versioned_cases_have_unique_ids_and_explicit_outcomes():
    cases = load_cases()
    assert len(cases) >= 5
    assert any(c.customer_id is None for c in cases)
    assert any(c.customer_id is not None for c in cases)
    assert any(t.manual_review for c in cases for t in c.turns)


def test_verdict_checks_money_product_quantity_and_extra_operations():
    expected = [
        {
            "operation": "payment_options",
            "status": "success",
            "data": {"name": "Product", "quantity": 2, "final_total_brl": "100.00"},
        }
    ]
    actual = [
        {
            "operation": "payment_options",
            "status": "success",
            "data": {"name": "Product", "quantity": 2, "final_total_brl": "100"},
        }
    ]
    assert not check_results(actual, expected)
    for field, wrong in [("name", "Other"), ("quantity", 1), ("final_total_brl", "99")]:
        altered = [{**actual[0], "data": {**actual[0]["data"], field: wrong}}]
        assert check_results(altered, expected)
    assert check_results(actual * 2, expected)
    assert check_results([], expected)
    assert check_results([{**actual[0], "data": None}], expected)


def test_repeated_expectations_cannot_reuse_one_result():
    result = {"operation": "small_talk", "status": "success"}
    assert check_results([result], [result, result])


def test_failure_does_not_skip_later_turns_or_hide_manual_review():
    case = Scenario.model_validate(
        {
            "id": "test",
            "customer_id": None,
            "origin": "synthetic",
            "turns": [
                {
                    "message": "first",
                    "expected": [{"operation": "payment_options", "status": "success"}],
                },
                {
                    "message": "second",
                    "expected": [{"operation": "small_talk", "status": "success"}],
                    "manual_review": "Check prose",
                },
            ],
        }
    )
    calls = []

    def handle(message):
        calls.append(message)
        return TurnResponse(
            "Actual response",
            (
                SmallTalkResult(
                    status="success", data=SmallTalkData(template="greeting")
                ),
            ),
        )

    report = run_scenario(case, SimpleNamespace(handle=handle))
    assert calls == ["first", "second"]
    assert [t["automated_pass"] for t in report["turns"]] == [False, True]
    assert report["turns"][1]["manual_status"] == "pending"
    assert report["turns"][0]["response"] == "Actual response"


def test_optional_catalog_must_match_named_product_and_cannot_repeat():
    quote = {"operation": "payment_options", "status": "needs_information"}
    catalog = {
        "operation": "product_search",
        "data": {"products": [{"product_id": 82, "name": "C70"}]},
    }
    allowed = {
        "operation": "product_search",
        "data": {"products": [{"product_id": 82}]},
    }
    assert not check_results([quote], [quote], [allowed])
    assert not check_results([catalog, quote], [quote], [allowed])
    assert check_results([catalog, catalog, quote], [quote], [allowed])
    wrong = {"operation": "product_search", "data": {"products": [{"product_id": 81}]}}
    assert check_results([wrong, quote], [quote], [allowed])


def test_overlapping_expectations_are_independent_of_result_order():
    broad = {"operation": "payment_options", "status": "success"}
    specific = {**broad, "data": {"quantity": 2}}
    first = {**broad, "data": {"quantity": 1}}
    assert not check_results([specific, first], [broad, specific])
    assert not check_results([first, specific], [broad, specific])
