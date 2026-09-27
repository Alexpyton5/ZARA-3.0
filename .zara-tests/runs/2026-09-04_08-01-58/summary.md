# Validação 2026-09-04_08-01-58

- commit: `b74afcf92963e5635051c4b7e8154d5f546a03a7`
- modo: full
- alvo: <marker filtered>
- resultado: ===== 33 failed, 1624 passed, 28 skipped, 2 warnings in 154.02s (0:02:34) =====
- duração: 155.2s

## Comparação com baseline
- NOVAS falhas: nenhuma
- falhas conhecidas ainda presentes: 33
- corrigidas desde o baseline: ['tests/test_foundation_smoke.py::TestIPC::test_main_ipc_registration', 'tests/test_foundation_smoke.py::TestIntentClassification::test_intent_classifier_imports', 'tests/test_foundation_smoke.py::TestIntentClassification::test_local_deterministic_actions_defined', 'tests/test_foundation_smoke.py::TestIntentClassification::test_pc_voice_intent_imports', 'tests/test_foundation_smoke.py::TestVoiceEngine::test_gemini_live_imports', 'tests/test_foundation_smoke.py::TestVoiceEngine::test_voice_tts_imports', 'tests/test_os_ops_truth_contracts.py::test_brightness_rejects_observed_value_outside_tolerance', 'tests/test_ponte_claude.py::test_confirma_quando_a_mensagem_aparece_na_conversa_certa', 'tests/test_project_context_control.py::test_active_project_is_persisted_and_context_is_isolated', 'tests/test_project_context_control.py::test_budget_keeps_required_project_id_and_reports_omitted_doc', 'tests/test_project_context_control.py::test_explicit_project_does_not_mutate_active_selection', 'tests/test_router_integrity.py::test_050_all_intent_actions_except_known_gap_are_registered']