# Contrato de AIProvider — ZARA 3.0

## Interface (definida, não implementada)

```python
class AIProvider(Protocol):
    def generate(self, model_id: str, prompt: str, **kwargs: Any) -> str:
        ...
```

Em `core/ai_provider_contracts.py`. Um `Protocol`, não uma classe base —
qualquer objeto com esse método serve, sem herança forçada.

## Por que não tem implementação ainda

`core/model_router.py` (existente, ver `MODEL_ROUTER_ARCHITECTURE.md`) faz
**seleção** de modelo (qual usar), não **invocação** (chamar a API de
verdade). A invocação real hoje está espalhada em outros pontos do código
que não foram tocados nesta sessão — formalizar isso em adapters
(`GeminiProvider`, `GroqProvider`, etc.) exigiria tocar código de
integração ativo, e o risco de regressão numa madrugada sem Alex por perto
não vale a pena para um contrato que ninguém consome ainda.

## Contrato de dados

```python
@dataclass
class ModelRequest:
    capabilities: list[ModelCapability]
    require_tools: bool = False
    policy: str = "smart"  # "smart" | "economy" | "fast"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ModelResponse:
    model_id: str | None
    provider: str | None
    accepted: bool
    rejection_reason: str | None = None
    fallback_model_ids: list[str] = field(default_factory=list)
```

`ModelResponse` não carrega texto gerado — só a decisão de QUAL modelo usar.
Gerar texto é responsabilidade de um `AIProvider` concreto (a ser escrito),
chamado depois que `select_model()` decidiu o `model_id`.

## Uso correto (quando um AIProvider concreto existir)

```python
resp = select_model(ModelRequest(capabilities=[ModelCapability.REASONING]))
if not resp.accepted:
    # tratar rejeição, tentar fallback_model_ids, ou devolver erro estruturado
    ...
else:
    provider: AIProvider = ...  # implementação concreta, ainda não escrita
    text = provider.generate(resp.model_id, prompt)
```

## O que este contrato PROÍBE por construção

- Ninguém pede um provider específico — só capability. `model_id` é uma
  saída, nunca uma entrada de quem consome `select_model`.
- `select_model()` nunca levanta exceção para "nenhum candidato" — devolve
  `ModelResponse(accepted=False, rejection_reason=...)`, um objeto
  estruturado, sempre tratável sem `try/except` no chamador.
- `select_model()` não abre conexão de rede (testado explicitamente
  substituindo `urllib.request.urlopen` por uma função que levanta erro se
  chamada — `tests/test_ai_provider_contracts.py::test_select_model_never_calls_a_network_api`).
