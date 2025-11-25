"""
Enhanced diagnostic test runner to identify async pollution sources.

This runner uses Python's async generator hooks and warning filters to track
async resource leaks without inspecting objects (avoiding Celery proxy issues).

Usage:
    TEST_RUNNER = 'opencontractserver.tests.enhanced_diagnostic_runner.EnhancedDiagnosticTestRunner'
"""

import sys
import traceback
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.test.runner import DiscoverRunner


class AsyncResourceDiagnostics:
    """Track async resources without object inspection."""

    def __init__(self):
        self.current_test = None
        self.resources_by_test = defaultdict(
            lambda: {
                "async_generators_created": [],
                "async_generators_finalized": [],
                "unawaited_coroutines": [],
                "warnings": [],
            }
        )
        self.global_async_gen_count = 0
        self.global_async_gen_finalized_count = 0

    def start_test(self, test_name):
        """Called when a test starts."""
        self.current_test = test_name

    def end_test(self, test_name):
        """Called when a test ends."""
        # Write periodic reports after every test
        self._write_periodic_report()

    def track_async_gen_created(self, gen):
        """Hook called when async generator is created."""
        self.global_async_gen_count += 1
        stack = "".join(traceback.format_stack()[:-1])  # Exclude this frame

        info = {
            "test": self.current_test,
            "timestamp": datetime.now().isoformat(),
            "stack_trace": stack,
            "global_count": self.global_async_gen_count,
        }

        if self.current_test:
            self.resources_by_test[self.current_test][
                "async_generators_created"
            ].append(info)

    def track_async_gen_finalized(self, gen):
        """Hook called when async generator is finalized."""
        self.global_async_gen_finalized_count += 1

        info = {
            "test": self.current_test,
            "timestamp": datetime.now().isoformat(),
            "global_count": self.global_async_gen_finalized_count,
        }

        if self.current_test:
            self.resources_by_test[self.current_test][
                "async_generators_finalized"
            ].append(info)

    def track_unawaited_coroutine(self, message, category):
        """Called when unawaited coroutine warning is issued."""
        stack = "".join(traceback.format_stack()[:-2])  # Exclude warning frames

        info = {
            "test": self.current_test,
            "message": str(message),
            "category": category.__name__,
            "timestamp": datetime.now().isoformat(),
            "stack_trace": stack,
        }

        if self.current_test:
            self.resources_by_test[self.current_test]["unawaited_coroutines"].append(
                info
            )

    def generate_report(self):
        """Generate comprehensive diagnostic report."""
        report = []
        report.append("=" * 80)
        report.append("ENHANCED ASYNC DIAGNOSTICS REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}\n")

        # Global statistics
        report.append("GLOBAL ASYNC GENERATOR STATISTICS")
        report.append("-" * 80)
        report.append(f"Total async generators created: {self.global_async_gen_count}")
        report.append(
            f"Total async generators finalized: {self.global_async_gen_finalized_count}"
        )
        leaked_count = (
            self.global_async_gen_count - self.global_async_gen_finalized_count
        )
        report.append(f"Leaked async generators: {leaked_count}")

        if leaked_count > 0:
            report.append(
                f"\n⚠️  WARNING: {leaked_count} async generators were not properly finalized!\n"
            )

        # Per-test analysis
        report.append("\nPER-TEST ASYNC RESOURCE ANALYSIS")
        report.append("-" * 80)

        tests_with_issues = []

        for test_name, data in sorted(self.resources_by_test.items()):
            gens_created = len(data["async_generators_created"])
            gens_finalized = len(data["async_generators_finalized"])
            unawaited = len(data["unawaited_coroutines"])

            leaked_in_test = gens_created - gens_finalized

            if leaked_in_test > 0 or unawaited > 0:
                tests_with_issues.append(
                    {
                        "name": test_name,
                        "leaked": leaked_in_test,
                        "unawaited": unawaited,
                        "data": data,
                    }
                )

        if tests_with_issues:
            report.append(
                f"\nFound {len(tests_with_issues)} tests with async resource issues:\n"
            )

            for issue in tests_with_issues:
                report.append(f"\n{'=' * 80}")
                report.append(f"TEST: {issue['name']}")
                report.append(f"{'=' * 80}")

                if issue["leaked"] > 0:
                    report.append(f"\n  Leaked async generators: {issue['leaked']}")
                    report.append("\n  Creation locations:")

                    for i, gen_info in enumerate(
                        issue["data"]["async_generators_created"][:3]
                    ):
                        report.append(f"\n  [{i+1}] Created at {gen_info['timestamp']}")
                        report.append(
                            f"      Global count at creation: {gen_info['global_count']}"
                        )
                        # Show last 5 frames of stack trace
                        stack_lines = gen_info["stack_trace"].strip().split("\n")
                        report.append("      Stack trace (last 5 frames):")
                        for line in stack_lines[-10:]:
                            report.append(f"        {line}")

                    if len(issue["data"]["async_generators_created"]) > 3:
                        remaining = len(issue["data"]["async_generators_created"]) - 3
                        report.append(
                            f"\n  ... and {remaining} more async generator(s) created in this test"
                        )

                if issue["unawaited"] > 0:
                    report.append(f"\n  Unawaited coroutines: {issue['unawaited']}")

                    for i, coro_info in enumerate(
                        issue["data"]["unawaited_coroutines"][:3]
                    ):
                        report.append(f"\n  [{i+1}] {coro_info['message']}")
                        report.append(f"      Detected at: {coro_info['timestamp']}")
                        # Show last 5 frames of stack trace
                        stack_lines = coro_info["stack_trace"].strip().split("\n")
                        report.append("      Stack trace (last 5 frames):")
                        for line in stack_lines[-10:]:
                            report.append(f"        {line}")

                    if len(issue["data"]["unawaited_coroutines"]) > 3:
                        remaining = len(issue["data"]["unawaited_coroutines"]) - 3
                        report.append(
                            f"\n  ... and {remaining} more unawaited coroutine(s) in this test"
                        )
        else:
            report.append("\n✅ No tests with async resource issues detected!")

        # Accumulation pattern analysis
        if self.global_async_gen_count > 0:
            report.append("\n\nACCUMULATION PATTERN ANALYSIS")
            report.append("-" * 80)

            cumulative_created = 0
            cumulative_finalized = 0

            for test_name in sorted(self.resources_by_test.keys()):
                data = self.resources_by_test[test_name]
                created = len(data["async_generators_created"])
                finalized = len(data["async_generators_finalized"])

                cumulative_created += created
                cumulative_finalized += finalized
                cumulative_leaked = cumulative_created - cumulative_finalized

                if created > 0 or finalized > 0:
                    report.append(
                        f"{test_name[:70]:<70} | "
                        f"Created: {created:2d} | "
                        f"Finalized: {finalized:2d} | "
                        f"Cumulative leaked: {cumulative_leaked:3d}"
                    )

                    if cumulative_leaked > 20:  # Highlight problematic accumulation
                        report.append(
                            "  ⚠️  HIGH ACCUMULATION - Event loop pollution likely!"
                        )

        return "\n".join(report)

    def _write_periodic_report(self):
        """Write periodic diagnostic report after each test."""
        try:
            report = self.generate_report()
            report_path = Path("/tmp/enhanced_async_diagnostic_periodic.txt")
            report_path.write_text(report)
        except Exception as e:
            # Don't let reporting errors break test execution
            print(f"Warning: Failed to write periodic report: {e}")


