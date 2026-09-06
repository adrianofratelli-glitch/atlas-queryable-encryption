> Estado vigente: melhoria `1e12692` aprovada pelo usuário e integrada em `main`. As menções abaixo a aprovação pendente são históricas. As propostas de core/schema/dataset continuam sem aplicação.

# Revisão de engenharia e design — atlas-queryable-encryption

## Resultado

Handler global registra tipo da exceção e request_id, sem serializar a mensagem/traceback que pode conter plaintext.

Branch `review/codex-improvements`, criada de `main` em `5f7ceef743f4dc769070d8de28779db8754f321e`. Sem merge, push, troca de biblioteca core, alteração de schema ou dataset.

## Commits de correção

- `0fb4b27 fix: keep exception payloads out of encryption logs`

## Commits visible-change

Nenhum.

## Validação

- 38 testes unitários passaram.
- Build de produção passou; análise Ruff E9/F63/F7/F82 com target Python 3.12 passou.
- Browser com APIs bloqueadas: 1440×1000, 768×1024 e 360×800; sem pageerror e sem overflow horizontal no shell inicial; link de salto transfere foco ao conteúdo.
- As 14 cópias de pov-signature.css permanecem idênticas; lang pt-BR confirmado. Nenhuma alteração na camada compartilhada de CSS.
- Auditor de portas passou: registro e configurações alinhados.
- npm audit do lockfile após correções: 0 altos, 0 críticos, 0 moderados e 0 baixos.

## Sugestões não aplicadas e limites

- A correção elimina um caminho potencial de vazamento em logs; não foi encontrada evidência de credencial real exposta. Não é uma auditoria de logs históricos.
- Coleção cifrada única, dois clientes e encryptedFields preservados. Nenhuma mudança de KMS, schema ou seed.

A verificação visual cobre o shell offline e abas acessíveis sem backend, não todos os estados de dados. Não certifica contraste de cada componente, comportamento touch completo ou toda a navegação com Atlas. Fluxos reais de escrita/carga não foram executados para preservar datasets. Nenhuma comparação de performance foi inventada. Evidências locais: `/tmp/codex-portfolio-review/`.

## Dependências Python

Auditoria do ambiente instalado, não de uma resolução limpa do manifesto; ferramentas de desenvolvimento podem aparecer junto com runtime. Os IDs abaixo não equivalem a exploração confirmada na PoV. Reconciliar versões instaladas/manifests e testar compatibilidade; atualizações core/major ficaram fora desta rodada. Pacotes de ferramenta e componentes extras do venv também não foram alterados fora da branch.

| Pacote instalado | Versão | Advisory | Versões corrigidas informadas |
|---|---|---|---|
| pytest | 8.4.2 | PYSEC-2026-1845 | 9.0.3 |

## Segredos e compartilhamento

Varredura por padrões de chaves privadas, chaves Anthropic/AWS e URI MongoDB autenticada no histórico Git local alcançável: nenhuma credencial real confirmada; matches encontrados eram placeholders conhecidos. Limite: não é scanner de entropia, não cobre objetos inacessíveis, texto em screenshots nem logs externos.

Nenhum import/referência estática a `_shared/grove_client.py` foi encontrado nesta PoV. Configuração própria de gateway/ambiente não constitui dependência de código desse módulo. `_shared` permaneceu intocado; consumidores externos/dinâmicos não são garantidos por busca estática. Relatório separado: `../REVIEW_SHARED.md`.


## Fechamento final — 2026-09-05

Esta seção atualiza o estado dos achados históricos acima.

- Aplicado/reavaliado: Sem alteração nova de runtime; saneamento de logs anterior mantido.
- Validação: 38 testes; npm sem achados.
- Propostas e limites restantes: pytest 8.4.2 → 9.0.3: elimina advisory de diretório temporário, mas é salto major de ferramenta de testes; propor atualização dedicada com plugins/CI validados. KMS, encryptedFields, dois clientes e seed preservados. Logs históricos não foram auditados.
- pip-audit atual: pytest 8.4.2: PYSEC-2026-1845
- Ambiente: pip 26.2.1 nos ambientes que possuem pip; FinScope mantém uv sem pip. Essa atualização local não altera arquivos de dependências das PoVs.
- `_shared`: nenhum importador estático comprovado nesta PoV; apenas smoke consome o helper no inventário.


## Homologação de resiliência e UI

- Melhoria: Recuperar pré-voo e titulares após falha; distinguir lista vazia de erro; mensagem correta para busca sem resultado; ignorar chamadas já canceladas.
- Isolamento: `review/codex-homologation`, baseada no HEAD `d76a5d9`. Mudança de estado observável; aguardando aprovação individual, sem merge.
- Validação: build passou; UI offline em 1440×1000, 768×1024 e 360×800 sem pageerror nem overflow horizontal; skip link transfere foco. 0 testes novos de transporte/polling neste repositório. As suítes locais anteriores foram reexecutadas; resultados consolidados no vault PoVs-Handoffs.
- Limite: teste offline/fixture não certifica cenário real completo nem ausência de bugs. Não houve alteração de schema, dataset ou dependência core.
- Propostas preservadas: pytest 8.4.2 → 9.0.3: elimina advisory de diretório temporário, mas é salto major de ferramenta de testes; propor atualização dedicada com plugins/CI validados. KMS, encryptedFields, dois clientes e seed preservados. Logs históricos não foram auditados.
- `_shared` e daemon do portal não foram alterados nesta rodada.
