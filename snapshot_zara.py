#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot ZARA 3.0 — exporta camada de DADOS sem segredos.
- Exclui/redige todos arquivos de segredo inclusive backups e variantes
- Nunca faz fallback copiando bruto quando a redacao falhar
- Exclui caches/builds (__pycache__, *.pyc)
- Implementa restore seguro em pasta limpa com dry-run, manifest e protecao contra path traversal
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import memory_dir, user_data_dir, config_dir
from memory.memory_manager import export_memory, load_memory, _redact_memory_for_export


SENSITIVE_FILENAME_PATTERNS = (
    "api_keys",
    "secret",
    "credential",
    "password",
    "token",
    "senha",
    "chave",
)
SENSITIVE_SUFFIXES = (
    ".bak",
    ".backup",
    ".orig",
    ".antes",
    ".backup",
    "-backup",
    "-bak",
    ".bak-",
)


def is_sensitive_filename(name: str) -> bool:
    """Verifica se o nome do arquivo indica conteudo sensivel."""
    name_lower = name.lower()
    for pattern in SENSITIVE_FILENAME_PATTERNS:
        if pattern in name_lower:
            return True
    for suffix in SENSITIVE_SUFFIXES:
        if name_lower.endswith(suffix):
            return True
    return False


def is_cache_or_build(name: str) -> bool:
    """Verifica se e arquivo de cache ou build que deve ser excluido."""
    return (
        name == "__pycache__"
        or name.endswith(".pyc")
        or name.endswith(".pyo")
        or name.endswith(".pyd")
        or name == ".pytest_cache"
        or name == ".mypy_cache"
        or name == ".ruff_cache"
    )


def should_exclude_file(name: str) -> bool:
    """Determina se arquivo deve ser excluido do snapshot."""
    # api_keys.json principal deve ser REDIGIDO, nao excluido
    if name == "api_keys.json":
        return False
    return is_sensitive_filename(name) or is_cache_or_build(name)


def should_exclude_dir(name: str) -> bool:
    """Determina se diretorio deve ser excluido do snapshot."""
    return name == "__pycache__" or is_cache_or_build(name)


