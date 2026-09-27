from core.lab_v1.feedback_inbox import looks_like_product_criticism


def test_positive_negated_error_is_not_criticism():
    assert not looks_like_product_criticism("Não há erro ou falha na ZARA.")


def test_positive_negated_error_variants_are_not_criticism():
    assert not looks_like_product_criticism("não há ERRO ou FALHA na ZARA")
    assert not looks_like_product_criticism("  Não   há   erro   ou   falha   na ZARA.  ")


def test_real_product_criticism_remains_detected():
    for text in ("A ZARA apresenta erro.", "O envio falhou.", "O aplicativo não funciona."):
        assert looks_like_product_criticism(text)


def test_negated_error_with_another_real_problem_remains_criticism():
    assert looks_like_product_criticism("Não há erro ou falha, mas o aplicativo trava.")
