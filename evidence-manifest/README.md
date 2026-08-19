# evidence-manifest — Índice Sanitizado do Corpus Forense

Gerado em 2026-08-19 pela task **T-00-02** do plano `kdrx-correcao-auditoria`.

## O que é

Inventário de todos os arquivos **não-produto** versionados no repositório
`rafaelsmc1987/kimiswarm` @ `37ee7c4e10f7bbf6b2cbc288d16545fb1111f48b`, ANTES da
remoção/movimentação (T-00-03/T-00-04). Serve como prova do que existia e do que foi
retirado da árvore de produto.

## Conteúdo

- `manifest.jsonl` — uma linha JSON por arquivo: `{"path", "size_bytes", "sha256"}`.
  **4.138 entradas, 0 ilegíveis.**
- `summary.json` — totais, regra de classificação, commit e timestamp.

## Garantia de sanitização

**Nenhum byte de conteúdo foi copiado.** Apenas paths, tamanhos e hashes SHA256
(one-way). Arquivos com nomes sensíveis (ex.: `s6/container_environment/SSH_PASSWORD`)
aparecem apenas como path + hash — o valor original permanece apenas no arquivo
original, que será movido para storage privado em T-00-03.

## Regra de classificação

- **Produto (ficam no repo):** `src/`, `plugins/`, `tests/`, `docs/`, `.claude/`,
  `pyproject.toml`, `.gitignore`, `.gitattributes`, `README.md` → 113 arquivos.
- **Não-produto (saem para o corpus forense):** todo o restante → 4.138 arquivos,
  354.529.475 bytes (~338 MB).

## Verificação

- Spot-check: SHA256 de `.ssh/authorized_keys` recomputado via `Get-FileHash` = hash do
  manifesto (MATCH).
- Scan de padrões de segredo no manifesto: 29 ocorrências, todas substrings de PATH
  (ex.: `glab-token/`, `secret-scan.sh`) ou falsos positivos de regex (`sk-` dentro de
  `risk-`/`dusk-`). Nenhum valor secreto presente.
