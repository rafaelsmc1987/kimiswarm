# Third-party notices

`kdrx` depends on:

- **Pydantic** (MIT) — schema modeling and JSON-Schema export.
  Copyright (c) Samuel Colvin and contributors.

This notice covers the kdrx Python package and kdr-x plugin only. Other directories under plugins contain separately sourced components with unresolved redistribution provenance; see audit/plugin-inventory.json. They are excluded from the kdr-x release artifacts. The referenced
research repositories (see `LICENSE_MATRIX.md`) were inspected for requirements
only; their code and prompts are not reproduced here.

## Runtime dependency

```
pydantic>=2.5
```

## Dev dependencies

```
pytest>=7.4
pytest-cov>=4.1
```
