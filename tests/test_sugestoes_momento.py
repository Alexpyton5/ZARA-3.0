import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.sugestoes_momento import SugestoesMomento


def test_inicializacao():
    """Testa a inicialização do módulo."""
    diario_mock = Mock()
    sugestoes = SugestoesMomento(diario=diario_mock, limite_diario=3, limite_ociosidade=10.0)
    
    assert sugestoes.diario == diario_mock
    assert sugestoes.limite_diario == 3
    assert sugestoes.limite_ociosidade == 10.0
    assert sugestoes.estado_path.name == "sugestoes_momento_state.json"


def test_carregar_estado_arquivo_inexistente(tmp_path):
    """Testa carregamento de estado quando o arquivo não existe."""
    estado_path = tmp_path / "estado.json"
    sugestoes = SugestoesMomento(estado_path=estado_path)
    
    # Deve retornar estado inicial
    hoje = time.strftime("%Y-%m-%d", time.localtime())
    assert sugestoes._estado["date"] == hoje
    assert sugestoes._estado["shown_count"] == 0
    assert sugestoes._estado["shown_ids"] == []


def test_carregar_estado_arquivo_existente(tmp_path):
    """Testa carregamento de estado a partir de arquivo existente."""
    estado_path = tmp_path / "estado.json"
    estado_inicial = {
        "date": "2026-08-22",
        "shown_count": 2,
        "shown_ids": [1, 2, 3]
    }
    
    with estado_path.open("w", encoding="utf-8") as f:
        json.dump(estado_inicial, f)
    
    sugestoes = SugestoesMomento(estado_path=estado_path)
    assert sugestoes._estado == estado_inicial


def test_resetar_estado_se_novo_dia(tmp_path):
    """Testa reset do estado quando muda o dia."""
    estado_path = tmp_path / "estado.json"
    estado_ontem = {
        "date": "2026-08-21",  # ontem
        "shown_count": 5,
        "shown_ids": [1, 2, 3, 4, 5]
    }
    
    with estado_path.open("w", encoding="utf-8") as f:
        json.dump(estado_ontem, f)
    
    sugestoes = SugestoesMomento(estado_path=estado_path)
    # Força a data de hoje ser diferente
    with patch('time.strftime') as mock_strftime:
        mock_strftime.return_value = "2026-08-22"  # hoje
        sugestoes._resetar_estado_se_novo_dia()
    
    assert sugestoes._estado["date"] == "2026-08-22"
    assert sugestoes._estado["shown_count"] == 0
    assert sugestoes._estado["shown_ids"] == []


