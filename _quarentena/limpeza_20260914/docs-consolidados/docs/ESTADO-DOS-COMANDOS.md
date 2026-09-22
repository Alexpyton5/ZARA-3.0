# Estado dos comandos de voz da ZARA

Levantamento em 21/08/2026, feito por qa_tester (tarefa t_97f6b775). Metodo:
leitura de codigo (nao alterado), cruzamento entre `core/pc_voice_intent.py`
(padroes de fala -> acao), `core/actions/*.py` (`@action(name=...)` registrado
no `ActionRegistry`), `core/ipc_handlers.py` (roteador que liga voz a acao) e
`tests/` (o que tem prova automatizada). Rodei `pytest -q` completo
(1058 testes) e os grupos `-k voice`, `-k media`, `-k relay` e mais alguns
filtros por assunto. Todos passaram, saida real:

```
1058 passed in 20.73s      (pytest -q, suite inteira)
160 passed, 898 deselected  (pytest -q -k voice)
121 passed, 937 deselected  (pytest -q -k "media or relay")
259 passed, 799 deselected  (grupo brightness/window/clipboard/system_voice/
                              open_app_intent/safe_app_close/safe_input/
                              ponte_claude/folder_control/file_voice/
                              media_control/media_semantic)
```

NAO MEDIDO FISICAMENTE: latencia de voz real (microfone/audio) e taxa de
sucesso falada com o Alex. Os numeros de teste acima sao suite automatizada
(mocks/unit), nao gravacao de voz real. Nao estimo latencia sem medicao.

## Legenda
- FUNCIONA: acao registrada no ActionRegistry + padrao no roteador de voz +
  pelo menos 1 teste automatizado passando que cobre essa acao/nome.
- QUEBRADO: existe no codigo/roteador mas teste falhou, ou nao roda.
  (Nenhum caso encontrado nesta varredura — suite inteira verde.)
- SO EXISTE NO PAPEL: acao registrada e ligada ao roteador de voz, mas SEM
  teste automatizado que exercite essa acao pelo nome. Codigo existe, ninguem
  provou que funciona por voz.

## Tabela (60 acoes distintas mapeadas em pc_voice_intent.py)

