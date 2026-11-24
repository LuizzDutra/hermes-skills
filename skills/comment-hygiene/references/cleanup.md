# comment-hygiene — limpeza (modo B)

Modo B é a passada sobre uma árvore que já tem narração de processo. O modo A
(regras de autoria) está no `SKILL.md` e vale sempre.

**A ordem importa: rode `prune-tests` ANTES desta passada.** Docstring de teste que
narra história é a evidência que a decisão de prune usa para saber o que o teste
protege; deslope primeiro apaga a evidência e pode custar um teste de guarda real.
Limpar depois do prune também mexe em menos arquivos.

1. **Meça antes de editar.** `python scripts/comment_scan.py <roots>` e reporte o
   inventário por tipo e por `contract_risk`, depois `--style` para as classes de
   prosa. Nunca comece por word-grep: código cheio de identificadores faz contagem de
   palavra virar ruído (o termo "commit" casou centenas de identificadores num repo
   com 23 citações reais de hash).
2. **Triagem de cada hit em uma de quatro ações** (leia a linha; não decida em lote):

   | ação | hits |
   |---|---|
   | REMOVER | rótulo puro (`P5`, `S-10`, `CHK-8`), um `(ac74518)` solto, narrativa ("hoje isso falha", "será implementado") |
   | REESCREVER | rótulo + fato → só o fato. A maioria. Se sobrar só o rótulo, remova. |
   | MANTER | o porquê: invariantes, ordem, regra de redação/segurança, tolerância a formato antigo, `# noqa` / `# type: ignore` |
   | NUNCA TOCAR | docstring de contrato (item 3), strings de `help=`/argparse, docstring de módulo ligada a `--help` (`description=__doc__`), mensagem de log/evento para o usuário |

3. **Ache a zona de contrato primeiro.** Só handler de rota (decorator
   `@router.<verbo>` / `@app.<verbo>`) e classe `BaseModel` publicam a docstring.
   Confirme no schema gerado e rode o check de sync do schema depois de cada lote que
   tocou um deles.
4. **Não instale guarda rígida de árvore inteira por padrão.** Um teste que falha em
   token marcador tem falsos positivos reais: palavras hex (`ed25519`), ids `BEH-`
   quando o time liga teste por nome, tokens legados em fixture congelada, citação
   histórica que um revisor quer manter. Se o time quiser enforcement, escopo em
   **linhas adicionadas** (`comment_scan.py --staged --fail`, no pre-commit ou no diff
   da CI), nunca na árvore toda, e com allowlist.
5. **Execute em lotes por área, um commit cada**, rodando o gate do repo (testes,
   lint, sync de schema) depois de cada um. Prove que o lote mudou só comentário:
   `python scripts/verify_comments_only.py <base> [HEAD]` tem que dar PASS no
   intervalo. Exceção deliberada (docstring que precisou mudar para continuar
   verdadeira) é aceitável — então verifique o diff daquele arquivo lendo.
6. **Termine pelos portadores de comentário fora do `.py`.** O scanner lê Python só:
   Makefile, `docker-compose.yml`, `.env.example`, CI e `pyproject.toml` carregam a
   mesma narração e sobrevivem a um scan "0 hits". Varra com a gramática de marcador
   e limpe num lote final. Arquivo local não versionado (AGENTS.md da máquina) fica
   corrigido em disco e nunca staged.
7. **Case com uma review.** Uma passada de higiene preserva afirmação falsa em prosa
   mais limpa: comentário pode ficar sem slop e errado depois do refactor. Pegue a
   lista de fatos a corrigir na review em que a passada está embutida, ou rode uma
   antes.

## Scanner

```bash
python scripts/comment_scan.py <roots>              # inventário (marcadores + sha)
python scripts/comment_scan.py <roots> --style      # + prosa: endereçamento, passo, tempo
python scripts/comment_scan.py --staged --fail      # gate de linhas adicionadas
python scripts/comment_scan.py --staged --style --fail
python scripts/comment_scan.py <roots> --json       # uma linha JSON por hit
python scripts/comment_scan.py <roots> --allow 'ADR-\d+|BEH-014'
```

Gramática de marcador: `\b(P\d+(?:\.\d+)?[a-z]?|S-\d+[a-z]?|CHK-\d+|INV-\d+|OQ-\d+|BEH-\d+|SC-\d+)\b`.
Sha conta só em `(abcd123)` ou depois de `commit `/`hash `. `--style` acrescenta três
famílias: `addressed` (fala com o solicitante), `step` (passo/fase/tarefa numerada) e
`tense` (passado/futuro: previously, used to, será implementado, antes era).
`--style` é desligado por padrão porque prosa tem falso positivo ("previously"
legítimo, "step" como nome de variável em texto); ligue no gate de linhas
adicionadas e mantenha allowlist.

`--staged` vê só linhas adicionadas, então hit legado nunca faz falhar. É o ponto:
scan de árvore inteira é inventário, não gate.

## Pitfalls

- **Não reescreva comentário que codifica regra de segurança/redação**, mesmo quando
  cita história: tire a citação, mantenha a frase do invariante intacta.
- **`verify_comments_only` PASS ≠ contrato igual.** Docstring é código em
  FastAPI/Pydantic — diff do schema gerado separado.
- **Não escaneie string literal** (o scan lê comentário e docstring): texto de
  usuário com referência a passo é edição separada e deliberada; mudar pode mudar
  comportamento ou saída.
- **`#` dentro de block scalar de YAML é payload, não comentário.** Num ConfigMap
  (`Corefile: |`) as linhas indentadas com `#` fazem parte do valor; "limpar" muda o
  objeto e a config servida. Prove que a edição de YAML é comment-only com
  `yaml.safe_load` antes/depois — objetos parseados idênticos, senão reverta.
- **Docstring de módulo pode ser saída de usuário.** `argparse(description=__doc__)`
  publica como `--help`; o lote que a muda regenera o golden do help no mesmo commit.
- **Confie em `contract_risk` só onde ele é preciso:** handler de rota e subclasse de
  `BaseModel`. Docstring de módulo em arquivo que importa pydantic NÃO é contrato.
- **Artefato de planejamento está fora de escopo.** `.specs/**/spec.yaml` e
  `plan.yaml` carregam ids de passo/check de propósito — o leitor navega o plano por
  eles. Nunca roteie esses arquivos para limpeza e exclua os tokens deles do
  inventário de código.

## Arquivos

- `scripts/comment_scan.py` — inventário (`--json`, `--staged`, `--style`, `--fail`, `--allow`).
- `scripts/verify_comments_only.py` — prova por AST que um intervalo git mudou só
  comentário/docstring.