def test_obter_sugestoes_sem_sugestoes_pendentes(tmp_path):
    """Testa quando não há sugestões pendentes."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    diario_mock.sugestoes_pendentes.return_value = []
    
    sugestoes = SugestoesMomento(diario=diario_mock, estado_path=estado_path)
    resultado = sugestoes.obter_sugestoes()
    
    assert resultado == []
    diario_mock.sugestoes_pendentes.assert_called_once()


def test_obter_sugestoes_agrupamento_chave(tmp_path):
    """Testa o agrupamento por chave de agregação."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    # Duas sugestões com mesma chave
    sug1 = {
        "id": 1,
        "dia": "2026-08-22",
        "regra": "revisar_acao",
        "chave_agregacao": "volume_up | os_volume",
        "comando_representativo": "aumenta o volume",
        "acao": "os_volume"
    }
    sug2 = {
        "id": 2,
        "dia": "2026-08-22",
        "regra": "revisar_acao",
        "chave_agregacao": "volume_up | os_volume",  # mesma chave
        "comando_representativo": "suba o som",
        "acao": "os_volume"
    }
    # Uma sugestão com chave diferente
    sug3 = {
        "id": 3,
        "dia": "2026-08-22",
        "regra": "otimizar",
        "chave_agregacao": "abrir_youtube | youtube_open",
        "comando_representativo": "abre o youtube",
        "acao": "youtube_open"
    }
    
    diario_mock.sugestoes_pendentes.return_value = [sug1, sug2, sug3]
    
    sugestoes = SugestoesMomento(diario=diario_mock, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        # Mock ambiente favorável (dia, livre, etc.)
        ambiente_mock = Mock()
        ambiente_mock.periodo = "tarde"
        ambiente_mock.ocioso_segundos = 60.0
        mock_ler_ambiente.return_value = ambiente_mock
        
        resultado = sugestoes.obter_sugestoes()
    
    # Deve retornar apenas 2 sugestões (uma por chave de agregação)
    assert len(resultado) == 2
    chaves_resultado = {s["chave_agregacao"] for s in resultado}
    assert chaves_resultado == {"volume_up | os_volume", "abrir_youtube | youtube_open"}


def test_obter_sugestoes_silencio_noturno(tmp_path):
    """Testa que não retorna sugestões durante silêncio noturno."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    diario_mock.sugestoes_pendentes.return_value = [{"id": 1}]
    
    sugestoes = SugestoesMomento(diario=diario_mock, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        ambiente_mock = Mock()
        ambiente_mock.periodo = "noite"  # silêncio noturno
        ambiente_mock.ocioso_segundos = 60.0
        mock_ler_ambiente.return_value = ambiente_mock
        
        resultado = sugestoes.obter_sugestoes()
    
    assert resultado == []


def test_obter_sugestoes_alex_ocupado(tmp_path):
    """Testa que não retorna sugestões quando Alex está ocupado."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    diario_mock.sugestoes_pendentes.return_value = [{"id": 1}]
    
    sugestoes = SugestoesMomento(diario=diario_mock, limite_ociosidade=30.0, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        ambiente_mock = Mock()
        ambiente_mock.periodo = "tarde"
        ambiente_mock.ocioso_segundos = 5.0  # muito pouco tempo ocioso
        mock_ler_ambiente.return_value = ambiente_mock
        
        resultado = sugestoes.obter_sugestoes()
    
    assert resultado == []


def test_obter_sugestoes_limite_diario(tmp_path):
    """Testa o limite diário de sugestões."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    # Cria 10 sugestões pendentes
    sugestoes_pendentes = [
        {"id": i, "dia": "2026-08-22", "regra": "test", "chave_agregacao": f"chave_{i}", 
         "comando_representativo": f"cmd_{i}", "acao": f"acao_{i}"}
        for i in range(10)
    ]
    diario_mock.sugestoes_pendentes.return_value = sugestoes_pendentes
    
    sugestoes = SugestoesMomento(diario=diario_mock, limite_diario=3, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        ambiente_mock = Mock()
        ambiente_mock.periodo = "tarde"
        ambiente_mock.ocioso_segundos = 60.0
        mock_ler_ambiente.return_value = ambiente_mock
        
        # Primeira chamada
        resultado1 = sugestoes.obter_sugestoes()
        assert len(resultado1) == 3
        assert sugestoes._estado["shown_count"] == 3
        
        # Segunda chamada no mesmo dia
        resultado2 = sugestoes.obter_sugestoes()
        assert len(resultado2) == 0  # limite atingido
        assert sugestoes._estado["shown_count"] == 3


def test_obter_sugestoes_nao_repetir_mesma_sugestao(tmp_path):
    """Testa que não mostra a mesma sugestão duas vezes no mesmo dia."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    sug = {"id": 42, "dia": "2026-08-22", "regra": "test", "chave_agregacao": "test|test", 
           "comando_representativo": "test", "acao": "test"}
    diario_mock.sugestoes_pendentes.return_value = [sug]
    
    sugestoes = SugestoesMomento(diario=diario_mock, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        ambiente_mock = Mock()
        ambiente_mock.periodo = "tarde"
        ambiente_mock.ocioso_segundos = 60.0
        mock_ler_ambiente.return_value = ambiente_mock
        
        # Primeira chamada
        resultado1 = sugestoes.obter_sugestoes()
        assert len(resultado1) == 1
        assert resultado1[0]["id"] == 42
        assert sugestoes._estado["shown_count"] == 1
        assert 42 in sugestoes._estado["shown_ids"]
        
        # Segunda chamada - deve retornar vazio já que já foi mostrada
        resultado2 = sugestoes.obter_sugestoes()
        assert resultado2 == []
        assert sugestoes._estado["shown_count"] == 1  # permanece o mesmo


def test_obter_sugestoes_sem_id_usa_hash(tmp_path):
    """Testa que sugestões sem ID usam hash para controle de repetição."""
    estado_path = tmp_path / "estado.json"
    diario_mock = Mock()
    # Sugestão sem ID
    sug = {
        "dia": "2026-08-22",
        "regra": "test",
        "chave_agregacao": "test|test",
        "comando_representativo": "test",
        "acao": "test"
        # sem campo 'id'
    }
    diario_mock.sugestoes_pendentes.return_value = [sug]
    
    sugestoes = SugestoesMomento(diario=diario_mock, estado_path=estado_path)
    
    with patch('core.sugestoes_momento.ler_ambiente') as mock_ler_ambiente:
        ambiente_mock = Mock()
        ambiente_mock.periodo = "tarde"
        ambiente_mock.ocioso_segundos = 60.0
        mock_ler_ambiente.return_value = ambiente_mock
        
        # Primeira chamada
        resultado1 = sugestoes.obter_sugestoes()
        assert len(resultado1) == 1
        # Verifica que o estado foi atualizado com algum ID (hash)
        assert sugestoes._estado["shown_count"] == 1
        
        # Segunda chamada - deve retornar vazio
        resultado2 = sugestoes.obter_sugestoes()
        assert resultado2 == []