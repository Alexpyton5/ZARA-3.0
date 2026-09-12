def _jarvis_reply_status(reply: str | None) -> str:
    clean = str(reply or '').strip()
    folded = clean.casefold()
    if not clean or folded.startswith(('não ', 'nao ', 'esse comando', 'para executar')):
        return 'FALHOU'
    if folded in ('que horas?', 'quando?') or 'qual horário' in folded or 'qual horario' in folded:
        return 'PENDENTE'
    return 'OK'
