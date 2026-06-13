# Changelog

All notable changes to docpact will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-06-13

### Added
- **18 MCP tools** for autonomous agent integration
- **Formal specification** (7,366 lines): CONTRATO v2, MCP v2, Verification v1, Discovery v1, Versioning v1
- **FastEmbed semantic detection** with Jina-ES model for conflict detection
- **Agent context** in MCP initialize response with project stats and workflow
- **DOCPACT_AGENT_GUIDE.md** for agent onboarding
- **Doctor checks** for FastEmbed and project health
- **Conflict detection** (verificar_conflicto tool) for RN management
- **RN lifecycle tools**: listar_rns, crear_rn, explicar_rn
- **Project setup tool** (setup_docpact) for initialization
- **Verification tool** (ejecutar_verificacion) for full project checks
- **Test runner tool** (ejecutar_tests) for RN test execution
- **Report generator** (generar_reporte) for project metrics
- **Contract creation tool** (crear_contrato) from natural language
- **Contract fix tool** (corregir_contrato) for corrections
- **15 DRY argument helpers** for CLI commands
- **Argument registrar pattern** for CLI modules

### Changed
- **Orchestrator** split from 884 to 312 lines (+ 3 modules)
- **CLI main.py** reduced from 620 to 67 lines
- **semantic_rn.py** split into 5 validator modules
- **commands.py** split into 7 command modules
- **MCP tool descriptions** now self-contained with examples
- **Embedding model** upgraded from paraphrase-multilingual-mpnet-base-v2 to jina-embeddings-v2-base-es

### Fixed
- **Doctor NameError** in ejecutar function
- **Doctor TypeError** for string Path conversion
- **verify-rn KeyError** for missing 'mensaje' field

### Deprecated
- Legacy RN marker verification (use semantic validators instead)
- Vanity score metric (use honest metrics: rns_fake, rns_huerfanas)

## [0.5.1] - 2026-06-12

### Added
- Briefing generation for context handoff
- Guard system for runtime enforcement
- LLM judge for test quality evaluation
- Bridge between components

### Changed
- Improved side effects detection
- Enhanced marker honesty checker

## [0.5.0] - 2026-06-10

### Added
- MCP server v2 with 8 initial tools
- Semantic RN validators (5 types)
- Contract index for cross-function analysis
- Transitive effects detection

### Changed
- Improved parser for complex docstrings
- Enhanced TypeScript support

## [0.4.2] - 2026-06-08

### Added
- RN test checker
- RN registry checker
- Module boundary checker

### Fixed
- Edge cases in side effects detection

## [0.4.1] - 2026-06-06

### Added
- Signature checker for input/output validation
- Dependency verifier
- Import checker for duplicate imports

## [0.4.0] - 2026-06-04

### Added
- CLI with 21 commands
- Pre-commit hook support
- CI/CD integration

### Changed
- Improved error reporting

## [0.3.1] - 2026-06-02

### Added
- TypeScript/JSX support (regex-based)
- Configuration via docpact.toml

## [0.3.0] - 2026-05-30

### Added
- Side effects verification
- RN marker verification
- Basic scoring system

## [0.2.0] - 2026-05-28

### Added
- CONTRATO parser (lexer + parser)
- Python AST extractor
- Basic verification pipeline

## [0.1.0] - 2026-05-25

### Added
- Initial release
- Basic CONTRATO format support
