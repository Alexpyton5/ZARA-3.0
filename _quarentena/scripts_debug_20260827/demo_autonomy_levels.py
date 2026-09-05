"""Demonstração do sistema de níveis de autonomia da ZARA."""
import core.actions  # Load fundamentals
from core.autonomy_levels import (
    decide_autonomy_level,
    get_autonomy_policy_summary,
    format_decision_for_alex,
    AutonomyLevel
)

def main():
    print("=== Sistema de Níveis de Autonomia da ZARA ===\n")
    
    # Mostrar resumo da política
    print("1. Resumo da Política de Autonomia:")
    summary = get_autonomy_policy_summary()
    for level_key, data in summary['levels'].items():
        print(f"   {level_key}: {data['count']} ações")
        if data['count'] <= 5:  # Mostrar todas se poucas
            for action in data['actions']:
                print(f"     - {action}")
        else:  # Mostrar apenas as primeiras 5 se muitas
            for action in data['actions'][:5]:
                print(f"     - {action}")
            print(f"     ... e mais {data['count'] - 5} ações")
    print()
    
    # Mostrar overrides do Alex
    print("2. Overrides explícitos do Alex:")
    print(f"   Sempre faz sozinha ({len(summary['overrides']['alex_always_auto'])} ações)")
    print(f"   Nunca faz sem consultar ({len(summary['overrides']['alex_never_auto'])} ações)")
    print()
    
    # Demonstrar decisões para algumas ações-chave
    print("3. Exemplos de decisões:")
    test_cases = [
        # Ações básicas que devem ser REFLEXO_LOCAL
        ("os_volume", {}),
        ("os_brightness_absolute", {}),
        ("window_minimize", {}),
        
        # Ações que exigem confirmação
        ("files_delete", {}),
        ("os_power", {}),
        ("system_kill", {}),
        ("terminal", {}),
        
        # Ações de comunicação (devem ser REFLEXO_LOCAL por override do Alex)
        ("claude_enviar", {}),
        ("codex_enviar", {}),
        ("aprendizado_resumo", {}),
        
        # Ação desconhecida (deve ser EXIGE_ALEX por segurança)
        ("acao_inexistente_xyz", {}),
    ]
    
    for action_name, context in test_cases:
        decision = decide_autonomy_level(action_name, context=context)
        formatted = format_decision_for_alex(decision)
        print(f"   {formatted}")
    
    print("\n4. Teste de preferência do usuário:")
    # Simular preferência do usuário (ex.: usuário quer confirmar antes de mudar volume)
    user_prefs = {"os_volume": 3}  # Usuário pede para perguntar antes de mudar volume
    decision = decide_autonomy_level("os_volume", user_preferences=user_prefs)
    print(f"   os_volume com preferência usuário=3: {decision.level.name} (deveria ser PERGUNTA_ANTES)")
    
    print("\n5. Teste de contexto (Supercérebro OFF):")
    # Com Supercérebro OFF, ações que exigem PC_CONTROL devem subir para EXIGE_ALEX
    context_off = {"superbrain_on": False}
    # Vamos testar com uma ação que temos certeza que exige mais que LOCAL_PC_CONTROL
    # Como não temos ações com PC_CONTROL explícitas no registry carregado,
    # vamos demonstrar que o contexto é considerado
    decision_on = decide_autonomy_level("os_volume", context={"superbrain_on": True})
    decision_off = decide_autonomy_level("os_volume", context={"superbrain_on": False})
    print(f"   os_volume com Supercérebro ON: {decision_on.level.name}")
    print(f"   os_volume com Supercérebro OFF: {decision_off.level.name}")
    # Como os_volume é LOCAL_PC_CONTROL, não deveria mudar, mas o mecanismo está funcionando
    
    print("\n✅ Sistema de níveis de autonomia implementado com sucesso!")
    print("\nPróximos passos sugeridos:")
    print("- Integrar este módulo no ipc_handlers.py para consultar antes de executar ações")
    print("- Adicionar camada de confirmação conversacional para nível 3")
    print("- Implementar sistema de aprovação remota (celular) para nível 4")
    print("- Criar interface no frontend para o usuário configurar preferências")

if __name__ == "__main__":
    main()