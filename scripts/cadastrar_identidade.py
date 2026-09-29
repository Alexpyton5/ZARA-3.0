"""Cadastro das referencias biometricas (FRENTE G - G3).

Fluxo que depende do Alex: ele (e a esposa) precisam fornecer amostras
reais de rosto e voz. Este script guia o passo a passo e grava SOMENTE
o hash do embedding + metadados (nunca imagem/audio cru).

Uso:
    python scripts/cadastrar_identidade.py --papel dono --modalidade voz
    python scripts/cadastrar_identidade.py --papel esposa --modalidade rosto --simulacao

O modo --simulacao completa o fluxo de ponta a ponta para teste, sem
biometria real. Sem ele, o script mostra os passos reais e tenta a
captura pelos provedores reais (ainda nao plugados -> erro honesto).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# bootstrap: raiz do projeto no sys.path (rodar de qualquer cwd)
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.identidade_rosto_voz import (  # noqa: E402
    IdentityGate,
    IdentityStore,
    ProvedorNaoImplementado,
    ProvedorSimulacao,
)

FRASES_VOZ = [
    "ZARA, sou eu.",
    "ZARA, pode me ouvir?",
    "ZARA, sou eu, pode falar.",
]


def _passos_rosto(papel: str) -> None:
    print(f"\n[1] {papel}: fique na frente da camera do PC.")
    print("[2] Olhe direto para a camera, com o rosto bem iluminado.")
    print("[3] Fique parado por 3 segundos a cada captura.")
    print("[4] Serão 3 capturas (frente, leve esquerda, leve direita).")


def _passos_voz(papel: str) -> None:
    print(f"\n[1] {papel}: fique num lugar silencioso.")
    print("[2] Fale em tom normal, como fala com a ZARA todo dia.")
    print("[3] Diga cada frase 1 vez, esperando o sinal:")
    for i, frase in enumerate(FRASES_VOZ, 1):
        print(f"    {i}. \"{frase}\"")


def _capturar_simulacao(modalidade: str, n: int) -> list[bytes]:
    # Amostras FAKE marcadas como simulacao: so para testar o fluxo.
    return [f"simulacao-{modalidade}-{i}".encode() for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cadastra referencia biometrica (rosto/voz) da frente G.")
    ap.add_argument("--papel", required=True, choices=["dono", "esposa"],
                    help="dono = Alex; esposa = usuaria autorizada")
    ap.add_argument("--modalidade", required=True, choices=["rosto", "voz"])
    ap.add_argument("--amostras", type=int, default=3)
    ap.add_argument("--simulacao", action="store_true",
                    help="completa o fluxo com amostras fake (teste)")
    args = ap.parse_args()

    if args.modalidade == "rosto":
        _passos_rosto(args.papel)
    else:
        _passos_voz(args.papel)

    store = IdentityStore()
    if args.simulacao:
        print("\n[modo simulacao: amostras fake, sem biometria real]")
        prov = ProvedorSimulacao()
        amostras = _capturar_simulacao(args.modalidade, args.amostras)
    else:
        print("\n[ERRO HONESTO] Captura real ainda nao plugada.")
        print("Ver docs/identidade-rosto-voz.md, secao 'Provedores reais'.")
        print("Para testar o fluxo: rode com --simulacao.")
        return 2

    gate = IdentityGate(
        store=store,
        prov_rosto=prov if args.modalidade == "rosto" else ProvedorNaoImplementado("rosto"),
        prov_voz=prov if args.modalidade == "voz" else ProvedorNaoImplementado("voz"),
    )
    try:
        tpl = gate.cadastrar(args.papel, args.modalidade, amostras,
                             qualidade=0.9)
    except ValueError as exc:
        print(f"\n[ERRO] {exc}")
        return 1

    print(f"\n[OK] {args.papel}/{args.modalidade} cadastrado:")
    print(f"     modelo={tpl.modelo} amostras={tpl.amostras} "
          f"qualidade={tpl.qualidade}")
    print(f"     guardado em: {store.caminho}")
    print("     (só hash + metadados; nenhum áudio/imagem foi gravado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
