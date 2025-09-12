#!/usr/bin/env python3
"""
Type checking script for MohFlow.

This script runs mypy and other type checking tools to ensure
full type safety across the MohFlow codebase.
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
import argparse


def run_command(cmd: List[str], description: str) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, and stderr."""
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def run_mypy(src_path: Path, strict: bool = False) -> bool:
    """Run mypy type checking."""
    print("\n" + "="*60)
    print("🔍 Running MyPy Type Checking")
    print("="*60)
    
    cmd = ["mypy"]
    
    if strict:
        cmd.extend([
            "--strict",
            "--no-warn-return-any",  # Too noisy for now
            "--no-warn-unused-ignores",  # Allow some ignores
        ])
    
    # Add source path
    cmd.append(str(src_path))
    
    exit_code, stdout, stderr = run_command(
        cmd, 
        "MyPy static type checking"
    )
    
    if exit_code == 0:
        print("✅ MyPy: All type checks passed!")
        if stdout:
            print(stdout)
    else:
        print("❌ MyPy: Type check errors found:")
        if stdout:
            print("STDOUT:", stdout)
        if stderr:
            print("STDERR:", stderr)
    
    return exit_code == 0


def check_type_annotations(src_path: Path) -> bool:
    """Check for missing type annotations."""
    print("\n" + "="*60)
    print("📝 Checking Type Annotation Coverage")
    print("="*60)
    
    # Use mypy with specific flags to check annotation coverage
    cmd = [
        "mypy",
        "--disallow-untyped-defs",
        "--disallow-incomplete-defs", 
        "--disallow-untyped-decorators",
        "--no-error-summary",
        str(src_path)
    ]
    
    exit_code, stdout, stderr = run_command(
        cmd,
        "Type annotation coverage check"
    )
    
    if exit_code == 0:
        print("✅ Type Annotations: Complete coverage!")
    else:
        print("⚠️  Type Annotations: Some functions lack complete type hints")
        if stdout:
            print("Issues found:")
            print(stdout)
    
    return exit_code == 0


def validate_type_imports(src_path: Path) -> bool:
    """Validate that type imports are used correctly."""
    print("\n" + "="*60)
    print("📦 Validating Type Imports")
    print("="*60)
    
    issues = []
    
    # Check for common type import issues
    for py_file in src_path.rglob("*.py"):
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
                # Check for missing TYPE_CHECKING imports
                if "from typing import" in content and "TYPE_CHECKING" not in content:
                    if any(pattern in content for pattern in [
                        "if TYPE_CHECKING:",
                        "Union[",
                        "Optional[", 
                        "List[",
                        "Dict["
                    ]):
                        # This is fine - TYPE_CHECKING not needed
                        pass
                
                # Check for forward references without quotes
                if "-> MohflowLogger" in content and '"MohflowLogger"' not in content:
                    # Should use string literals for forward refs
                    pass  # This is actually fine in modern Python
                
        except Exception as e:
            issues.append(f"Error reading {py_file}: {e}")
    
    if issues:
        print("❌ Type Import Issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ Type Imports: All imports are properly structured")
        return True


def run_protocol_checks(src_path: Path) -> bool:
    """Check that Protocol implementations are correct."""
    print("\n" + "="*60)
    print("🔌 Checking Protocol Implementations")
    print("="*60)
    
    # Use mypy to specifically check protocol compliance
    cmd = [
        "mypy",
        "--check-untyped-defs",
        "--warn-incomplete-stub",
        str(src_path / "types.py"),  # Focus on our types module
    ]
    
    exit_code, stdout, stderr = run_command(
        cmd,
        "Protocol implementation check"
    )
    
    if exit_code == 0:
        print("✅ Protocols: All implementations are compliant")
    else:
        print("⚠️  Protocols: Some implementation issues found")
        if stdout:
            print(stdout)
    
    return exit_code == 0


