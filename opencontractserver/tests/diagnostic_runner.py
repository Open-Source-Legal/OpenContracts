"""
Diagnostic test runner that tracks async resource leaks.

Usage:
    Add to settings:
        TEST_RUNNER = 'opencontractserver.tests.diagnostic_runner.DiagnosticTestRunner'

    Or run directly:
        python manage.py test --testrunner=opencontractserver.tests.diagnostic_runner.DiagnosticTestRunner
"""

import asyncio
import gc
import traceback
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.test.runner import DiscoverRunner


class AsyncResourceTracker:
    """Track async resources created during tests."""

    def __init__(self):
        self.resources_by_test = defaultdict(
            lambda: {
                "generators_created": [],
                "generators_closed": [],
                "coroutines_created": [],
                "coroutines_completed": [],
                "warnings": [],
            }
        )
        self.current_test = None
        self.event_loop_states = []

    def start_test(self, test_name):
        """Mark start of a test."""
        self.current_test = test_name
        self.event_loop_states.append(
            {
                "test": test_name,
                "event": "start",
                "timestamp": datetime.now().isoformat(),
                "loop_state": self._get_loop_state(),
            }
        )

    def end_test(self, test_name):
        """Mark end of a test."""
        self.event_loop_states.append(
            {
                "test": test_name,
                "event": "end",
                "timestamp": datetime.now().isoformat(),
                "loop_state": self._get_loop_state(),
            }
        )

        # Force garbage collection and check for leaks
        gc.collect()
        leaked_gens = self._find_leaked_generators()
        leaked_coros = self._find_leaked_coroutines()

        if leaked_gens or leaked_coros:
            self.resources_by_test[test_name]["leaked_generators"] = leaked_gens
            self.resources_by_test[test_name]["leaked_coroutines"] = leaked_coros

    def _get_loop_state(self):
        """Get current event loop state."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                return "CLOSED"
            tasks = asyncio.all_tasks(loop)
            return f"OPEN ({len(tasks)} tasks)"
        except RuntimeError as e:
            return f"NO_LOOP ({e})"

    def _find_leaked_generators(self):
        """Find async generators that weren't closed."""
        # Simplified - rely on warnings instead of object inspection
        # to avoid Celery proxy issues
        return []

    def _find_leaked_coroutines(self):
        """Find coroutines that weren't awaited."""
        # Simplified - rely on warnings instead of object inspection
        # to avoid Celery proxy issues
        return []

    def record_warning(self, message, test_name=None):
        """Record a warning."""
        test = test_name or self.current_test
        self.resources_by_test[test]["warnings"].append(
            {
                "message": str(message),
                "timestamp": datetime.now().isoformat(),
                "stack": traceback.format_stack(),
            }
        )

    def generate_report(self):
        """Generate diagnostic report."""
        report = []
        report.append("=" * 80)
        report.append("ASYNC RESOURCE DIAGNOSTICS REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}\n")

        # Summary
        total_tests = len(self.resources_by_test)
        tests_with_leaks = sum(
            1
            for data in self.resources_by_test.values()
            if data.get("leaked_generators") or data.get("leaked_coroutines")
        )
        tests_with_warnings = sum(
            1 for data in self.resources_by_test.values() if data.get("warnings")
        )

        report.append("SUMMARY")
        report.append("-" * 80)
        report.append(f"Total tests run: {total_tests}")
        report.append(f"Tests with resource leaks: {tests_with_leaks}")
        report.append(f"Tests with warnings: {tests_with_warnings}\n")

        # Tests with issues
        if tests_with_leaks or tests_with_warnings:
            report.append("TESTS WITH ISSUES")
            report.append("-" * 80)

            for test_name, data in sorted(self.resources_by_test.items()):
                leaked_gens = data.get("leaked_generators", [])
                leaked_coros = data.get("leaked_coroutines", [])
                warnings_list = data.get("warnings", [])

                if leaked_gens or leaked_coros or warnings_list:
                    report.append(f"\n{test_name}:")

                    if leaked_gens:
                        report.append(f"  Leaked async generators: {len(leaked_gens)}")
                        for gen in leaked_gens[:3]:  # Show first 3
                            report.append(f"    - {gen['qualname']}")
                        if len(leaked_gens) > 3:
                            report.append(f"    ... and {len(leaked_gens) - 3} more")

                    if leaked_coros:
                        report.append(f"  Leaked coroutines: {len(leaked_coros)}")
                        for coro in leaked_coros[:3]:  # Show first 3
                            report.append(f"    - {coro['qualname']}")
                        if len(leaked_coros) > 3:
                            report.append(f"    ... and {len(leaked_coros) - 3} more")

                    if warnings_list:
                        report.append(f"  Warnings: {len(warnings_list)}")
                        for warn in warnings_list[:2]:  # Show first 2
                            report.append(f"    - {warn['message']}")
                        if len(warnings_list) > 2:
                            report.append(f"    ... and {len(warnings_list) - 2} more")

        # Event loop state timeline
        report.append("\n\nEVENT LOOP STATE TIMELINE")
        report.append("-" * 80)
        for i, state in enumerate(self.event_loop_states[-50:]):  # Last 50 events
            report.append(
                f"{i+1}. [{state['timestamp']}] {state['test']} ({state['event']}) - {state['loop_state']}"
            )

        return "\n".join(report)


# Global tracker
_tracker = None


def get_tracker():
    """Get or create the global tracker."""
    global _tracker
    if _tracker is None:
        _tracker = AsyncResourceTracker()
    return _tracker


class DiagnosticTestRunner(DiscoverRunner):
    """Test runner with async diagnostics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = get_tracker()

        # Setup warning capture
        self.original_warn = warnings.warn

        def custom_warn(message, category=UserWarning, stacklevel=1):
            if "was never awaited" in str(message) or "async" in str(message).lower():
                self.tracker.record_warning(message)
            self.original_warn(message, category, stacklevel)

        warnings.warn = custom_warn

        print("[DiagnosticTestRunner] Async resource tracking ENABLED")

    def run_suite(self, suite, **kwargs):
        """Run test suite with diagnostics."""
        print("[DiagnosticTestRunner] Starting test suite with async diagnostics...")

        # Wrap each test to track resources
        for test in suite:
            test_name = str(test)
            original_run = test.run

            def tracked_run(result=None, test_name=test_name, orig=original_run):
                self.tracker.start_test(test_name)
                try:
                    return orig(result)
                finally:
                    self.tracker.end_test(test_name)

            test.run = tracked_run

        # Run the suite
        result = super().run_suite(suite, **kwargs)

        # Generate and save report
        report = self.tracker.generate_report()
        report_path = Path("/tmp/async_diagnostic_report.txt")
        report_path.write_text(report)

        print(f"\n{'='*80}")
        print(f"Async diagnostics report saved to: {report_path}")
        print(f"{'='*80}\n")

        # Print summary to console
        print(report.split("EVENT LOOP STATE TIMELINE")[0])

        return result

    def teardown_test_environment(self, **kwargs):
        """Cleanup and final report."""
        print("\n[DiagnosticTestRunner] Generating final async diagnostics report...")

        # Final garbage collection
        gc.collect()

        # Final check for lingering resources
        loop_state = self.tracker._get_loop_state()
        print(f"[DiagnosticTestRunner] Final event loop state: {loop_state}")

        super().teardown_test_environment(**kwargs)
