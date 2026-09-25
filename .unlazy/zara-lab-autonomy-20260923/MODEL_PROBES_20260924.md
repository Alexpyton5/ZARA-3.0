# Modelo e função — evidência curta, 2026-09-24

| Rota | Chamada real observada | Uso no Core |
| --- | --- | --- |
| NVIDIA Kimi K3 | Planejou e produziu patch em teste empacotado anterior; houve também uma resposta inválida e uma recuperação automática no candidato atual | CEO e programador principal, sujeito à certificação em cada perfil |
| NVIDIA GLM 5.3 | `OK` em prompt curto; falhou duas vezes ao gerar patch longo com resposta de sucesso inválida | Retirado da rota automática de código |
| NVIDIA GLM 5.3 Flash | `OK` em 7,2 s em chamada do adapter; certificado no perfil empacotado atual | Programador reserva; qualidade de patch ainda não provada |
| NVIDIA Nemotron Ultra | Certificado no perfil empacotado anterior e no atual | Revisor independente |
| OpenCode Mimo Flash Free | `OK` via CLI e `OpenCodeAdapter` | Fora do Autopilot: a tentativa com agente de ferramentas negadas retornou 403 `FreeTierError` |
| OpenCode Nemotron Ultra Free | `OK` via CLI e `OpenCodeAdapter` | Fora do Autopilot pelo mesmo portão de ferramentas |
| NVIDIA DeepSeek V4 Flash/Pro | Ambos HTTP 410 em chamadas reais | Indisponível |
| OpenCode DeepSeek V4.1 Flash | `Insufficient account funds` em chamada real | Indisponível |

O catálogo não prova inferência. Uma chamada curta não prova qualidade para patch ou revisão. Nenhum valor de credencial foi registrado aqui.
