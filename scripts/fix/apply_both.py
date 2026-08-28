#!/usr/bin/env python3
import re

# Read the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Step 1: Add _PATTERN_FORMAT and _historico_comandos after _ACOES_DE_TEXTO_LIVRE
new_section1 = '''

    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
    # para prevenir acidentes acidentais. Quando detectado, zara responde
    # honestamente que nao pode executar esse comando.
    _PATTERN_FORMAT = re.compile(
        r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        re.IGNORECASE,
    )
    # Historico dos ultimos 5 comandos detectados (memoria volatil)
    _historico_comandos: list[dict] = []
    _MAX_HISTORICO = 5

'''

# Find the position after _ACOES_DE_TEXTO_LIVRE
target1 = '    _ACOES_DE_TEXTO_LIVRE = frozenset({\n        \"browser_search\", \"input_type_text\", \"os_clipboard\",\n    })'

if target1 in content:
    content = content.replace(target1, target1 + new_section1, 1)
    print('Step 1: Added _PATTERN_FORMAT and _historico_comandos')
else:
    print('Step 1: Target not found')

# Step 2: Add format check in detect method after text_lower = line
new_section2 = '''

        # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
        # Verifica se o comando tenta formatar um drive antes de processar
        format_match = self._PATTERN_FORMAT.search(text_lower)
        if format_match:
            # Adicionar ao historico
            self._historico_comandos.append({
                'comando': text_lower,
                'acao': 'os_drive_format',
                'bloqueado': True,
            })
            if len(self._historico_comandos) > self._MAX_HISTORICO:
                self._historico_comandos = self._historico_comandos[-self._MAX_HISTORICO:]
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_drive_format",
                param=format_match.group(1),
                blocked=True,
                physical_effect=0,
                reply="Não posso executar comandos de formatao de drive. Esse comando e bloqueado por seguranca.",
            )

'''

# Find the position: after "text_lower = text.lower().strip()"
target2 = '        text_lower = text.lower().strip()'

if target2 in content:
    content = content.replace(target2, target2 + new_section2, 1)
    print('Step 2: Added format check in detect method')
else:
    print('Step 2: Target not found')

# Write back
with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('File updated successfully')