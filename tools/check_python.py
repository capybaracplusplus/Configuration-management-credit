"""Check structural limits that do not require a Python linter."""

import ast
from pathlib import Path

MAX_FUNCTION_LINES = 40
MAX_ARGUMENTS = 7
FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
DOCUMENTED_TYPES = (ast.Module, ast.ClassDef, *FUNCTION_TYPES)


def argument_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count positional, keyword-only, and variadic arguments."""
    arguments = node.args
    return (
        len(arguments.posonlyargs)
        + len(arguments.args)
        + len(arguments.kwonlyargs)
        + bool(arguments.vararg)
        + bool(arguments.kwarg)
    )


def function_problems(
    path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str]:
    """Report function length and parameter-count violations."""
    issues = []
    starts = [node.lineno, *(item.lineno for item in node.decorator_list)]
    start = min(starts)
    length = (node.end_lineno or node.lineno) - start + 1
    label = f"{path}:{node.lineno}: {node.name}"
    if length > MAX_FUNCTION_LINES:
        issues.append(f"{label}: {length} lines; maximum {MAX_FUNCTION_LINES}")
    count = argument_count(node)
    if count > MAX_ARGUMENTS:
        issues.append(f"{label}: {count} arguments; maximum {MAX_ARGUMENTS}")
    return issues


def python_problems(path: Path, content: str) -> list[str]:
    """Parse Python code and collect its structural violations."""
    try:
        tree = ast.parse(content, filename=str(path))
    except SyntaxError as error:
        return [f"{path}:{error.lineno}: {error.msg}"]
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, FUNCTION_TYPES):
            issues.extend(function_problems(path, node))
        if path.parts[0] in {"src", "tools"}:
            issues.extend(documentation_problems(path, node))
    return issues


def documentation_problems(path: Path, node: ast.AST) -> list[str]:
    """Require docstrings on production modules, classes, and functions."""
    if not isinstance(node, DOCUMENTED_TYPES) or ast.get_docstring(node):
        return []
    label = getattr(node, "name", "module")
    line = getattr(node, "lineno", 1)
    return [f"{path}:{line}: missing docstring for {label}"]