| comando (acao) | estado | o que falta |
|---|---|---|
| os_app (abrir calculadora/notepad/chrome/task_manager/settings/paint/snipping_tool/edge/spotify) | FUNCIONA | test_open_app_intent.py, test_router_integrity.py |
| os_close_safe_app (fechar apps seguros) | FUNCIONA | test_safe_app_close.py |
| os_open (downloads/documents/desktop/pictures/zara_root) | FUNCIONA | test_folder_control.py, test_operational_context.py |
| browser_open_url | FUNCIONA | test_browser_dispatch.py, test_action_metadata_safety.py |
| youtube_open | FUNCIONA | test_media_app_controls.py, test_browser_dispatch.py |
| youtube_search | FUNCIONA | test_media_app_controls.py |
| youtube_play_by_name | FUNCIONA | test_media_app_controls.py |
| youtube_next / media_next | FUNCIONA | test_media_app_controls.py, test_media_control.py |
| media_previous | FUNCIONA | test_media_control.py, test_media_semantic_217.py |
| youtube_now_playing | FUNCIONA | test_media_app_controls.py |
| youtube_another_by_artist | FUNCIONA | test_media_app_controls.py |
| spotify_search | FUNCIONA | test_media_app_controls.py |
| youtube_skip_ad | FUNCIONA | test_media_app_controls.py |
| browser_new_tab | FUNCIONA | test_media_app_controls.py |
| browser_back | FUNCIONA | test_media_app_controls.py |
| browser_forward | FUNCIONA | test_media_app_controls.py |
| browser_close_tab | FUNCIONA | test_media_app_controls.py |
| browser_read_page | SO EXISTE NO PAPEL | registrado e no roteador, zero teste com esse nome |
| vision_screenshot | FUNCIONA | test_notification_screenshot_control.py |
| os_notify | FUNCIONA | test_notification_screenshot_control.py |
| system_time | FUNCIONA | test_system_information_real.py, test_system_voice_intents.py |
| system_metrics | FUNCIONA | idem |
| system_info | FUNCIONA | idem |
| system_processes | FUNCIONA | idem |
| browser_search (pesquisar X) | FUNCIONA | test_browser_dispatch.py, test_recusa_honesta.py |
| os_volume (nivel/up/down) | FUNCIONA | test_volume_context.py, test_router_integrity.py |
| youtube_pause / youtube_resume | FUNCIONA | test_media_app_controls.py, test_media_control.py |
| youtube_seek (avancar/voltar segundos, reiniciar) | FUNCIONA | test_media_app_controls.py |
| audio_mute / audio_unmute | FUNCIONA | test_media_control.py, test_action_metadata_safety.py |
| audio_status | FUNCIONA | test_audio_status.py |
| os_wifi_on / os_wifi_off | FUNCIONA | test_windows_radios.py |
| os_bluetooth_on / os_bluetooth_off | FUNCIONA | test_windows_radios.py |
| os_brightness_absolute / up / down | FUNCIONA | test_brightness_control.py |
| os_night_light_on / off | FUNCIONA | test_brightness_control.py, test_system_voice_intents.py |
| window_minimize / maximize / restore | FUNCIONA | test_window_control.py, test_operational_context.py |
| window_switch_next | FUNCIONA | test_window_control.py |
| window_focus_named (chrome/zara/vscode/project) | FUNCIONA | test_window_control.py |
| window_move (lado direito/esquerdo, contextual) | SO EXISTE NO PAPEL | registrado no ActionRegistry e no roteador (contextual_geometry), zero teste com esse nome |
| window_resize_larger (contextual) | SO EXISTE NO PAPEL | idem, zero teste |
| window_close (contextual) | SO EXISTE NO PAPEL | idem, zero teste |
| browser_scroll (rolar pagina) | FUNCIONA | test_media_app_controls.py, test_router_integrity.py |
| os_clipboard (copiar texto / limpar) | FUNCIONA | test_clipboard_voice.py, test_action_metadata_safety.py |
| os_clipboard_read (ler area de transferencia) | SO EXISTE NO PAPEL | registrado e no roteador, zero teste com esse nome |
| input_type_text ("digite 'x'") | FUNCIONA | test_safe_input_controls.py |
| input_hotkey (selecionar tudo, copiar, colar, desfazer...) | FUNCIONA | test_safe_input_controls.py (cobre allowlist e paste; nem todo verbo do padrao tem caso individual) |
| claude_ler / codex_ler (ler resposta) | FUNCIONA | test_ponte_claude.py |
| claude_enviar / codex_enviar (mandar mensagem) | FUNCIONA | test_ponte_claude.py |
| ponte_repassar (repassar claude<->codex) | FUNCIONA | test_ponte_claude.py |
| aprendizado_resumo ("o que voce aprendeu") | SO EXISTE NO PAPEL | registrado (core/actions/aprendizado_acoes.py) e no roteador, zero teste com esse nome exato |

## Resumo numerico
- Total de acoes distintas mapeadas em pc_voice_intent.py: 60
- Todas as 60 estao registradas no ActionRegistry (`core/actions/*.py`) — nenhuma acao fantasma achada, nenhuma referenciada no roteador que nao existe no registry.
- Todas as 60 estao ligadas ao roteador de voz (`core/ipc_handlers.py` instancia `PcVoiceIntentDetector` e despacha via `execute_action`).
- Com teste automatizado cobrindo o nome da acao: 54 de 60 (FUNCIONA).
- Sem teste automatizado com esse nome: 6 de 60 (SO EXISTE NO PAPEL) —
  browser_read_page, window_move, window_resize_larger, window_close,
  os_clipboard_read, aprendizado_resumo. A tabela acima e a fonte de verdade.
- QUEBRADO: 0 achados nesta varredura. Suite inteira (1058 testes) passou.

## O que falta para fechar a lacuna (SO EXISTE NO PAPEL)
Cada uma dessas 6 acoes tem codigo real, registro no ActionRegistry e padrao
de regex no roteador — ou seja, plausivelmente funcionam — mas nenhum teste
automatizado exercita o nome da acao, entao "funciona" aqui e INFERENCIA, nao
prova. Para virar FUNCIONA de verdade falta:
1. Um teste chamando o detector com a frase de voz e checando `action ==
   "<nome>"` (como os outros arquivos test_*_control.py ja fazem).
2. Um teste chamando a funcao de `core/actions/*.py` (mock do lado do SO
   quando aplicavel) confirmando `ActionResult.success`.

## Nao verificado fisicamente
- Latencia de voz real com microfone (alvo <500ms) e barge-in real: nao
  medido nesta tarefa. So rodei suite automatizada.
- Taxa de sucesso falada com o Alex: nao medido, nao estimado.

## Nao alterei nenhum arquivo do app
Toquei so em `docs/ESTADO-DOS-COMANDOS.md` (este arquivo). Os scripts
auxiliares de varredura (`_qa_scan*.py`) foram criados e apagados na propria
sessao, so leram arquivos, nao escreveram em nada do app.
