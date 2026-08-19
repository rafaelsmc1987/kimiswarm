# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x (main) | ✅ |

## Reporting a Vulnerability

**NÃO abra issue pública para vulnerabilidades.** Use o GitHub Private Vulnerability
Reporting ("Security" → "Report a vulnerability") em
<https://github.com/rafaelsmc1987/kimiswarm> ou contate os mantenedores diretamente.

Inclua: descrição, impacto, passos de reprodução e commit afetado.

Resposta esperada: reconhecimento em 72h; avaliação inicial em 7 dias.

## Escopo

- O pipeline KDR-X (`src/kdrx/`), o plugin Claude Code (`plugins/kdr-x/`) e os hooks.
- **Vazamento de segredos:** se encontrar qualquer credencial neste repositório,
  reporte IMEDIATAMENTE como vulnerabilidade crítica (contexto: auditoria de
  2026-08-19, blocker B-01 — remediação em andamento no plano de correção).

## Notas

- `evidence-manifest/` contém apenas paths + SHA256 (índice sanitizado); não contém
  segredos por construção.
- Scanners de segredos (gitleaks, detect-secrets) rodam localmente e em CI; ver
  `.gitleaks.toml` e `.secrets.baseline`.
- O teste `tests/test_repo_hygiene.py` falha se paths proibidos (`.ssh/`, `*.har`,
  dumps de sandbox, corpus forense) reaparecerem na árvore tracked.
