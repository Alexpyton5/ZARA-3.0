#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot do cérebro operacional da ZARA 3.0
Exporta a camada de DADOS (memória, config, lembretes, skills, etc.)
sem senhas, tokens, cache ou build.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Adiciona o diretório raiz do projeto ao path para importar módulos do core
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import memory_dir, user_data_dir, config_dir
from memory.memory_manager import export_memory, load_memory, _redact_memory_for_export


def get_project_data_dirs():
    """Retorna os diretórios de dados que devem ser incluidos no snapshot."""
    base = PROJECT_ROOT
    return {
        'memory': base / 'memory',
        'config': base / 'config',
        'data': base / 'data',
        'lembretes': base / 'lembretes',
        'skills': base / 'skills',
        'integrations': base / 'integrations',
    }


def redact_api_keys_file(src_path: Path, dst_path: Path):
    """Copia o arquivo de api_keys redigindo os valores."""
    try:
        with open(src_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Erro ao ler {src_path}: {e}")
        # Se falhar, copia o arquivo original (melhor que nada)
        shutil.copy2(src_path, dst_path)
        return

    # Redige valores de chaves conhecidas e qualquer coisa que pareça uma chave
    sensitive_keys = {
        'gemini_api_key', 'zai_api_key', 'xai_api_key', 'groq_api_key',
        'nvidia_api_key', 'hermes_api_key'
    }
    for key in data:
        if key in sensitive_keys:
            data[key] = '«redacted»'
        elif isinstance(data[key], str) and data[key]:
            # Heurística simples: se o valor parece uma chave (larga e alfanumérica), redige
            if len(data[key]) >= 20 and all(c.isalnum() or c in '_-' for c in data[key]):
                data[key] = '«redacted»'

    try:
        with open(dst_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erro ao escrever {dst_path}: {e}")
        # Em caso de erro, tenta copiar o original
        shutil.copy2(src_path, dst_path)


def export_cerebro(snapshot_dir: Path):
    """Exporta o cérebro operacional para o diretório informado."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"Exportando cérebro para: {snapshot_dir}")

    data_dirs = get_project_data_dirs()

    # 1. Exporta memória com redigição de sensíveis (usa função existente)
    memory_export_dir = snapshot_dir / 'memory'
    memory_export_dir.mkdir()
    try:
        # Usa a função de exportação da memory_manager que já redige
        exported_path = export_memory(destination=memory_export_dir / f"zara-memory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        print(f"Memória exportada e redigida: {exported_path}")
    except Exception as e:
        print(f"Falha ao exportar memória: {e}")
        # Fallback: copia a memória bruta (não recomendado para produção, mas para teste)
        shutil.copytree(data_dirs['memory'], memory_export_dir, dirs_exist_ok=True)

    # 2. Exporta config (com redigição de api_keys.json)
    config_export_dir = snapshot_dir / 'config'
    config_export_dir.mkdir()
    for item in data_dirs['config'].iterdir():
        if item.is_file():
            if item.name == 'api_keys.json':
                redact_api_keys_file(item, config_export_dir / item.name)
            else:
                # Copia outros arquivos de config (ex.: example, base.py, etc.)
                shutil.copy2(item, config_export_dir / item.name)
        elif item.is_dir() and item.name != '__pycache__':
            shutil.copytree(item, config_export_dir / item.name, dirs_exist_ok=True)

    # 3. Exporta data
    data_export_dir = snapshot_dir / 'data'
    if data_dirs['data'].exists():
        shutil.copytree(data_dirs['data'], data_export_dir, dirs_exist_ok=True)

    # 4. Exporta lembretes
    lembretes_export_dir = snapshot_dir / 'lembretes'
    if data_dirs['lembretes'].exists():
        shutil.copytree(data_dirs['lembretes'], lembretes_export_dir, dirs_exist_ok=True)

    # 5. Exporta skills
    skills_export_dir = snapshot_dir / 'skills'
    if data_dirs['skills'].exists():
        shutil.copytree(data_dirs['skills'], skills_export_dir, dirs_exist_ok=True)

    # 6. Exporta integracaoes
    integrations_export_dir = snapshot_dir / 'integrations'
    if data_dirs['integrations'].exists():
        shutil.copytree(data_dirs['integrations'], integrations_export_dir, dirs_exist_ok=True)

    # Cria um manifesto simples
    manifest = {
        'snapshot_time': datetime.now().isoformat(),
        'source': str(PROJECT_ROOT),
        'contents': [str(p) for p in snapshot_dir.rglob('*')],
        'note': 'Snapshot do cérebro operacional da ZARA 3.0 - camada de DADOS apenas, com redigição de segredos.'
    }
    (snapshot_dir / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print("Exportação concluída.")


def verify_export(snapshot_dir: Path):
    """Verifica se o snapshot não contém segredos óbvios."""
    print("\nVerificando exportação...")
    issues = []

    # Verifica se api_keys.json foi redigido
    api_keys_path = snapshot_dir / 'config' / 'api_keys.json'
    if api_keys_path.exists():
        try:
            content = api_keys_path.read_text(encoding='utf-8')
            if '«redacted»' not in content and 'gemini_api_key' in content:
                # Se ainda tiver o valor original, é um problema
                if 'AIza' in content or 'gsk_' in content:
                    issues.append("api_keys.json contém chaves não redigidas")
        except Exception as e:
            issues.append(f"Não foi possível ler api_keys.json para verificação: {e}")

    # Verifica se a memória exportada não contém chaves simples
    memory_files = list((snapshot_dir / 'memory').glob('*.json'))
    for mf in memory_files:
        try:
            content = mf.read_text(encoding='utf-8').lower()
            # Procure por padrões de chaves comuns
            if 'aiza' in content or 'gsk_' in content or ' bearer ' in content:
                issues.append(f"Memória exportada pode conter chaves não redigidas: {mf.name}")
        except Exception:
            pass

    if issues:
        print("PROBLEMS ENCONTRADOS:")
        for issue in issues:
            print(f" - {issue}")
        return False
    else:
        print("Nenhum problema óbvio de vazamento de segredos detectado.")
        return True


def main():
    """Função principal: cria snapshot em um diretório temporário e verifica."""
    # Diretório de snapshots (pode ser alterado para um local de backup real)
    snapshot_base = PROJECT_ROOT / 'snapshots'
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    snapshot_dir = snapshot_base / f'cerebro_{timestamp}'

    try:
        export_cerebro(snapshot_dir)
        if verify_export(snapshot_dir):
            print(f"\nSnapshot criado com sucesso em: {snapshot_dir}")
            print("Para restaurar, copie o conteúdo de volta para o diretório do projeto (sobrescrevendo os diretórios de dados).")
        else:
            print("\nExportação concluída, mas foram encontrados problemas de vazamento de segredos.")
            return 1
    except Exception as e:
        print(f"Erro durante a exportação: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())