def redact_api_keys_file(src_path: Path, dst_path: Path) -> bool:
    """
    Redige api_keys.json. Retorna True se sucesso, False se falha.
    NUNCA faz fallback copiando o original.
    """
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERRO] Falha ao ler {src_path}: {e}")
        return False

    sensitive_keys = {
        "gemini_api_key",
        "zai_api_key",
        "xai_api_key",
        "groq_api_key",
        "nvidia_api_key",
        "hermes_api_key",
        "telegram_bot_token",
        "telegram_group_token",
        "telegram_dono",
        "telegram_group_dono_privado",
        "telegram_group_id",
    }

    for key in list(data.keys()):
        if key in sensitive_keys:
            data[key] = "«redacted»"
        elif isinstance(data[key], str) and data[key]:
            if len(data[key]) >= 20 and all(c.isalnum() or c in "_-" for c in data[key]):
                data[key] = "«redacted»"

    try:
        with open(dst_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao escrever {dst_path}: {e}")
        return False


def copy_with_redaction(src: Path, dst: Path, redaction_fn=None) -> bool:
    """
    Copia arquivo aplicando redacao se fornecida.
    Retorna True se sucesso, False se falha (nao faz fallback).
    """
    try:
        if redaction_fn:
            return redaction_fn(src, dst)
        else:
            shutil.copy2(src, dst)
            return True
    except Exception as e:
        print(f"[ERRO] Falha ao copiar {src} -> {dst}: {e}")
        return False


def export_cerebro(snapshot_dir: Path) -> bool:
    """Exporta o cerebro operacional para o diretorio informado. Retorna True se sucesso."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"Exportando cerebro para: {snapshot_dir}")

    data_dirs = get_project_data_dirs()
    core_files = get_project_core_files()

    all_ok = True

    # 1. Exporta memoria com redigicao de sensiveis (usa funcao existente)
    memory_export_dir = snapshot_dir / "memory"
    memory_export_dir.mkdir()
    try:
        exported_path = export_memory(
            destination=memory_export_dir / f"zara-memory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        print(f"Memoria exportada e redigida: {exported_path}")
    except Exception as e:
        print(f"[ERRO] Falha ao exportar memoria: {e}")
        all_ok = False

    # 2. Exporta config (com redigicao de api_keys.json, EXCLUI backups)
    config_export_dir = snapshot_dir / "config"
    config_export_dir.mkdir()
    config_src = data_dirs["config"]
    if config_src.exists():
        for item in config_src.iterdir():
            if should_exclude_file(item.name) or should_exclude_dir(item.name):
                print(f"  Excluido (sensivel/cache): {item.name}")
                continue
            if item.is_file():
                if item.name == "api_keys.json":
                    ok = copy_with_redaction(item, config_export_dir / item.name, redact_api_keys_file)
                    if not ok:
                        all_ok = False
                else:
                    ok = copy_with_redaction(item, config_export_dir / item.name)
                    if not ok:
                        all_ok = False
            elif item.is_dir() and not should_exclude_dir(item.name):
                ok = copytree_filtered(item, config_export_dir / item.name)
                if not ok:
                    all_ok = False

    # 3. Exporta data
    data_export_dir = snapshot_dir / "data"
    data_src = data_dirs["data"]
    if data_src.exists():
        ok = copytree_filtered(data_src, data_export_dir)
        if not ok:
            all_ok = False

    # 4. Exporta lembretes
    lembretes_export_dir = snapshot_dir / "lembretes"
    lembretes_src = data_dirs["lembretes"]
    if lembretes_src.exists():
        ok = copytree_filtered(lembretes_src, lembretes_export_dir)
        if not ok:
            all_ok = False

    # 5. Exporta skills
    skills_export_dir = snapshot_dir / "skills"
    skills_src = data_dirs["skills"]
    if skills_src.exists():
        ok = copytree_filtered(skills_src, skills_export_dir)
        if not ok:
            all_ok = False

    # 6. Exporta integracoes
    integrations_export_dir = snapshot_dir / "integrations"
    integrations_src = data_dirs["integrations"]
    if integrations_src.exists():
        ok = copytree_filtered(integrations_src, integrations_export_dir)
        if not ok:
            all_ok = False

    # 7. Exporta identidade/persona
    identity_export_dir = snapshot_dir / "core" / "identity"
    identity_export_dir.parent.mkdir(parents=True, exist_ok=True)
    identity_src = data_dirs["identity"]
    if identity_src.exists():
        ok = copytree_filtered(identity_src, identity_export_dir)
        if not ok:
            all_ok = False

    # 8. Exporta automacoes (initiative)
    initiative_export_dir = snapshot_dir / "core" / "initiative"
    initiative_export_dir.parent.mkdir(parents=True, exist_ok=True)
    initiative_src = data_dirs["initiative"]
    if initiative_src.exists():
        ok = copytree_filtered(initiative_src, initiative_export_dir)
        if not ok:
            all_ok = False

    # 9. Exporta percepcao (perception)
    perception_export_dir = snapshot_dir / "core" / "perception"
    perception_export_dir.parent.mkdir(parents=True, exist_ok=True)
    perception_src = data_dirs["perception"]
    if perception_src.exists():
        ok = copytree_filtered(perception_src, perception_export_dir)
        if not ok:
            all_ok = False

    # 10. Exporta arquivos especificos do core (Task Registry/LAB)
    core_export_dir = snapshot_dir / "core"
    core_export_dir.mkdir(parents=True, exist_ok=True)
    for src_file in core_files:
        if src_file.exists():
            dst_file = core_export_dir / src_file.name
            ok = copy_with_redaction(src_file, dst_file)
            if not ok:
                all_ok = False
            else:
                print(f"Copiado: {src_file.name}")
        else:
            print(f"Aviso: arquivo nao encontrado: {src_file}")

    # Cria manifesto
    manifest = {
        "snapshot_time": datetime.now().isoformat(),
        "source": str(PROJECT_ROOT),
        "contents": [str(p.relative_to(snapshot_dir)) for p in snapshot_dir.rglob("*")],
        "note": "Snapshot do cerebro operacional da ZARA 3.0 - camada de DADOS apenas, com redigicao de segredos, sem caches/builds/backups.",
    }
    try:
        (snapshot_dir / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print(f"[ERRO] Falha ao criar manifesto: {e}")
        all_ok = False

    print("Exportacao concluida.")
    return all_ok


def copytree_filtered(src: Path, dst: Path) -> bool:
    """Copia arvore de diretorios filtrando arquivos sensiveis e caches."""
    all_ok = True
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if should_exclude_file(item.name) or should_exclude_dir(item.name):
                continue
            if item.is_file():
                ok = copy_with_redaction(item, dst / item.name)
                if not ok:
                    all_ok = False
            elif item.is_dir():
                ok = copytree_filtered(item, dst / item.name)
                if not ok:
                    all_ok = False
    except Exception as e:
        print(f"[ERRO] Falha ao copiar arvore {src} -> {dst}: {e}")
        return False
    return all_ok


def get_project_data_dirs():
    """Retorna os diretorios de dados que devem ser incluidos no snapshot."""
    base = PROJECT_ROOT
    return {
        "memory": base / "memory",
        "config": base / "config",
        "data": base / "data",
        "lembretes": base / "lembretes",
        "skills": base / "skills",
        "integrations": base / "integrations",
        "identity": base / "core" / "identity",
        "initiative": base / "core" / "initiative",
        "perception": base / "core" / "perception",
    }


def get_project_core_files():
    """Retorna arquivos especificos do core que devem ser incluidos (Task Registry/LAB)."""
    base = PROJECT_ROOT
    core = base / "core"
    return [
        core / "lab_coordinator.py",
        core / "autonomy_lab_bridge.py",
        core / "capability_registry.py",
    ]


def verify_export(snapshot_dir: Path) -> bool:
    """Verifica se o snapshot nao contem segredos obvios."""
    print("\nVerificando exportacao...")
    issues = []

    # Verifica se api_keys.json foi redigido
    api_keys_path = snapshot_dir / "config" / "api_keys.json"
    if api_keys_path.exists():
        try:
            content = api_keys_path.read_text(encoding="utf-8")
            if "«redacted»" not in content and "gemini_api_key" in content:
                if "AIza" in content or "gsk_" in content:
                    issues.append("api_keys.json contem chaves nao redigidas")
        except Exception as e:
            issues.append(f"Nao foi possivel ler api_keys.json para verificacao: {e}")

    # Verifica se NAO existem arquivos de backup sensiveis (exceto api_keys.json principal se redigido)
    for backup_file in snapshot_dir.rglob("*"):
        if backup_file.is_file() and is_sensitive_filename(backup_file.name):
            # Permite api_keys.json se estiver redigido
            if backup_file.name == "api_keys.json":
                try:
                    content = backup_file.read_text(encoding="utf-8")
                    if "«redacted»" in content:
                        continue  # OK, esta redigido
                except Exception:
                    pass
            issues.append(f"Arquivo sensivel nao excluido: {backup_file.relative_to(snapshot_dir)}")

    # Verifica se nao existem caches
    for cache_file in snapshot_dir.rglob("__pycache__"):
        issues.append(f"Cache nao excluido: {cache_file.relative_to(snapshot_dir)}")
    for pyc_file in snapshot_dir.rglob("*.pyc"):
        issues.append(f"Cache .pyc nao excluido: {pyc_file.relative_to(snapshot_dir)}")

    # Verifica memoria exportada
    memory_files = list((snapshot_dir / "memory").glob("*.json"))
    for mf in memory_files:
        try:
            content = mf.read_text(encoding="utf-8").lower()
            if "aiza" in content or "gsk_" in content or " bearer " in content:
                issues.append(f"Memoria exportada pode conter chaves nao redigidas: {mf.name}")
        except Exception:
            pass

    if issues:
        print("PROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f" - {issue}")
        return False
    else:
        print("Nenhum problema obvio de vazamento de segredos detectado.")
        return True


def _is_safe_path(base: Path, target: Path) -> bool:
    """Verifica se target esta dentro de base (protecao contra path traversal)."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def restore_snapshot(snapshot_dir: Path, target_dir: Path, dry_run: bool = True) -> bool:
    """
    Restaura snapshot em pasta limpa com protecao contra path traversal.
    Retorna True se sucesso.
    """
    manifest_path = snapshot_dir / "MANIFEST.json"
    if not manifest_path.exists():
        print(f"[ERRO] Manifesto nao encontrado: {manifest_path}")
        return False

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERRO] Falha ao ler manifesto: {e}")
        return False

    print(f"{'[DRY-RUN] ' if dry_run else ''}Restaurando snapshot de {manifest.get('snapshot_time', 'desconhecido')}")
    print(f"Origem: {manifest.get('source', 'desconhecido')}")
    print(f"Destino: {target_dir}")

    if not target_dir.exists():
        if dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"[DRY-RUN] Diretorio destino criado: {target_dir}")
        else:
            print(f"[ERRO] Diretorio destino nao existe: {target_dir}")
            return False

    # Verifica se o diretorio destino esta "limpo" (so arquivos do projeto)
    existing = list(target_dir.iterdir())
    if existing and not dry_run:
        print(f"[AVISO] Diretorio destino nao esta vazio: {len(existing)} itens existentes")
        # Na restauracao real, poderiamos pedir confirmacao ou limpar

    all_ok = True
    for rel_path_str in manifest.get("contents", []):
        dst = target_dir / rel_path_str

        # PROTECAO CONTRA PATH TRAVERSAL - verifica ANTES de ver se src existe
        if not _is_safe_path(target_dir, dst):
            print(f"[ERRO] Path traversal detectado no manifesto: {rel_path_str} -> fora do destino")
            all_ok = False
            continue

        src = snapshot_dir / rel_path_str
        if not src.exists():
            print(f"[AVISO] Arquivo do manifesto nao encontrado no snapshot: {rel_path_str}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Copiaria: {rel_path_str}")
        else:
            try:
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                print(f"  Restaurado: {rel_path_str}")
            except Exception as e:
                print(f"[ERRO] Falha ao restaurar {rel_path_str}: {e}")
                all_ok = False

    if dry_run:
        print("\n[DRY-RUN] Simulacao concluida. Rode com --restore para executar.")
    else:
        if all_ok:
            print("\nRestauracao concluida com sucesso.")
        else:
            print("\nRestauracao concluida COM ERROS.")

    return all_ok


