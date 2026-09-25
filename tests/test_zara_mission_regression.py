import pytest

from core.lab_v1.feedback_inbox import looks_like_product_criticism


@pytest.mark.parametrize(
    "text",
    [
        "A ZARA está sem erro e sem falha.",
        "A ZARA está sem bug.",
    ],
)
def test_negated_problem_terms_are_not_criticism(text):
    assert looks_like_product_criticism(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "A ZARA está com erro e falha ao responder.",
        "A ZARA não funciona corretamente.",
        "A ZARA travou durante o uso.",
        "A ZARA apresentou um bug hoje.",
        "A ZARA está muito lenta.",
    ],
)
def test_real_criticism_remains_detected(text):
    assert looks_like_product_criticism(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "A ZARA está sem erro, mas travou ao responder.",
        "A ZARA está sem falha, porém está lenta.",
        "A ZARA está sem bug, mas não funciona.",
    ],
)
def test_negated_terms_do_not_hide_other_real_criticism(text):
    assert looks_like_product_criticism(text) is True


@pytest.mark.parametrize("text", ["", "Tudo certo.", "A ZARA respondeu normalmente."])
def test_non_criticism_remains_ignored(text):
    assert looks_like_product_criticism(text) is False
