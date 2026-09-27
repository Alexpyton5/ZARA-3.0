# Validação 2026-09-04_08-20-09

- commit: `db12ed6cd9fa8c747eace4299088b142b5a00085`
- modo: full
- alvo: <marker filtered>
- resultado: ===== 25 failed, 1632 passed, 28 skipped, 2 warnings in 144.58s (0:02:24) =====
- duração: 145.7s

## Comparação com baseline
- NOVAS falhas: nenhuma
- falhas conhecidas ainda presentes: 25
- corrigidas desde o baseline: ['tests/test_foundation_smoke.py::TestIPC::test_main_ipc_registration', 'tests/test_foundation_smoke.py::TestIntentClassification::test_intent_classifier_imports', 'tests/test_foundation_smoke.py::TestIntentClassification::test_local_deterministic_actions_defined', 'tests/test_foundation_smoke.py::TestIntentClassification::test_pc_voice_intent_imports', 'tests/test_foundation_smoke.py::TestVoiceEngine::test_gemini_live_imports', 'tests/test_foundation_smoke.py::TestVoiceEngine::test_voice_tts_imports', 'tests/test_os_ops_truth_contracts.py::test_brightness_rejects_observed_value_outside_tolerance', 'tests/test_os_ops_truth_contracts.py::test_night_light_never_reports_cloudstore_only_success', 'tests/test_os_ops_truth_contracts.py::test_window_close_protects_any_zara_window', 'tests/test_ponte_claude.py::test_confirma_quando_a_mensagem_aparece_na_conversa_certa', 'tests/test_project_context_control.py::test_active_project_is_persisted_and_context_is_isolated', 'tests/test_project_context_control.py::test_budget_keeps_required_project_id_and_reports_omitted_doc', 'tests/test_project_context_control.py::test_explicit_project_does_not_mutate_active_selection', 'tests/test_remote_approval_bridge.py::test_adapter_token_is_never_stored', 'tests/test_remote_approval_bridge.py::test_expiry_during_slow_verification_fails_closed', 'tests/test_remote_approval_bridge.py::test_invalid_timeout_is_rejected[inf]', 'tests/test_remote_approval_bridge.py::test_missing_failing_and_wrong_verifiers_fail_closed', 'tests/test_remote_approval_bridge.py::test_pending_and_approved_requests_expire_without_sleep', 'tests/test_remote_approval_bridge.py::test_terminal_history_is_bounded', 'tests/test_router_integrity.py::test_050_all_intent_actions_except_known_gap_are_registered']