"""Testes de core/pii_redaction: mascara dados sensiveis BR antes da nuvem."""

from core.pii_redaction import (
    cnpj_valido,
    cpf_valido,
    find_pii,
    redact,
    redaction_report,
)


def test_cpf_valido_mascarado_e_invalido_intacto():
    assert redact("meu cpf 529.982.247-25 ok") == "meu cpf [CPF] ok"
    assert redact("cpf 52998224725") == "cpf [CPF]"
    # digitos verificadores errados: nao e CPF, nao mascara
    assert redact("codigo 529.982.247-26") == "codigo 529.982.247-26"
    assert cpf_valido("52998224725")
    assert not cpf_valido("52998224726")
    assert not cpf_valido("11111111111")


def test_cnpj_valido_mascarado():
    assert redact("cnpj 11.222.333/0001-81") == "cnpj [CNPJ]"
    assert cnpj_valido("11222333000181")
    assert not cnpj_valido("11222333000182")


def test_telefone_br_mascarado():
    assert redact("me liga no (71) 99988-7766") == "me liga no [TELEFONE]"
    assert redact("zap 71999887766") == "zap [TELEFONE]"
    assert redact("+55 71 99988-7766 urgente") == "[TELEFONE] urgente"
    assert redact("fone 5571999887766") == "fone [TELEFONE]"
    # corrida de 16 digitos que nao passa no Luhn nem parece telefone: intacta
    assert redact("numero 4111 1111 1111 1112") == "numero 4111 1111 1111 1112"


def test_email_cartao_pix_e_chave_api():
    assert redact("manda p/ alex.teste4up@gmail.com") == "manda p/ [EMAIL]"
    assert redact("cartao 4111 1111 1111 1111") == "cartao [CARTAO]"
    assert "[PIX]" in redact(
        "chave 123e4567-e89b-12d3-a456-426614174000"
    )
    assert redact("usa sk-abcDEF1234567890xyz") == "usa [CHAVE-API]"
    assert redact("chave nvapi-abc123XYZ-_9") == "chave [CHAVE-API]"


def test_texto_sem_pii_volta_intacto():
    texto = "a ZARA e a JARVIS real do Alex, boa noite"
    assert redact(texto) == texto
    assert find_pii(texto) == []
    rel = redaction_report(texto)
    assert rel["teve_pii"] is False
    assert rel["contagem"] == {}


def test_find_pii_e_relatorio_contam_tipos():
    texto = "cpf 529.982.247-25 e email alex.teste4up@gmail.com"
    achados = find_pii(texto)
    tipos = sorted(a["tipo"] for a in achados)
    assert tipos == ["cpf", "email"]
    assert all(a["trecho"] for a in achados)
    rel = redaction_report(texto)
    assert rel["teve_pii"] is True
    assert rel["contagem"] == {"cpf": 1, "email": 1}
    assert "[CPF]" in rel["texto"] and "[EMAIL]" in rel["texto"]


def test_redact_aceita_none_e_vazio():
    assert redact(None) == ""
    assert redact("") == ""
