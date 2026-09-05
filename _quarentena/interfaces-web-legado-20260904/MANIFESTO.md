# Quarentena — interfaces web legadas (2026-09-04)

Movido por auditoria mecânica da raiz (`tools/zara_root_audit.py`), a pedido do Alex
(seção 43-44 do pedido "ZARA — SINGLE SOURCE OF TRUTH").

## zara_interface/

- **Path original:** `zara_interface/` (raiz)
- **Path novo:** `_quarentena/interfaces-web-legado-20260904/zara_interface/`
- **O que é:** projeto Next.js separado (nome interno "zara-interface"), com config de
  deploy Cloudflare Wrangler (`.wrangler`, `.sites-runtime`). Tecnologia completamente
  diferente do `frontend/` (Electron + Vite) que é o app oficial.
- **Antes de mover:** 966 MB no disco. 855 MB eram `node_modules/`, `.next/` e
  `.sites-runtime/npm-cache` — cache regenerável, gitignorado, apagado antes da
  quarentena (não fazia sentido mover cache). Só ~4 MB de conteúdo real (107 arquivos
  rastreados pelo git) foram movidos.
- **Referências encontradas:** só `frontend/src/renderer/components/zara/ZaraDashboard.tsx`
  (um `<iframe src="zara_interface/index.html">`) — componente **não usado** pelo app real
  (`App.tsx` renderiza `ZaraHome`, não `ZaraDashboard`). A referência foi neutralizada
  (`src="about:blank"` + comentário) para não apontar pra um caminho que sumiu.
  Fora isso, só menções em docs históricos (`ARCHITECTURE_MAP.md`,
  `CORRECTIONS_AND_AUDITS.md`, `FOUNDATION_M1-M7_REPORT.md`,
  `TRANSFORMATION_PLAN.md`) — registro do passado, não código ativo.
- **Classificação:** LEGACY (experimento paralelo, nunca ligado ao build/runtime oficial).
- **Motivo:** não é a ZARA oficial, não entra no build do Electron, não é servido em
  runtime. Alex pediu para eliminar múltiplas "ZARAs" do workflow.

## zara-interface-codigo-completo/

- **Path original:** `zara-interface-codigo-completo/` (raiz)
- **Path novo:** `_quarentena/interfaces-web-legado-20260904/zara-interface-codigo-completo/`
- **O que é:** parece ser um dump de código-fonte limpo (sem `node_modules`) do mesmo
  projeto acima — mesmo `package.json`, mesmos 107 arquivos rastreados. Provavelmente um
  snapshot de backup feito à parte.
- **Tamanho:** 1,5 MB (já era pequeno, sem cache).
- **Referências encontradas:** só docs históricos (`CURRENT_STATE_REPORT.md`,
  `KEEP_CONNECT_REFACTOR_REPLACE.md`, `TRANSFORMATION_PLAN.md`). Nenhuma referência em
  código ativo.
- **Classificação:** LEGACY (cópia de backup do mesmo experimento acima).

## Decisão

Nada foi apagado — só isolado. Se em algum momento ficar comprovado que ninguém precisa
disso, aí sim vira candidato a remoção definitiva, com autorização explícita.

Data: 2026-09-04
