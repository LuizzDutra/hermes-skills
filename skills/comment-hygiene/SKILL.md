---
name: comment-hygiene
description: "Use when writing or cleaning comments and docstrings."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [refactor, comments, documentation, cleanup, review, authoring, auto-load]
    related_skills: [prune-tests, requesting-code-review, simplify-code, spec-graph, commit]
---

# comment-hygiene

Regra central: **um comentário descreve o código que está na frente do leitor.** Não
descreve a conversa que o produziu, o plano que o encomendou, nem a linha do tempo
das versões.

Escreva para quem chega depois: só o repositório à mão — sem o chat, sem o plano,
sem o autor. Se a frase só faz sentido para quem acompanhou o trabalho, ela não é
comentário: é recado.

## Nunca (em comentário e docstring)

1. **Endereçar o solicitante.** `# conforme pedido`, `# as requested`, `# a pedido`,
   `# como você pediu`, `# como discutimos`. Quem lê o código nunca viu essa conversa.
2. **Citar o plano ou o processo.** Sem `P5`, `S-10`, `CHK-8`, `INV-6`, `OQ-2`,
   `BEH-014`, `Step 3`, `Fase 2`, `Etapa 4`, número de tarefa, ticket interno ou hash
   de commit. O plano é arquivado; o comentário fica.
3. **Narrar o tempo sem necessidade.** `antes era`, `foi movido para cá`, `hoje isso
   falha`, `será implementado depois`, `TODO: implementar`, `previously`, `used to`,
   `renamed from`. Se a única informação é que algo mudou ou ainda vai mudar, o git
   já conta — apague. Exceção: o fato temporal tem efeito hoje
   (`# tolera meta sem o bloco repo: tarefas antigas seguem sem repositório`) — aí o
   sujeito é a compatibilidade, não a história.
4. **Repetir o código.** Se o nome ou o tipo carregam o sentido, mude o nome em vez
   de comentar.
5. **Changelog em docstring de módulo.** Módulo: o que é e por que existe agora.

## Sempre

- O *porquê*, o invariante, o risco evitado, a ordem que importa, unidades, a
  tolerância a dados legados, a regra de segurança/redação.
- ADR do repositório quando ele explica a decisão (`docs/adr/ADR-0002-*.md`): o ADR
  sobrevive ao branch, o plano não.
- Docstring de contrato é texto publicado: handler `@router.<verbo>` e classe
  `BaseModel` vão para o OpenAPI. Escreva para o consumidor da API — comportamento,
  parâmetros, erros — sem jargão interno e sem processo.

## Antes de fechar o diff

```bash
python scripts/comment_scan.py --staged --style    # caminho relativo à skill
```

Só linhas adicionadas, nunca a árvore inteira. Procedimento completo de limpeza,
allowlist, contrato, o que não é comentário (specs, YAML com `|`, `help=`, mensagens
de log): `references/cleanup.md`.
