# Quadro da ZARA — 22/08/2026

Alvo oficial: chegar ao nível JARVIS funcionando de graça por padrão. Modelo pago é opcional.

## O que existe agora

- O cérebro está separado em memória, conhecimento e skills, com migração e recuperação testadas.
- A ZARA carrega só 23 capacidades essenciais no início e busca as demais quando precisa.
- Ambiente, contexto compacto, telemetria de roteamento, diário de experiência e visão de último recurso já têm implementação e testes.
- Aprovação remota tem uma base segura: autenticação, expiração e uso único.
- Snapshot, manifesto do build e inventário de higiene protegem dados e tornam mudanças recuperáveis.
- O portão de qualidade está ativo com 1.294 testes identificados. A suíte real terminou com 1.293 aprovados, 1 skip de symlink no Windows e nenhuma falha.
- O OpenClaw escolhe modelo por dificuldade e só libera modelo pago depois de conferir a cota ao vivo.

## O que ainda falta

- Eliminar a primeira viagem descartada da voz sem quebrar a sessão Gemini Live.
- Ter voz principal totalmente gratuita e rápida, sem chave obrigatória.
- Ligar a aprovação pelo celular ao Telegram e ao executor real.
- Mostrar telemetria e sugestões revisáveis na interface.
- Validar a interface premium dentro da build distribuída.
- Criar e testar um comando único que instala dependências, testa, empacota e gera o instalador do zero.
- Unir percepção, memória e iniciativa em níveis claros de autonomia.

## Maiores riscos

1. Mexer na voz sem respeitar o protocolo pode piorar reconexão, conversa direta e barge-in.
2. Um build antigo pode parecer pronto mesmo sem ser reproduzível do zero.
3. Proatividade sem controle pode transformar ajuda em incômodo ou ação arriscada.
4. O hardware de 16 GB de RAM e 4 GB de VRAM limita os modelos locais maiores.

## Próximos três passos

1. Fechar o build em um comando e provar o instalador numa execução limpa.
2. Fazer a arquitetura segura da voz sem a viagem inicial descartada.
3. Integrar aprovação móvel, painel de telemetria e sugestões do diário, sempre com revisão humana.

O placar detalhado das cinco fases está em `docs/FASES-CORUJAO-STATUS.md`.