def audit_existing_snapshots(snapshots_base: Path, quarantine_dir: Path) -> int:
    """
    Audita snapshots existentes e move inseguros para quarantena.
    Retorna numero de snapshots movidos.
    """
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    moved = 0

    for snap_dir in snapshots_base.iterdir():
        if not snap_dir.is_dir():
            continue
        if snap_dir.name.startswith("_"):
            continue

        print(f"\nAuditoria: {snap_dir.name}")
        issues = []

        # Verifica arquivos de backup sensiveis (exceto api_keys.json principal se redigido)
        for backup_file in snap_dir.rglob("*"):
            if backup_file.is_file() and is_sensitive_filename(backup_file.name):
                # Permite api_keys.json se estiver redigido
                if backup_file.name == "api_keys.json":
                    try:
                        content = backup_file.read_text(encoding="utf-8")
                        if "«redacted»" in content:
                            continue  # OK, esta redigido
                    except Exception:
                        pass
                issues.append(f"Arquivo sensivel: {backup_file.relative_to(snap_dir)}")

        # Verifica caches
        for cache_file in snap_dir.rglob("__pycache__"):
            issues.append(f"Cache: {cache_file.relative_to(snap_dir)}")
        for pyc_file in snap_dir.rglob("*.pyc"):
            issues.append(f"Cache .pyc: {pyc_file.relative_to(snap_dir)}")

        # Verifica api_keys.json
        api_keys_path = snap_dir / "config" / "api_keys.json"
        if api_keys_path.exists():
            try:
                content = api_keys_path.read_text(encoding="utf-8")
                if "«redacted»" not in content and ("AIza" in content or "gsk_" in content):
                    issues.append("api_keys.json contem chaves nao redigidas")
            except Exception:
                pass

        if issues:
            print(f"  INSEGURO - {len(issues)} problemas:")
            for issue in issues:
                print(f"   - {issue}")
            # Move para quarantena
            dst = quarantine_dir / snap_dir.name
            if dst.exists():
                dst = quarantine_dir / f"{snap_dir.name}_{datetime.now().strftime('%H%M%S')}"
            shutil.move(str(snap_dir), str(dst))
            print(f"  Movido para: {dst}")
            moved += 1
        else:
            print(f"  SEGURO")

    return moved


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Snapshot ZARA 3.0 - exportacao/restore seguro")
    parser.add_argument("--export", action="store_true", help="Cria novo snapshot")
    parser.add_argument("--verify", type=Path, help="Verifica snapshot existente")
    parser.add_argument("--restore", type=Path, help="Restaura snapshot (requer --target)")
    parser.add_argument("--target", type=Path, help="Diretorio alvo para restore")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simula restore (padrao)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run", help="Executa restore real")
    parser.add_argument("--audit", action="store_true", help="Auditoria snapshots existentes")
    parser.add_argument("--quarantine", type=Path, default=PROJECT_ROOT / "_quarentena" / "snapshots-inseguros", help="Diretorio de quarantena")

    args = parser.parse_args()

    snapshots_base = PROJECT_ROOT / "snapshots"

    if args.audit:
        print("=== AUDITORIA DE SNAPSHOTS EXISTENTES ===")
        moved = audit_existing_snapshots(snapshots_base, args.quarantine)
        print(f"\nTotal movidos para quarantena: {moved}")
        return 0 if moved >= 0 else 1

    if args.verify:
        if not args.verify.exists():
            print(f"[ERRO] Snapshot nao encontrado: {args.verify}")
            return 1
        ok = verify_export(args.verify)
        return 0 if ok else 1

    if args.restore:
        if not args.target:
            print("[ERRO] --target e obrigatorio para --restore")
            return 1
        if not args.restore.exists():
            print(f"[ERRO] Snapshot nao encontrado: {args.restore}")
            return 1
        ok = restore_snapshot(args.restore, args.target, dry_run=args.dry_run)
        return 0 if ok else 1

    if args.export:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot_dir = snapshots_base / f"zara_{timestamp}"
        ok = export_cerebro(snapshot_dir)
        if ok:
            ok = verify_export(snapshot_dir)
        if ok:
            print(f"\nSnapshot criado com sucesso em: {snapshot_dir}")
            return 0
        else:
            print("\nExportacao concluida com problemas.")
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())