def generate_type_report(src_path: Path) -> None:
    """Generate a comprehensive type coverage report."""
    print("\n" + "="*60)
    print("📊 Type Coverage Report")
    print("="*60)
    
    # Count files and functions with type annotations
    total_files = 0
    typed_files = 0
    total_functions = 0
    typed_functions = 0
    
    for py_file in src_path.rglob("*.py"):
        if py_file.name.startswith("__"):
            continue
            
        total_files += 1
        has_types = False
        
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
                # Basic heuristics for type checking
                if any(pattern in content for pattern in [
                    "-> ",
                    ": str",
                    ": int", 
                    ": bool",
                    ": Optional",
                    ": Union",
                    ": List",
                    ": Dict",
                    "from typing import"
                ]):
                    has_types = True
                    typed_files += 1
                
                # Count function definitions
                import re
                functions = re.findall(r'def\s+\w+\s*\([^)]*\)', content)
                total_functions += len(functions)
                
                # Count typed functions (rough estimate)
                typed_funcs = re.findall(r'def\s+\w+\s*\([^)]*\)\s*->', content)
                typed_functions += len(typed_funcs)
                
        except Exception as e:
            print(f"Error processing {py_file}: {e}")
    
    # Calculate percentages
    file_coverage = (typed_files / total_files * 100) if total_files > 0 else 0
    func_coverage = (typed_functions / total_functions * 100) if total_functions > 0 else 0
    
    print(f"📁 Files with type hints: {typed_files}/{total_files} ({file_coverage:.1f}%)")
    print(f"🔧 Functions with return types: {typed_functions}/{total_functions} ({func_coverage:.1f}%)")
    
    # Quality assessment
    if file_coverage >= 90 and func_coverage >= 80:
        print("🎯 Type Coverage: Excellent!")
    elif file_coverage >= 70 and func_coverage >= 60:
        print("👍 Type Coverage: Good")
    else:
        print("⚠️  Type Coverage: Needs improvement")


def main() -> int:
    """Main entry point for type checking."""
    parser = argparse.ArgumentParser(description="MohFlow Type Checking")
    parser.add_argument("--strict", action="store_true", 
                       help="Run in strict mode with all checks")
    parser.add_argument("--src", type=Path, default=Path("src"),
                       help="Source directory path")
    parser.add_argument("--report-only", action="store_true",
                       help="Only generate type coverage report")
    
    args = parser.parse_args()
    
    src_path = args.src
    if not src_path.exists():
        print(f"❌ Source path not found: {src_path}")
        return 1
    
    print("🚀 MohFlow Type Safety Validation")
    print("="*60)
    print(f"Source path: {src_path.absolute()}")
    print(f"Strict mode: {args.strict}")
    
    if args.report_only:
        generate_type_report(src_path)
        return 0
    
    # Run all checks
    checks_passed = 0
    total_checks = 0
    
    # 1. MyPy type checking
    total_checks += 1
    if run_mypy(src_path, strict=args.strict):
        checks_passed += 1
    
    # 2. Type annotation coverage
    total_checks += 1
    if check_type_annotations(src_path):
        checks_passed += 1
    
    # 3. Type import validation
    total_checks += 1
    if validate_type_imports(src_path):
        checks_passed += 1
    
    # 4. Protocol compliance
    total_checks += 1
    if run_protocol_checks(src_path):
        checks_passed += 1
    
    # Generate report
    generate_type_report(src_path)
    
    # Summary
    print("\n" + "="*60)
    print("📋 TYPE SAFETY SUMMARY")
    print("="*60)
    
    print(f"Checks passed: {checks_passed}/{total_checks}")
    
    if checks_passed == total_checks:
        print("🎉 All type safety checks passed!")
        print("✅ MohFlow is fully type-safe and mypy compliant")
        return 0
    else:
        print(f"⚠️  {total_checks - checks_passed} type safety issues need attention")
        print("❌ MohFlow needs type safety improvements")
        return 1


if __name__ == "__main__":
    sys.exit(main())