# Global diagnostics instance
_diagnostics = None


def get_diagnostics():
    """Get or create global diagnostics instance."""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = AsyncResourceDiagnostics()
    return _diagnostics


class EnhancedDiagnosticTestRunner(DiscoverRunner):
    """Test runner with enhanced async diagnostics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostics = get_diagnostics()

        # Setup async generator hooks
        def firstiter_hook(gen):
            """Called when async generator is iterated for first time."""
            self.diagnostics.track_async_gen_created(gen)

        def finalizer_hook(gen):
            """Called when async generator is finalized."""
            self.diagnostics.track_async_gen_finalized(gen)

        sys.set_asyncgen_hooks(firstiter=firstiter_hook, finalizer=finalizer_hook)

        # Setup warning filter for unawaited coroutines
        original_showwarning = warnings.showwarning

        def custom_showwarning(
            message, category, filename, lineno, file=None, line=None
        ):
            if "was never awaited" in str(message) or category == RuntimeWarning:
                self.diagnostics.track_unawaited_coroutine(message, category)
            # Still show the original warning
            original_showwarning(message, category, filename, lineno, file, line)

        warnings.showwarning = custom_showwarning
        warnings.simplefilter("default", RuntimeWarning)

        print("\n" + "=" * 80)
        print("ENHANCED ASYNC DIAGNOSTIC MODE ENABLED")
        print("=" * 80)
        print("Tracking:")
        print("  - Async generator creation and finalization")
        print("  - Unawaited coroutines")
        print("  - Stack traces for all async resource issues")
        print("=" * 80 + "\n")

    def run_suite(self, suite, **kwargs):
        """Run test suite with per-test tracking."""

        # Wrap each test
        for test in suite:
            test_name = str(test)
            original_run = test.run

            def tracked_run(result=None, test_name=test_name, orig=original_run):
                self.diagnostics.start_test(test_name)
                try:
                    return orig(result)
                finally:
                    self.diagnostics.end_test(test_name)

            test.run = tracked_run

        # Run the suite
        result = super().run_suite(suite, **kwargs)

        # Generate and save report
        report = self.diagnostics.generate_report()
        report_path = Path("/tmp/enhanced_async_diagnostic.txt")
        report_path.write_text(report)

        print(f"\n{'=' * 80}")
        print(f"Enhanced diagnostic report saved to: {report_path}")
        print(f"{'=' * 80}\n")

        # Print key findings to console
        print(report)

        return result
