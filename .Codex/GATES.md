# Gates: ZARA-CYCLE7-SUITE-PHYSICAL-20260927

OWNS: core/**, memory/**, tests/**, frontend/**, .Codex/**

Scope: fechar a suíte sem maquiar testes e executar o teste físico do Lab com agentes reais e custo R$ 0.

- [ ] G1: todos os testes Python são coletados sem erro
  CHECK: .venv\Scripts\python.exe -m pytest tests --collect-only -q -q --disable-warnings --tb=no && echo PYTHON_COLLECTION_OK
  EXPECT: PYTHON_COLLECTION_OK
  EVIDENCE: pending

- [ ] G2: a suíte Python completa termina sem falhas
  CHECK: .venv\Scripts\python.exe -m pytest tests -q --disable-warnings --tb=no && echo PYTHON_SUITE_OK
  EXPECT: PYTHON_SUITE_OK
  EVIDENCE: pending

- [ ] G3: a suíte do frontend compila e passa
  CHECK: npm.cmd test && echo FRONTEND_SUITE_OK
  EXPECT: FRONTEND_SUITE_OK
  CWD: frontend
  EVIDENCE: pending

- [ ] G4: o app empacotado despacha CEO e REVIEWER reais, registra um turno e mantém os outros nove assentos calados
  EVIDENCE: pending

- [ ] G5: a única chamada externa do teste usa endpoint NVIDIA comprovadamente sem cobrança e nenhuma credencial aparece em relatório ou commit
  EVIDENCE: pending

- [ ] G6: o resultado e as limitações do ciclo são registrados em LOOP_LOG/LOOP_INBOX e publicados na branch autorizada
  EVIDENCE: pending
