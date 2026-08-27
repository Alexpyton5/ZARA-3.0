# ZARA 3.0 — raiz principal

Esta é a única raiz canônica de desenvolvimento da ZARA:

`C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`

Estado atual: **runtime empacotado certificado no escopo de boot, renderer, backend e IPC inicial**.
A antiga candidata no volume `D:` está em standby porque esse volume foi detectado como sujo.

Comece pelo [relatório de tomada de controle](./MENTOR_TAKEOVER_REPORT.md) e por
[OPERATIONS.md](./OPERATIONS.md). Esses documentos definem evidências, tarefas, backups em
standby, relação entre fonte/build/runtime, status real dos checks, gates de promoção e protocolo de
segurança.

Evidência atual (2026-08-27): 1411 de 1591 testes Python passaram, 153 falharam e 27 foram
pulados. O bug em `core/action_registry.py` (decorator `action()` descartava argumentos posicionais
de chamadas diretas) foi corrigido nesta mesma revisão, o que já reduziu as falhas de 209 para 153.
As 153 falhas restantes são pré-existentes e pertencem a um refactor de autonomia/capability ainda
não commitado, em duas frentes distintas e não relacionadas às correções da AUDITORIA_2026-08-27:
(1) `IPCHandler` ainda não implementa `handle_soul_get` e outros handlers do recurso "soul"; (2)
`VadConfig` lê valores de padding/sensibilidade que não batem com o esperado pelos testes novos.
O número "62 testes" abaixo e em
OPERATIONS.md é histórico de uma raiz muito mais antiga do projeto (poucas dezenas de arquivos de
teste) — hoje a suíte tem mais de 150 arquivos. compileall/Ruff passaram; `npm ci`, `npm ls`, lint,
typecheck, Vite, Electron TypeScript, sidecar e `electron-builder` passaram. O lint terminou com
0 erros e 47 warnings. O sidecar fonte e o empacotado compartilham SHA-256
`639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`.
O smoke final passou com backend ready, renderer sem failure, zero boot race e stderr zero. O
Supercérebro permaneceu corretamente OFF/desconectado. Permanecem pendentes a validação humana da
voz/áudio, chamadas reais às APIs e ativação conectada do Hermes.

Hashes SHA-256 finais:

- Sidecar: `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`
- Aplicativo unpacked: `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- Instalador: `4D63B88D050CF4110D93DBC59D47A21C8E4E191DBA2AC881CFFBF8BD832CEA41`

## Entradas do projeto

- Backend: `main.py`, `core/`, `integrations/` e `memory/`.
- Frontend/Electron: `frontend/src/`.
- Testes: `tests/`.
- Empacotamento do sidecar: `build_exe.py`.
- Saídas em `dist-sidecar/`, `frontend/dist-*` e `frontend/release/` são geradas e não devem ser
  editadas diretamente.

## Contexto do laboratório

O módulo ZARA-LAB-CORE-001 sucede os patches ZARA-TEAM-ROOM-001/002 e inclui conselho local,
participação ZARA/Hermes, status dos trabalhadores, propostas, fila e feed. Funcionalidade pendente
de implementação ou validação permanece identificada no quadro operacional; não deve ser anunciada
como concluída antes dos respectivos gates.
