from core.cronometro import relatorio
import json
r = relatorio(ultimos=1000)
print(json.dumps(r, ensure_ascii=False, indent=2))