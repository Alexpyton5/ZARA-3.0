# Zoe: usar o computador pela ZARA

A ZARA precisa estar aberta no Windows. Use a mesma conta do Windows que executa a ZARA via Tailscale/SSH. O painel Zoe mantém o app Muse incorporado; esta ponte controla a ZARA local e não exige API da Meta.

No PowerShell, dentro de `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`:

```powershell
& .\.venv\Scripts\python.exe tools\zoe_bridge.py status
& .\.venv\Scripts\python.exe tools\zoe_bridge.py actions
& .\.venv\Scripts\python.exe tools\zoe_bridge.py see
& .\.venv\Scripts\python.exe tools\zoe_bridge.py run computer_list_windows
& .\.venv\Scripts\python.exe tools\zoe_bridge.py run vision_find_text '{"text":"Bloco de Notas"}'
```

`see` devolve a janela ativa, o texto reconhecido e o caminho da captura. Use o `hwnd` da janela observada para agir:

```powershell
& .\.venv\Scripts\python.exe tools\zoe_bridge.py run computer_focus_window '{"hwnd":12345}'
& .\.venv\Scripts\python.exe tools\zoe_bridge.py run computer_click '{"x":500,"y":300,"expected_hwnd":12345}'
& .\.venv\Scripts\python.exe tools\zoe_bridge.py run computer_type_text '{"text":"Olá Alex","expected_hwnd":12345}'
& .\.venv\Scripts\python.exe tools\zoe_bridge.py see
```

Substitua `12345` e as coordenadas pelos valores observados. Há também `computer_scroll` (`x`, `y`, `steps`, `expected_hwnd`) e `computer_press_key` (`key`, `expected_hwnd`). Leia a tela novamente depois de clicar, rolar ou pressionar tecla: essas ações não afirmam que o efeito ocorreu sem observação.

Com o **Supercérebro OFF**, leitura continua disponível, mas foco, clique, rolagem, digitação e teclas são bloqueados. O Alex pode ligar a chave visível na barra lateral da ZARA. A ponte não contorna essa chave nem confirma ações sensíveis. Campos de senha, pagamento e terminais não aceitam digitação por esta ação.

Prova feita em 28/09/2026 na janela de desenvolvimento: a ponte listou janelas, focou o Bloco de Notas, clicou, digitou texto e o leu de volta; com a chave OFF, o clique foi bloqueado. A captura é real, mas o texto de `see` vem de OCR local. Entendimento visual completo da imagem e uso espontâneo desta ponte pela Zoe via WhatsApp ainda são **NÃO PROVADOS**.
