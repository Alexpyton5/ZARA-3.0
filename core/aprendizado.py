"""ZARA-APRENDIZADO-001 — ela aprende com o que faz, todo dia.

Alex: "eu quero que ela possa aprender todos os dias com tudo que ela ouve, com
tudo que ela vê, com tudo que eu mando ela fazer, e que ela comece a ganhar
consciência: olha, eu fiz isso, eu aprendi aquilo, agora eu posso usar isso em
tal situação."

**O que isto é, sem misticismo.** Não é consciência. É memória de experiência:
ela registra o que foi pedido, o que ela fez, se deu certo, e como Alex reagiu.
Com isso ela para de repetir erro — que é a diferença prática entre um executor
de comando e algo que aprende.

**Por que sem IA.** A tentação é mandar um modelo "aprender" da conversa. Isso
gasta token em toda frase, inventa padrão onde não há, e some quando o app
fecha. O sinal que importa é barato e explícito: logo depois de uma ação, Alex
ou segue em frente (deu certo) ou reclama (deu errado). Reclamação em português
tem marcador claro. Reconhecer isso custa microssegundos e não erra quase nunca.

**O ciclo:**

    pedido -> ação -> resultado -> reação do Alex -> lição

A lição fica presa à FORMA do pedido, não à frase exata, para valer da próxima
vez que ele disser a mesma coisa com outras palavras.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

from core.paths import user_data_dir

# Reclamação logo depois de uma ação = a ação estava errada.
_RECLAMACAO = (
    r"\bn[ãa]o\s+(?:[ée]\s+)?(?:isso|isto|era|foi)\b",
    r"\bn[ãa]o\s+(?:foi|era)\s+(?:isso|isto|o\s+que)\b",
    r"\berrad[oa]\b",
    r"\bn[ãa]o\s+(?:e|é)\s+bem\s+isso\b",
    r"\bnem\s+era\s+isso\b",
    r"\bde\s+novo\b.*\bn[ãa]o\b",
    r"\bpedi\s+(?:outra|outro|foi)\b",
    r"\bnada\s+(?:aconteceu|mudou)\b",
    r"\bn[ãa]o\s+(?:funcionou|fez|executou|mudou|aconteceu)\b",
    r"\bcontinua\s+(?:igual|do\s+mesmo\s+jeito|a\s+mesma)\b",
)

# Elogio logo depois = confirma que aquela leitura estava certa.
_APROVACAO = (
    r"\b(?:isso|perfeito|exato|isso\s+mesmo|boa|ótimo|otimo|show|funcionou|deu\s+certo)\b",
    r"\bagora\s+sim\b",
    r"\bera\s+isso\b",
)

# Quanto tempo depois da ação a reação ainda conta como reação àquela ação.
_JANELA_DE_REACAO = 90.0


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in base if not unicodedata.combining(c))


def _forma_do_pedido(texto: str) -> str:
    """Reduz a frase à sua FORMA, para casar de novo com outras palavras.

    "abaixa o volume aí" e "diminui esse volume" viram a mesma chave. Sem isso
    a lição só valeria para a frase idêntica, e nunca seria usada.
    """
    limpo = _sem_acento(texto)
    palavras = re.findall(r"[a-z0-9]{3,}", limpo)
    vazias = {"que", "para", "por", "com", "uma", "meu", "minha", "isso", "isto",
              "essa", "esse", "the", "zara", "ai", "aqui", "agora", "pra"}
    uteis = sorted({p[:5] for p in palavras if p not in vazias})
    return " ".join(uteis[:8])


class Aprendizado:
    """Diário de experiências da ZARA. Determinístico e barato."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (user_data_dir() / "data" / "aprendizado" / "experiencias.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ultimo: dict | None = None  # última ação, à espera da reação
        self._criar()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _criar(self) -> None:
        with self._lock, self._conectar() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quando REAL NOT NULL,
                    pedido TEXT NOT NULL,
                    forma TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    sucesso INTEGER NOT NULL,
                    resultado TEXT,
                    origem TEXT,
                    reacao TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS licoes (
                    forma TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    acertos INTEGER NOT NULL DEFAULT 0,
                    erros INTEGER NOT NULL DEFAULT 0,
                    ultima REAL NOT NULL,
                    exemplo TEXT,
                    PRIMARY KEY (forma, acao)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_ep_quando ON episodios(quando)")

    # ------------------------------------------------------------------
    def registrar_acao(self, pedido: str, acao: str, sucesso: bool,
                       resultado: str = "", origem: str = "voz") -> int | None:
        """Anota o que ela acabou de fazer, e fica à espera da reação do Alex."""
        pedido = " ".join(str(pedido or "").split())
        if not pedido or not acao:
            return None
        forma = _forma_do_pedido(pedido)
        agora = time.time()
        try:
            with self._lock, self._conectar() as conn:
                cur = conn.execute(
                    "INSERT INTO episodios (quando, pedido, forma, acao, sucesso, resultado, origem)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (agora, pedido, forma, acao, 1 if sucesso else 0,
                     str(resultado or "")[:400], origem),
                )
                rid = int(cur.lastrowid)
        except Exception:
            return None
        self._ultimo = {"id": rid, "forma": forma, "acao": acao,
                        "quando": time.monotonic(), "pedido": pedido}
        return rid

    def observar_reacao(self, fala: str) -> str | None:
        """Lê a próxima fala do Alex como nota da ação anterior.

        Devolve "corrigiu", "aprovou" ou None. Só vale dentro da janela: uma
        reclamação dez minutos depois é sobre outra coisa.
        """
        pendente = self._ultimo
        if not pendente:
            return None
        if time.monotonic() - pendente["quando"] > _JANELA_DE_REACAO:
            self._ultimo = None
            return None

        texto = _sem_acento(fala)
        if not texto.strip():
            return None

        if any(re.search(p, texto) for p in _RECLAMACAO):
            veredito = "corrigiu"
        elif any(re.search(p, texto) for p in _APROVACAO) and len(texto) < 60:
            veredito = "aprovou"
        else:
            return None

        self._ultimo = None
        self._anotar_licao(pendente, veredito, fala)
        return veredito

    def _anotar_licao(self, episodio: dict, veredito: str, fala: str) -> None:
        campo = "erros" if veredito == "corrigiu" else "acertos"
        try:
            with self._lock, self._conectar() as conn:
                conn.execute(
                    "UPDATE episodios SET reacao=? WHERE id=?", (veredito, episodio["id"])
                )
                conn.execute(
                    f"""INSERT INTO licoes (forma, acao, {campo}, ultima, exemplo)
                        VALUES (?,?,1,?,?)
                        ON CONFLICT(forma, acao) DO UPDATE SET
                            {campo} = {campo} + 1, ultima = excluded.ultima""",
                    (episodio["forma"], episodio["acao"], time.time(), episodio["pedido"][:200]),
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    def licao_para(self, pedido: str) -> dict | None:
        """Antes de agir: já erramos com essa forma de pedido antes?"""
        forma = _forma_do_pedido(pedido)
        if not forma:
            return None
        try:
            with self._lock, self._conectar() as conn:
                linha = conn.execute(
                    "SELECT * FROM licoes WHERE forma=? ORDER BY erros DESC LIMIT 1", (forma,)
                ).fetchone()
        except Exception:
            return None
        if linha is None or linha["erros"] <= linha["acertos"]:
            return None
        return {"acao": linha["acao"], "erros": linha["erros"],
                "acertos": linha["acertos"], "exemplo": linha["exemplo"]}

    def o_que_aprendeu(self, desde_horas: float = 24.0, limite: int = 8) -> list[dict]:
        """Para Alex poder perguntar: 'o que você aprendeu hoje?'"""
        corte = time.time() - desde_horas * 3600
        try:
            with self._lock, self._conectar() as conn:
                linhas = conn.execute(
                    "SELECT forma, acao, acertos, erros, exemplo FROM licoes"
                    " WHERE ultima >= ? ORDER BY (erros + acertos) DESC LIMIT ?",
                    (corte, limite),
                ).fetchall()
        except Exception:
            return []
        return [dict(linha) for linha in linhas]

    # ------------------------------------------------------------------
    # ZARA-DIARIO-001 — o fechamento do dia.
    #
    # Alex: "no final do dia tivesse um momento onde ela reunisse todas as
    # informações e colocasse como novas experiências... que todo dia ela
    # crescesse em relação à memória dela, consciência de quem ela é, o que ela
    # é, pra que ela serve, as coisas que eu gosto, como eu funciono".
    #
    # É o mesmo ritual que eu tenho: no fim do dia, reler o que aconteceu e
    # guardar o que sobrou. A diferença é que aqui NADA é inventado — cada linha
    # do diário sai de episódio registrado. Um diário que inventa aprendizado
    # seria pior que não ter diário: ela passaria a "saber" coisas falsas.
    def fechar_o_dia(self, desde_horas: float = 24.0) -> dict:
        """Reúne o dia numa página do diário e devolve o que foi guardado."""
        resumo = self.resumo_do_dia(desde_horas)
        licoes = self.o_que_aprendeu(desde_horas, limite=12)

        acertou = [le for le in licoes if le["acertos"] > le["erros"]]
        errou = [le for le in licoes if le["erros"] > le["acertos"]]

        with self._lock, self._conectar() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS diario (
                    dia INTEGER PRIMARY KEY,
                    quando REAL NOT NULL,
                    acoes INTEGER, certas INTEGER, corrigidas INTEGER,
                    aprendi TEXT, errei TEXT
                )
            """)
            anterior = conn.execute("SELECT MAX(dia) d FROM diario").fetchone()["d"]
            dia = int(anterior or 0) + 1
            conn.execute(
                "INSERT INTO diario (dia, quando, acoes, certas, corrigidas, aprendi, errei)"
                " VALUES (?,?,?,?,?,?,?)",
                (dia, time.time(), resumo["acoes"], resumo["certas"], resumo["corrigidas"],
                 " | ".join(le["exemplo"] or le["forma"] for le in acertou[:6]),
                 " | ".join(le["exemplo"] or le["forma"] for le in errou[:6])),
            )

        return {"dia": dia, **resumo,
                "aprendi": [le["exemplo"] or le["forma"] for le in acertou[:6]],
                "errei": [le["exemplo"] or le["forma"] for le in errou[:6]]}

    def fechar_o_dia_se_preciso(self) -> dict | None:
        """Fecha o dia sozinha, quando vira o dia. ZARA-DIARIO-002.

        Alex: "isso funcione de forma orgânica, natural... ela faz um resumo
        sozinha, automática". Um ritual que depende de alguém lembrar de pedir
        não é ritual — é mais uma tarefa para ele.

        Fecha no máximo uma vez por dia de calendário, e só se algo aconteceu.
        """
        ultima = self.historia(limite=1)
        agora = time.time()
        if ultima:
            fechado_em = time.localtime(ultima[0]["quando"])
            hoje = time.localtime(agora)
            mesmo_dia = (fechado_em.tm_year, fechado_em.tm_yday) == (hoje.tm_year, hoje.tm_yday)
            if mesmo_dia:
                return None
        if self.resumo_do_dia(desde_horas=36.0)["acoes"] == 0:
            return None  # dia vazio não vira página
        return self.fechar_o_dia(desde_horas=36.0)

    def absorver_do_projeto(self, texto: str, fonte: str = "claude") -> str | None:
        """Aprende o ESTADO do projeto lendo o que Claude e Codex escrevem.

        Alex: "até nas minhas conversas com você, ela podia tirar aprendizado
        de: o que é que ele está construindo? pra ela saber em que nível ela
        está e pra onde a gente está indo."

        Guarda só frases de DECISÃO ou RESULTADO — "consertei", "está pronto",
        "não funciona". Absorver tudo encheria a memória de raciocínio técnico
        que não a ajuda em nada.
        """
        limpo = " ".join(str(texto or "").split())
        if not (25 <= len(limpo) <= 300):
            return None
        marcadores = (
            r"\b(?:consertei|corrigi|constru[íi]|criei|implementei|removi|troquei)\b",
            r"\b(?:est[áa]\s+pronto|funcionou|passou\s+a\s+funcionar|resolvido)\b",
            r"\b(?:n[ãa]o\s+funciona|falhou|quebrou|est[áa]\s+quebrado)\b",
            r"\b(?:agora\s+ela|a\s+partir\s+de\s+agora\s+ela)\b",
        )
        alvo = _sem_acento(limpo)
        if not any(re.search(m, alvo) for m in marcadores):
            return None

        try:
            with self._lock, self._conectar() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS projeto (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quando REAL NOT NULL, fonte TEXT, fato TEXT NOT NULL UNIQUE
                    )
                """)
                conn.execute(
                    "INSERT OR IGNORE INTO projeto (quando, fonte, fato) VALUES (?,?,?)",
                    (time.time(), fonte, limpo[:300]),
                )
        except Exception:
            return None
        return limpo[:300]

    def onde_estamos(self, limite: int = 6) -> list[str]:
        """O que ela sabe do rumo do projeto, pelo que leu."""
        try:
            with self._lock, self._conectar() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS projeto (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quando REAL NOT NULL, fonte TEXT, fato TEXT NOT NULL UNIQUE
                    )
                """)
                linhas = conn.execute(
                    "SELECT fato FROM projeto ORDER BY quando DESC LIMIT ?", (limite,)
                ).fetchall()
        except Exception:
            return []
        return [linha["fato"] for linha in linhas]

    def historia(self, limite: int = 30) -> list[dict]:
        """Os dias já fechados — a memória que cresce."""
        try:
            with self._lock, self._conectar() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS diario (
                        dia INTEGER PRIMARY KEY, quando REAL NOT NULL,
                        acoes INTEGER, certas INTEGER, corrigidas INTEGER,
                        aprendi TEXT, errei TEXT
                    )
                """)
                linhas = conn.execute(
                    "SELECT * FROM diario ORDER BY dia DESC LIMIT ?", (limite,)
                ).fetchall()
        except Exception:
            return []
        return [dict(linha) for linha in linhas]

    def contar_o_que_aprendeu(self, desde_horas: float = 24.0) -> str:
        """A frase que ela fala quando Alex pergunta 'o que você aprendeu?'."""
        resumo = self.resumo_do_dia(desde_horas)
        if not resumo["acoes"]:
            return "Hoje eu ainda não fiz nada que valesse aprender."

        partes = [
            f"Hoje eu executei {resumo['acoes']} "
            f"{'ação' if resumo['acoes'] == 1 else 'ações'}, "
            f"{resumo['certas']} deram certo."
        ]
        if resumo["corrigidas"]:
            partes.append(
                f"Você me corrigiu {resumo['corrigidas']} "
                f"{'vez' if resumo['corrigidas'] == 1 else 'vezes'}, e eu guardei cada uma."
            )
        licoes = self.o_que_aprendeu(desde_horas, limite=3)
        errou = [le for le in licoes if le["erros"] > le["acertos"]]
        if errou:
            exemplo = errou[0]["exemplo"] or errou[0]["forma"]
            partes.append(f"O que eu mais errei foi quando você pede assim: {exemplo}.")
        dias = self.historia(limite=1)
        if dias:
            partes.append(f"Estou no dia {dias[0]['dia'] + 1} de convivência com você.")
        return " ".join(partes)

    def resumo_do_dia(self, desde_horas: float = 24.0) -> dict:
        corte = time.time() - desde_horas * 3600
        try:
            with self._lock, self._conectar() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) c FROM episodios WHERE quando >= ?", (corte,)
                ).fetchone()["c"]
                ok = conn.execute(
                    "SELECT COUNT(*) c FROM episodios WHERE quando >= ? AND sucesso=1", (corte,)
                ).fetchone()["c"]
                corrigidas = conn.execute(
                    "SELECT COUNT(*) c FROM episodios WHERE quando >= ? AND reacao='corrigiu'",
                    (corte,),
                ).fetchone()["c"]
        except Exception:
            return {"acoes": 0, "certas": 0, "corrigidas": 0}
        return {"acoes": int(total), "certas": int(ok), "corrigidas": int(corrigidas)}
