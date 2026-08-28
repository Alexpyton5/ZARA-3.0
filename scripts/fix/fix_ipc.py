import sys

with open('core/ipc_handlers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We know the line numbers (0-indexed) for the start and end of the block to replace.
# From the earlier read, the block starts at line 3651 (0-indexed) which is the line "    def foi_aprovado(self, id_do_pedido: str) -> bool:"
# and ends at line 3737 (0-indexed) which is the line "            return False" (the last line of the except block) and then the newline? Actually, we want to replace until the end of the _deve_requer_aprovacao_explicita function.
# Let's find the end by scanning for the next method definition after the _deve_requer_aprovacao_explicita function.

# Instead, we'll replace from line 3651 to line 3737 (inclusive) with the corrected block.

# But note: the file might have changed. We'll use the content we have from the last read to be safe.

# We'll write the corrected block as a list of strings.

corrected_block = [
    "    def foi_aprovado(self, id_do_pedido: str) -> bool:\n",
    "        \"\"\"Ele autorizou? Só True quando ele disse sim de verdade.\"\"\"\n",
    "        return id_do_pedido in getattr(self, \"_aprovado_por_alex\", set())\n",
    "\n",
    "    def _deve_requer_aprovacao_explicita(self, texto: str) -> bool:\n",
    "        \"\"\"\n",
    "        Determina se um texto de comando do Telegram requer aprovação explícita.\n",
    "        \n",
    "        Returns True se o comando, quando executado, exigiria confirmação\n",
    "        segundo as regras do action registry (ações HIGH risk ou MEDIUM risk\n",
    "        que requerem confirmação explícita).\n",
    "        \"\"\"\n",
    "        try:\n",
        "            # Tentar detectar a intenção de PC para determinar qual ação seria executada\n",
        "            from core.pc_voice_intent import PcVoiceIntentDetector\n",
        "            \n",
        "            # Usar as mesmas configurações que _try_pc_intent usa para detecção\n",
        "            detector = PcVoiceIntentDetector(\n",
        "                pc_control_allowed=bool(self.supercerebro_active),\n",
        "                volume_context_level=self._last_volume_level if self._context_fresh(\"volume\") else None,\n",
        "                window_context_available=bool(\n",
        "                    (self._context_fresh(\"app\") or self._context_fresh(\"window\"))\n",
        "                    and self._last_window_hwnd\n",
        "                ),\n",
        "                folder_context=(\n",
        "                    self._last_safe_folder\n",
        "                    if self._context_fresh(\"folder\")\n",
        "                    and self._last_safe_folder in {\"downloads\", \"documents\", \"desktop\", \"pictures\", \"zara_root\"}\n",
        "                    else None\n",
        "                ),\n",
        "            )\n",
        "            \n",
        "            # Detectar se é uma intenção de PC\n",
        "            res = detector.detect(texto)\n",
        "            if not res.is_pc_intent:\n",
        "                # Se não for intenção de PC, não requer aprovação explícita via Telegram\n",
        "                # (pode ser conversa, lembrete, etc.)\n",
        "                return False\n",
        "            \n",
        "            if res.blocked:\n",
        "                # Se estiver bloqueado por falta de Supercérebro, ainda assim pode\n",
        "                # querer aprovação explícita, mas vamos ser conservadores e não exigir\n",
        "                # aprovação explícita para ações bloqueadas - elas vão falhar de qualquer jeito\n",
        "                return False\n",
        "            \n",
        "            # Verificar se a ação está registrada\n",
        "            from core.action_registry import get_registry\n",
        "            from core.capability_registry import load_capability\n",
        "            \n",
        "            load_capability(res.action)\n",
        "            if res.action not in get_registry()._specs:\n",
        "                # Ação não registrada - tratar como não requerendo aprovação explícita\n",
        "                return False\n",
        "            \n",
        "            # Obter a especificação da ação\n",
        "            spec = get_registry()._specs.get(res.action)\n",
        "            if spec is None:\n",
        "                return False\n",
        "            \n",
        "            # Regras para determinar se requer aprovação explícita:\n",
        "            # 1. Ações HIGH risk sempre requerem confirmação (one-shot challenge)\n",
        "            # 2. Ações MEDIUM risk requerem confirmação se medium_risk_open for False\n",
        "            # 3. Ações que requerem Supercérebro mas que ele está OFF requerem confirmação\n",
        "            \n",
        "            # Regra 1: HIGH risk sempre requer confirmação\n",
        "            if spec.risk == \"HIGH\":\n",
        "                return True\n",
        "            \n",
        "            # Regra 2: MEDIUM risk requer confirmação se a política MEDIUM não estiver aberta\n",
        "            if spec.risk == \"MEDIUM\" and not self.medium_risk_open:\n",
        "                return True\n",
        "            \n",
        "            # Regra 3: Ações que requerem Supercérebro mas que ele está OFF\n",
        "            superbrain_required = spec.capability not in {\"READ_ONLY\", \"LOCAL_PC_CONTROL\"}\n",
        "            if superbrain_required and not self.supercerebro_active:\n",
        "                return True\n",
        "            \n",
        "            # Regra 4: Ações marcadas com requires_confirmation no ActionRegistry\n",
        "            if spec.requires_confirmation:\n",
        "                return True\n",
        "            \n",
        "            return False\n",
        "        except Exception:\n",
        "            # Em caso de qualquer erro, ser conservador e não exigir aprovação explícita\n",
        "            # Isso evita bloquear o sistema se houver problemas na detecção\n",
        "            return False\n",
        "\n"
]

# Now, we need to know the exact indices to replace.
# We'll search for the line that starts with "    def foi_aprovado(self, id_do_pedido: str) -> bool:"
start_index = None
for i, line in enumerate(lines):
    if line.rstrip() == "    def foi_aprovado(self, id_do_pedido: str) -> bool:":
        start_index = i
        break

if start_index is None:
    print("Could not find the start of the block")
    sys.exit(1)

# Now, we need to find the end of the _deve_requer_aprovacao_explicita function.
# We'll look for the next line that starts with "    def " (with exactly 4 spaces) after the start_index, but we must skip the empty lines and the function body.
# Actually, we know that the function ends before the next method definition. We'll look for the next line that starts with "    def " and is not inside the function.

# We'll set end_index to the line before the next method definition.
end_index = None
for i in range(start_index + 1, len(lines)):
    if lines[i].startswith("    def ") and not lines[i].startswith("        "):
        # This is a new method at the same indentation level as the class methods.
        end_index = i - 1
        break

if end_index is None:
    # If we didn't find a next method, then we replace until the end of the file.
    end_index = len(lines) - 1

# Now, replace lines[start_index:end_index+1] with corrected_block
new_lines = lines[:start_index] + corrected_block + lines[end_index+1:]

with open('core/ipc_handlers.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)