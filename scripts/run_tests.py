#!/usr/bin/env python3
"""
Test runner script for Financial AI Agent.

Usage:
    python scripts/run_tests.py                    # Run all tests
    python scripts/run_tests.py --unit             # Unit tests only
    python scripts/run_tests.py --integration      # Integration tests only
    python scripts/run_tests.py --models           # Model tests only
    python scripts/run_tests.py --coverage         # With coverage report
    python scripts/run_tests.py --fast             # Skip slow tests
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_command(cmd: list[str], cwd: Path = project_root) -> int:
    """Run command and return exit code."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="Run tests for Financial AI Agent")
    
    # Test selection
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only") 
    parser.add_argument("--models", action="store_true", help="Run model tests only")
    parser.add_argument("--api", action="store_true", help="Run API tests only")
    
    # Test options
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", "-n", type=int, help="Number of parallel workers")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    
    # Specific test
    parser.add_argument("test_file", nargs="?", help="Specific test file to run")
    
    args = parser.parse_args()
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Test selection markers
    markers = []
    if args.unit:
        markers.append("unit")
    if args.integration:
        markers.append("integration") 
    if args.models:
        markers.append("models")
    if args.api:
        markers.append("api")
    
    if markers:
        cmd.extend(["-m", " or ".join(markers)])
    
    # Skip slow tests
    if args.fast:
        if markers:
            cmd[-1] += " and not slow"
        else:
            cmd.extend(["-m", "not slow"])
    
    # Coverage
    if args.coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=80"
        ])
    
    # Verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
    
    # Fail fast
    if args.fail_fast:
        cmd.append("-x")
    
    # Specific test file
    if args.test_file:
        cmd.append(args.test_file)
    else:
        cmd.append("tests/")
    
    # Add common options
    cmd.extend([
        "--tb=short",
        "--strict-markers",
        "--disable-warnings"
    ])
    
    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    env["APP_ENV"] = "test"
    
    # Run tests
    print("=" * 60)
    print("Running Financial AI Agent Tests")
    print("=" * 60)
    
    result = subprocess.run(cmd, env=env, cwd=project_root)
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
        if args.coverage:
            print("📊 Coverage report generated in htmlcov/")
    else:
        print(f"\n❌ Tests failed with exit code {result.returncode}")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())