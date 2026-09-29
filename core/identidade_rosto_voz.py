"""ZARA - Identificacao por rosto/voz (FRENTE G, MISSAO GIGANTE 3).

G1 - DESENHO DO SISTEMA
-----------------------
Toda interacao (voz, chat, remoto) passa pelo IdentityGate ANTES de qualquer
acao. O portao responde UMA pergunta: "quem esta falando comigo?".

    evidencia (rosto + voz) -> IdentityGate.gate_interaction()
        -> autorizado (dono/esposa): segue o fluxo normal
        -> estranho: fala "você é um estranho" e IGNORA (latch de sessao)
        -> nao_cadastrado: cadastro ainda nao feito pelo Alex -> passa
           (comportamento de hoje), com aviso em log. DECISAO DOCUMENTADA:
           o cadastro depende do Alex (G3); travar o app antes disso
           quebraria o uso dele.

Threat model (nota do engenheiro de identidade):
- Atacante considerado: pessoa desconhecida falando com o assistente.
- Fora de escopo nesta versao: replay de voz gravada (mitigacao futura:
  frase-desafio aleatoria + liveness da camera). Nao e cofre de banco,
  e protecao domestica.
- Regra dura: NUNCA gravar imagem/audio cru no disco. So hash SHA-256 do
  embedding + metadados do modelo (modelo, versao, dimensao, qualidade).
- Regra dura: NUNCA inventar referencia biometrica. O store nasce VAZIO.

Fusao rosto+voz: cada pessoa cadastrada recebe a MAIOR pontuacao entre as
modalidades com evidencia disponivel. Limiares padrao (cosine 0..1):
rosto >= 0.60, voz >= 0.55. Faixa ambigua [limiar-0.15, limiar) = ESTRANHO
(fail-closed dentro do subsistema de identidade).

Provedores: a comparacao real (ONNX de rosto, embedding de locutor) e
plugavel via ProvedorRosto/ProvedorVoz. ProvedorSimulacao existe SOMENTE
para testes/desenvolvimento e se identifica como tal.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

try:  # pragma: no cover - import defensivo: o portao nunca quebra o app
    from core.paths import user_data_dir
except Exception:  # pragma: no cover
    user_data_dir = None  # type: ignore[assignment]

try:  # pragma: no cover
    from core.audit_log import audit_log
except Exception:  # pragma: no cover
    audit_log = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constantes de contrato (G2)
# ---------------------------------------------------------------------------

#: Frase EXATA dita para desconhecido. Nao alterar sem decisao do Alex.
FRASE_ESTRANHO = "você é um estranho"

#: Papeis validos no cadastro. "dono" = Alex; "esposa" = usuaria autorizada.
PAPEIS_VALIDOS = ("dono", "esposa")

NOMES_EXIBICAO = {"dono": "Alex", "esposa": "esposa"}

MODALIDADES = ("rosto", "voz")

LIMIAR_ROSTO = 0.60
LIMIAR_VOZ = 0.55
FAIXA_AMBIGUA = 0.15  # abaixo do limiar -> ainda assim estranho (fail-closed)

MIN_AMOSTRAS_CADASTRO = 3
QUALIDADE_MINIMA = 0.5

ARQUIVO_REFERENCIAS = "referencias.json"


# ---------------------------------------------------------------------------
# Modelos de dados (só metadados + hash; NUNCA biométrico cru)
# ---------------------------------------------------------------------------

@dataclass
class TemplateBiometrico:
    """Referencia biometrica de UMA modalidade de UMA pessoa.

    Guarda apenas o hash SHA-256 do embedding (bytes) e os metadados do
    modelo que o gerou. Imagem e audio crus jamais tocam o disco.
    """

    modalidade: str
    modelo: str
    dimensao: int
    hash_embedding: str
    qualidade: float
    amostras: int
    cadastrado_em: str = ""
    papel: str = ""  # dono da referencia (permite ao provedor simular por pessoa)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TemplateBiometrico":
        return cls(**{k: d.get(k, "") for k in
                      ("modalidade", "modelo", "dimensao", "hash_embedding",
                       "qualidade", "amostras", "cadastrado_em", "papel")})


@dataclass
class PessoaCadastrada:
    papel: str
    nome_exibicao: str
    rosto: TemplateBiometrico | None = None
    voz: TemplateBiometrico | None = None

    def to_dict(self) -> dict:
        return {
            "papel": self.papel,
            "nome_exibicao": self.nome_exibicao,
            "rosto": self.rosto.to_dict() if self.rosto else None,
            "voz": self.voz.to_dict() if self.voz else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PessoaCadastrada":
        def _t(v):
            return TemplateBiometrico.from_dict(v) if v else None
        return cls(
            papel=d.get("papel", ""),
            nome_exibicao=d.get("nome_exibicao", ""),
            rosto=_t(d.get("rosto")),
            voz=_t(d.get("voz")),
        )


def _hash_embedding(embedding: bytes, modelo: str) -> str:
    """Hash SHA-256 do embedding. O embedding cru nunca e persistido."""
    h = hashlib.sha256()
    h.update(modelo.encode("utf-8"))
    h.update(b"\x00")
    h.update(embedding)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Store persistente (JSON; nasce VAZIO - G3 depende do Alex)
# ---------------------------------------------------------------------------

class IdentityStore:
    """Persistencia das referencias biometricas cadastradas."""

    def __init__(self, caminho: Path | None = None):
        if caminho is None:
            base = user_data_dir() if user_data_dir else Path.home()
            caminho = Path(base) / "data" / "identidade" / ARQUIVO_REFERENCIAS
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._pessoas: dict[str, PessoaCadastrada] = {}
        self._carregar()

    def _carregar(self) -> None:
        try:
            if self.caminho.exists():
                dados = json.loads(self.caminho.read_text(encoding="utf-8"))
                for papel, d in (dados.get("pessoas") or {}).items():
                    if papel in PAPEIS_VALIDOS:
                        self._pessoas[papel] = PessoaCadastrada.from_dict(d)
        except Exception:
            self._pessoas = {}

    def _persistir(self) -> None:
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"pessoas": {p: v.to_dict()
                                   for p, v in self._pessoas.items()}},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.caminho)

    def pessoas(self) -> dict[str, PessoaCadastrada]:
        return dict(self._pessoas)

    def obter(self, papel: str) -> PessoaCadastrada | None:
        return self._pessoas.get(papel)

    def algum_cadastro(self) -> bool:
        return any(
            p.rosto is not None or p.voz is not None
            for p in self._pessoas.values()
        )

    def salvar(self, pessoa: PessoaCadastrada) -> None:
        if pessoa.papel not in PAPEIS_VALIDOS:
            raise ValueError(f"papel invalido: {pessoa.papel!r}")
        self._pessoas[pessoa.papel] = pessoa
        self._persistir()

    def remover(self, papel: str, modalidade: str | None = None) -> bool:
        """Remove cadastro (LGPD: direito de apagar dado biometrico)."""
        pessoa = self._pessoas.get(papel)
        if pessoa is None:
            return False
        if modalidade is None:
            del self._pessoas[papel]
        elif modalidade == "rosto":
            pessoa.rosto = None
        elif modalidade == "voz":
            pessoa.voz = None
        else:
            return False
        self._persistir()
        return True


# ---------------------------------------------------------------------------
# Provedores (comparacao). Real = plugavel; Simulacao = so p/ teste.
# ---------------------------------------------------------------------------

class ProvedorBiometrico(Protocol):
    def cadastrar(self, amostras: list[bytes], qualidade: float) -> TemplateBiometrico: ...
    def pontuar(self, amostra: bytes, template: TemplateBiometrico) -> float: ...


class ProvedorSimulacao:
    """DEV/TESTE APENAS. Retorna pontuacoes injetadas, sem biometria real.

    Nao usar em producao: nao mede nada, so repete o mapa configurado.
    """

    SIMULACAO = True

    def __init__(self, mapa: dict[tuple[str, str], float] | None = None,
                 modelo: str = "simulacao/v0"):
        self.mapa = dict(mapa or {})
        self.modelo = modelo

    def cadastrar(self, amostras: list[bytes], qualidade: float = 0.9) -> TemplateBiometrico:
        digest = hashlib.sha256(b"|".join(amostras)).digest()
        return TemplateBiometrico(
            modalidade="simulacao",
            modelo=self.modelo,
            dimensao=len(digest),
            hash_embedding=_hash_embedding(digest, self.modelo),
            qualidade=qualidade,
            amostras=len(amostras),
            cadastrado_em=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def pontuar(self, amostra: bytes, template: TemplateBiometrico) -> float:
        return float(self.mapa.get((template.papel, template.modalidade), 0.0))


class ProvedorNaoImplementado:
    """Placeholder honesto do provedor real (ONNX/embedding de locutor).

    Levanta erro explicativo em vez de fingir que mediu algo (frente C).
    """

    def __init__(self, modalidade: str):
        self.modalidade = modalidade

    def _erro(self) -> RuntimeError:
        return RuntimeError(
            f"provedor real de {self.modalidade} ainda nao plugado; "
            "ver docs/identidade-rosto-voz.md (secao 'Provedores reais'). "
            "Use ProvedorSimulacao apenas em teste."
        )

    def cadastrar(self, amostras: list[bytes], qualidade: float = 0.0) -> TemplateBiometrico:
        raise self._erro()

    def pontuar(self, amostra: bytes, template: TemplateBiometrico) -> float:
        raise self._erro()


# ---------------------------------------------------------------------------
# O portao (G2)
# ---------------------------------------------------------------------------

@dataclass
class Decisao:
    decisao: str  # autorizado | estranho | nao_cadastrado | sem_evidencia
    pessoa: str | None = None
    confianca: float = 0.0
    fala: str | None = None
    ignorar: bool = False
    motivo: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class IdentityGate:
    """Portao de identificacao na entrada de qualquer interacao."""

    def __init__(
        self,
        store: IdentityStore | None = None,
        prov_rosto: Any = None,
        prov_voz: Any = None,
        modo_estrito: bool = False,
    ):
        self.store = store or IdentityStore()
        self.prov_rosto = prov_rosto or ProvedorNaoImplementado("rosto")
        self.prov_voz = prov_voz or ProvedorNaoImplementado("voz")
        #: modo_estrito=True: sem evidencia biometrica com cadastro existente
        #: = estranho. False (padrao): passa com aviso em log.
        self.modo_estrito = modo_estrito
        self._estranho_latch = False
        self._aviso_sem_cadastro_dado = False

    # -- auditoria ------------------------------------------------------
    def _audit(self, acao: str, risco: str, resultado: str,
               erro: str | None = None) -> None:
        try:
            if audit_log is not None:
                audit_log().record(f"identidade.{acao}", risco, resultado, erro)
        except Exception:
            pass  # auditoria nunca quebra o portao

    # -- G3: cadastro ----------------------------------------------------
    def cadastrar(self, papel: str, modalidade: str,
                  amostras: list[bytes],
                  qualidade: float = 0.9) -> TemplateBiometrico:
        """Cadastra a referencia biometrica (fluxo do G3, depende do Alex).

        Nao inventa dados: exige amostras reais vindas do fluxo de cadastro.
        """
        if papel not in PAPEIS_VALIDOS:
            raise ValueError(f"papel invalido: {papel!r} (use {PAPEIS_VALIDOS})")
        if modalidade not in MODALIDADES:
            raise ValueError(f"modalidade invalida: {modalidade!r}")
        if len(amostras) < MIN_AMOSTRAS_CADASTRO:
            raise ValueError(
                f"cadastro exige >= {MIN_AMOSTRAS_CADASTRO} amostras "
                f"(recebido {len(amostras)})"
            )
        if not (0.0 <= qualidade <= 1.0) or qualidade < QUALIDADE_MINIMA:
            raise ValueError(
                f"qualidade insuficiente: {qualidade} "
                f"(minimo {QUALIDADE_MINIMA})"
            )
        prov = self.prov_rosto if modalidade == "rosto" else self.prov_voz
        template = prov.cadastrar(amostras, qualidade)
        template.modalidade = modalidade
        template.papel = papel
        pessoa = self.store.obter(papel) or PessoaCadastrada(
            papel=papel, nome_exibicao=NOMES_EXIBICAO[papel])
        if modalidade == "rosto":
            pessoa.rosto = template
        else:
            pessoa.voz = template
        self.store.salvar(pessoa)
        self._audit("cadastro", "HIGH", "ok",
                    f"{papel}/{modalidade} {template.amostras} amostras")
        return template

    # -- verificacao ------------------------------------------------------
    def _limiar(self, modalidade: str) -> float:
        return LIMIAR_ROSTO if modalidade == "rosto" else LIMIAR_VOZ

    def verificar(self, evidencia: dict) -> Decisao:
        """Compara evidencia {rosto: bytes|None, voz: bytes|None} com o cadastro."""
        if not self.store.algum_cadastro():
            if not self._aviso_sem_cadastro_dado:
                self._aviso_sem_cadastro_dado = True
                print("[IDENTIDADE] sem referencias cadastradas: portao em "
                      "modo nao_cadastrado (passa tudo). Cadastre com "
                      "scripts/cadastrar_identidade.py", flush=True)
            return Decisao(decisao="nao_cadastrado",
                           motivo="nenhuma referencia cadastrada")

        amostra_rosto = evidencia.get("rosto")
        amostra_voz = evidencia.get("voz")
        if amostra_rosto is None and amostra_voz is None:
            if self.modo_estrito:
                self._audit("sem_evidencia", "MEDIUM", "estranho",
                            "modo estrito sem evidencia")
                return Decisao(decisao="estranho", confianca=0.0,
                               motivo="modo estrito sem evidencia")
            self._audit("sem_evidencia", "LOW", "pass",
                        "sem amostra biometrica")
            return Decisao(decisao="sem_evidencia",
                           motivo="sem amostra biometrica")

        melhor_papel: str | None = None
        melhor_score = 0.0
        ambigua = False

        for papel, pessoa in self.store.pessoas().items():
            for modalidade, amostra in (("rosto", amostra_rosto),
                                        ("voz", amostra_voz)):
                template = pessoa.rosto if modalidade == "rosto" else pessoa.voz
                if template is None or amostra is None:
                    continue
                prov = self.prov_rosto if modalidade == "rosto" else self.prov_voz
                try:
                    score = float(prov.pontuar(amostra, template))
                except Exception as exc:
                    self._audit("falha_provedor", "MEDIUM", "erro",
                                f"{modalidade}: {exc}")
                    continue
                limiar = self._limiar(modalidade)
                if score >= limiar and score > melhor_score:
                    melhor_papel, melhor_score = papel, score
                elif limiar - FAIXA_AMBIGUA <= score < limiar:
                    ambigua = True  # fail-closed: quase-passou = estranho

        if melhor_papel is not None:
            return Decisao(decisao="autorizado", pessoa=melhor_papel,
                           confianca=melhor_score,
                           motivo=f"match {melhor_score:.2f}")
        self._audit("nao_reconhecido", "MEDIUM", "estranho",
                    "ambigua" if ambigua else "sem match")
        return Decisao(decisao="estranho", confianca=melhor_score,
                       motivo="ambigua" if ambigua else "sem match")

    # -- G2: o portao na entrada da interacao ------------------------------
    def gate_interaction(self, evidencia: dict | None = None) -> Decisao:
        """Ponto unico de entrada. Retorna o que fazer com a interacao.

        - autorizado     -> seguir o fluxo normal (ignorar=False)
        - estranho       -> falar FRASE_ESTRANHO (1x) e ignorar tudo
        - nao_cadastrado -> cadastro pendente: passa como hoje
        - sem_evidencia  -> passa (ou estranho no modo estrito)
        """
        veredito = self.verificar(evidencia or {})

        if veredito.decisao == "autorizado":
            if self._estranho_latch:
                self._estranho_latch = False
                self._audit("latch_liberado", "LOW", "ok",
                            f"pessoa reconhecida: {veredito.pessoa}")
            self._audit("ok", "LOW", "pass", veredito.pessoa or "")
            veredito.ignorar = False
            return veredito

        if veredito.decisao == "estranho":
            if self._estranho_latch:
                # Ja avisou: ignora em silencio, sem repetir a frase.
                veredito.fala = None
            else:
                self._estranho_latch = True
                veredito.fala = FRASE_ESTRANHO  # frase EXATA, 1x
            veredito.ignorar = True
            self._audit("estranho", "HIGH",
                        "frase" if veredito.fala else "ignorado",
                        veredito.motivo)
            return veredito

        # nao_cadastrado / sem_evidencia: nao trava o app.
        veredito.ignorar = False
        return veredito

    def resetar_latch(self) -> None:
        """Libera manualmente o latch de estranho (uso em teste/suporte)."""
        self._estranho_latch = False

    @property
    def estranho_ativo(self) -> bool:
        return self._estranho_latch


def gate() -> IdentityGate:
    """Fabrica padrao do portao (provedores reais ainda nao plugados)."""
    return IdentityGate()
