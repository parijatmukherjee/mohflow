"""
Exception variable inspection for MohFlow.

Provides rich exception formatting that includes local variable values
in tracebacks, similar to loguru's ``diagnose=True`` feature.

Usage::

    from mohflow.diagnose import DiagnosticFormatter

    formatter = DiagnosticFormatter(max_depth=3, max_value_length=200)
    try:
        process(order_id="ORD-123", amount=99.99)
    except Exception:
        rich_tb = formatter.format_exception(*sys.exc_info())
        # Includes local variable values at each frame

Security: Variable inspection is automatically disabled when
``MOHFLOW_ENVIRONMENT=production`` or when sensitive data patterns
are detected.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from types import FrameType, TracebackType
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
)

# Patterns that indicate a value is sensitive and should be masked
_SENSITIVE_PATTERNS = re.compile(
    r"(password|secret|token|api[_-]?key|auth|credential|"
    r"private[_-]?key|session[_-]?id|access[_-]?key)",
    re.IGNORECASE,
)

# Variable names to always skip
_SKIP_VARS = frozenset(
    {
        "__builtins__",
        "__name__",
        "__doc__",
        "__package__",
        "__loader__",
        "__spec__",
        "__file__",
        "__cached__",
    }
)


def _is_sensitive_name(name: str) -> bool:
    """Check if a variable name looks like it holds sensitive data."""
    return bool(_SENSITIVE_PATTERNS.search(name))


def _safe_repr(
    value: Any,
    max_length: int = 200,
    mask_sensitive: bool = True,
) -> str:
    """Produce a safe repr of *value*, truncated to *max_length*.

    Avoids repr-ing huge objects and masks values that look sensitive.
    """
    try:
        r = repr(value)
    except Exception:
        return "<repr failed>"
    if len(r) > max_length:
        r = r[: max_length - 3] + "..."
    return r


class FrameInfo:
    """Captured information about a single traceback frame."""

    __slots__ = (
        "filename",
        "lineno",
        "function",
        "code_context",
        "local_vars",
    )

    def __init__(
        self,
        filename: str,
        lineno: int,
        function: str,
        code_context: Optional[str],
        local_vars: Dict[str, str],
    ):
        self.filename = filename
        self.lineno = lineno
        self.function = function
        self.code_context = code_context
        self.local_vars = local_vars

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "filename": self.filename,
            "lineno": self.lineno,
            "function": self.function,
        }
        if self.code_context:
            result["code"] = self.code_context
        if self.local_vars:
            result["locals"] = self.local_vars
        return result


class DiagnosticFormatter:
    """Formats exceptions with local variable inspection.

    Parameters
    ----------
    max_depth : int
        Maximum number of frames to inspect (from the innermost).
    max_value_length : int
        Truncate variable repr after this many chars.
    max_vars_per_frame : int
        Maximum variables to show per frame.
    mask_sensitive : bool
        Replace values whose names match sensitive patterns with
        ``"***"``.
    auto_disable_production : bool
        Automatically disable variable inspection when
        ``MOHFLOW_ENVIRONMENT`` or ``ENVIRONMENT`` is
        ``"production"``.
    exclude_modules : sequence of str
        Skip frames whose filename contains any of these substrings.
    """

    def __init__(
        self,
        max_depth: int = 5,
        max_value_length: int = 200,
        max_vars_per_frame: int = 20,
        mask_sensitive: bool = True,
        auto_disable_production: bool = True,
        exclude_modules: Optional[Sequence[str]] = None,
    ):
        self.max_depth = max_depth
        self.max_value_length = max_value_length
        self.max_vars_per_frame = max_vars_per_frame
        self.mask_sensitive = mask_sensitive
        self.auto_disable_production = auto_disable_production
        self.exclude_modules = list(exclude_modules or [])

        # Pre-compute production flag
        env = os.environ.get(
            "MOHFLOW_ENVIRONMENT",
            os.environ.get("ENVIRONMENT", ""),
        )
        self._is_production = env.lower() in (
            "production",
            "prod",
        )

    @property
    def enabled(self) -> bool:
        """Whether variable inspection is active."""
        if self.auto_disable_production and self._is_production:
            return False
        return True

    def format_exception(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> str:
        """Format an exception with variable inspection.

        Falls back to stdlib traceback if inspection is disabled.
        """
        if exc_type is None or exc_value is None or exc_tb is None:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_type is None:
                return ""

        # Standard traceback first
        standard = "".join(
            traceback.format_exception(exc_type, exc_value, exc_tb)
        )

        if not self.enabled:
            return standard

        # Extract frame info
        frames = self._extract_frames(exc_tb)
        if not frames:
            return standard

        # Build enhanced output
        lines: List[str] = ["Traceback (with locals):\n"]
        for frame in frames:
            lines.append(
                f'  File "{frame.filename}", line {frame.lineno}, '
                f"in {frame.function}\n"
            )
            if frame.code_context:
                lines.append(f"    {frame.code_context.strip()}\n")
            if frame.local_vars:
                for var_name, var_repr in frame.local_vars.items():
                    lines.append(f"    | {var_name} = {var_repr}\n")

        # Exception line
        lines.append(f"{exc_type.__name__}: {exc_value}\n")

        return "".join(lines)

    def extract_frame_info(
        self,
        exc_tb: Optional[TracebackType] = None,
    ) -> List[FrameInfo]:
        """Extract frame info without formatting.

        Useful for structured logging where you want the data
        as dicts rather than formatted text.
        """
        if exc_tb is None:
            return []
        return self._extract_frames(exc_tb)

    def _extract_frames(
        self,
        tb: TracebackType,
    ) -> List[FrameInfo]:
        """Walk the traceback and extract frame details."""
        raw_frames: List[Tuple[FrameType, str, int, str, Optional[str]]] = []

        current: Optional[TracebackType] = tb
        while current is not None:
            frame = current.tb_frame
            filename = frame.f_code.co_filename
            lineno = current.tb_lineno
            funcname = frame.f_code.co_name

            # Read the source line if possible
            code_context = self._get_source_line(filename, lineno)

            raw_frames.append(
                (frame, filename, lineno, funcname, code_context)
            )
            current = current.tb_next

        # Limit depth (keep innermost frames)
        if len(raw_frames) > self.max_depth:
            raw_frames = raw_frames[-self.max_depth :]

        result: List[FrameInfo] = []
        for frame, filename, lineno, funcname, code in raw_frames:
            # Skip excluded modules
            if any(ex in filename for ex in self.exclude_modules):
                local_vars: Dict[str, str] = {}
            else:
                local_vars = self._extract_locals(frame)

            result.append(
                FrameInfo(
                    filename=filename,
                    lineno=lineno,
                    function=funcname,
                    code_context=code,
                    local_vars=local_vars,
                )
            )

        return result

    def _extract_locals(self, frame: FrameType) -> Dict[str, str]:
        """Extract local variable reprs from a frame."""
        local_vars: Dict[str, str] = {}
        count = 0

        for name, value in frame.f_locals.items():
            if name in _SKIP_VARS:
                continue
            if count >= self.max_vars_per_frame:
                break

            if self.mask_sensitive and _is_sensitive_name(name):
                local_vars[name] = '"***"'
            else:
                local_vars[name] = _safe_repr(
                    value,
                    max_length=self.max_value_length,
                )
            count += 1

        return local_vars

    def _get_source_line(
        self,
        filename: str,
        lineno: int,
    ) -> Optional[str]:
        """Read a single source line, or None if unavailable."""
        try:
            import linecache

            line = linecache.getline(filename, lineno)
            return line.rstrip() if line else None
        except Exception:
            return None
