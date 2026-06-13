"""CLI command modules for docpact.

Each module handles a group of related commands:
- check: Core verification (check, lint, validate, verify-rn)
- extract: Extraction & indexing (extract, index, traceability)
- test: Testing (test, test-quality, llm-judge)
- mcp: MCP integration (mcp, mcp-doctor, install-mcp)
- generate: Code generation (fix, init, config-suggest)
- report: Reporting (report, briefing)
- runtime: Runtime (guard, run, doctor)
"""

from docpact.cli.commands.check import (
    cmd_check,
    cmd_lint,
    cmd_validate,
    cmd_verify_rns,
)
from docpact.cli.commands.extract import (
    cmd_extract,
    cmd_index,
    cmd_traceability,
)
from docpact.cli.commands.test import (
    cmd_test,
    cmd_test_quality,
    cmd_llm_judge,
)
from docpact.cli.commands.mcp import (
    cmd_mcp,
    cmd_mcp_doctor,
    cmd_install_mcp,
)
from docpact.cli.commands.generate import (
    cmd_fix,
    cmd_init,
    cmd_config_suggest,
)
from docpact.cli.commands.report import (
    cmd_report,
    cmd_briefing,
)
from docpact.cli.commands.runtime import (
    cmd_guard,
    cmd_run,
    cmd_doctor,
)

__all__ = [
    # check
    "cmd_check",
    "cmd_lint",
    "cmd_validate",
    "cmd_verify_rns",
    # extract
    "cmd_extract",
    "cmd_index",
    "cmd_traceability",
    # test
    "cmd_test",
    "cmd_test_quality",
    "cmd_llm_judge",
    # mcp
    "cmd_mcp",
    "cmd_mcp_doctor",
    "cmd_install_mcp",
    # generate
    "cmd_fix",
    "cmd_init",
    "cmd_config_suggest",
    # report
    "cmd_report",
    "cmd_briefing",
    # runtime
    "cmd_guard",
    "cmd_run",
    "cmd_doctor",
]
