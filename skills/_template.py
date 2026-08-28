"""
Skill para Zara — estilo Mark-LI.
Copie este arquivo, renomeie (sem underscore inicial), preencha PLUGIN e run().
"""

PLUGIN = {
    "name": "minha_skill",                    # snake_case, único, ^[a-zA-Z_][a-zA-Z0-9_]{0,63}$
    "description": (
        "Uma ou duas frases que a Zara usa para decidir quando chamar. "
        "Seja explícito sobre gatilhos e, se puder confundir com outra skill, "
        "diga qual NÃO usar no lugar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "exemplo_arg": {"type": "STRING", "description": "O que este argumento significa"},
        },
        "required": [],   # vazio para skill sem argumentos
    },
    "category": "general",    # general, system, web, files, code, media, etc.
    "version": "1.0.0",
    "author": "seu_nome",
}

def run(parameters: dict, context=None) -> str:
    """
    parameters: dict com args que a Zara extraiu, batendo com PLUGIN['parameters'].
    context: objeto com acesso a voz, tela, memória, config — use context.falar(), context.memoria, etc.
    Retorna string curta em linguagem natural — isso é falado de volta pro usuário.
    Nunca levante exceção: capture seus erros e retorne string de erro falável.
    """
    exemplo_arg = parameters.get("exemplo_arg", "")
    try:
        resultado = f"Fiz a coisa com {exemplo_arg}."
    except Exception as e:
        return f"Minha skill falhou: {e}"
    if context and hasattr(context, "log"):
        context.log(f"Zara: {resultado}")
    return resultado
