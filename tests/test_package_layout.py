from __future__ import annotations

import importlib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_new_subpackage_imports_are_available(self) -> None:
        module_names = [
            "model_console.cli",
            "model_console.core.engine",
            "model_console.core.workflow",
            "model_console.core.run_state",
            "model_console.core.role_assignment",
            "model_console.core.reviews",
            "model_console.core.gitops",
            "model_console.agents.executor",
            "model_console.agents.command_builder",
            "model_console.agents.eval",
            "model_console.agents.mock",
            "model_console.contracts.config",
            "model_console.contracts.prompts",
            "model_console.contracts.validator",
            "model_console.observability.logging",
            "model_console.observability.reporting",
            "model_console.observability.transcript",
            "model_console.observability.transcript_viewer",
            "model_console.runtime",
            "model_console.safety.command_policy",
        ]

        for module_name in module_names:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_legacy_imports_match_restructured_modules(self) -> None:
        from model_console.engine import LoopEngine as legacy_loop_engine
        from model_console.executors import AgentExecutor as legacy_executor
        from model_console.config import load_app_config as legacy_load_app_config
        from model_console.safety import assert_command_safe as legacy_assert_command_safe

        from model_console.core.engine import LoopEngine
        from model_console.agents.executor import AgentExecutor
        from model_console.contracts.config import load_app_config
        from model_console.safety.command_policy import assert_command_safe

        self.assertIs(legacy_loop_engine, LoopEngine)
        self.assertIs(legacy_executor, AgentExecutor)
        self.assertIs(legacy_load_app_config, load_app_config)
        self.assertIs(legacy_assert_command_safe, assert_command_safe)

class ScriptPortabilityTests(unittest.TestCase):
    def test_scripts_do_not_hardcode_local_home_paths(self) -> None:
        for relative_path in [
            "scripts/run_product_brief_batch.py",
            "scripts/generate_product_brief_input.py",
        ]:
            with self.subTest(path=relative_path):
                content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertNotIn("/Users/magare/", content)
