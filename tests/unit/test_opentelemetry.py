"""Comprehensive unit tests for the MohFlow OpenTelemetry integration.

Covers:
  - __init__.py public exports
  - exporters.py (console, Jaeger, OTLP, multi, env-based)
  - propagators.py (setup, extract, inject, middleware, helpers)
  - trace_integration.py (TraceContext, enricher, filter, helpers)
"""

import logging
import os
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import (
    MagicMock,
    patch,
    PropertyMock,
    call,
)

import pytest

# ------------------------------------------------------------------ #
#  __init__.py – public surface                                       #
# ------------------------------------------------------------------ #


class TestModuleExports:
    """Ensure __init__.py re-exports everything listed in __all__."""

    def test_all_trace_integration_symbols(self):
        from mohflow.opentelemetry import (
            TraceContext,
            OpenTelemetryEnricher,
            setup_otel_logging,
            get_current_trace_context,
            trace_correlation_middleware,
        )

        assert TraceContext is not None
        assert OpenTelemetryEnricher is not None
        assert callable(setup_otel_logging)
        assert callable(get_current_trace_context)

    def test_all_exporter_symbols(self):
        from mohflow.opentelemetry import (
            setup_jaeger_exporter,
            setup_otlp_exporter,
            setup_console_exporter,
        )

        assert callable(setup_jaeger_exporter)
        assert callable(setup_otlp_exporter)
        assert callable(setup_console_exporter)

    def test_all_propagator_symbols(self):
        from mohflow.opentelemetry import (
            setup_trace_propagation,
            extract_trace_context,
            inject_trace_context,
        )

        assert callable(setup_trace_propagation)
        assert callable(extract_trace_context)
        assert callable(inject_trace_context)

    def test_all_list_completeness(self):
        import mohflow.opentelemetry as mod

        expected = {
            "TraceContext",
            "OpenTelemetryEnricher",
            "setup_otel_logging",
            "get_current_trace_context",
            "trace_correlation_middleware",
            "setup_jaeger_exporter",
            "setup_otlp_exporter",
            "setup_console_exporter",
            "setup_trace_propagation",
            "extract_trace_context",
            "inject_trace_context",
        }
        assert expected == set(mod.__all__)


# ------------------------------------------------------------------ #
#  exporters.py                                                       #
# ------------------------------------------------------------------ #


class TestSetupConsoleExporter:
    """Tests for setup_console_exporter."""

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", False)
    def test_returns_false_when_otel_missing(self):
        from mohflow.opentelemetry.exporters import (
            setup_console_exporter,
        )

        assert setup_console_exporter("svc") is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_success(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_console_exporter,
            )

            result = setup_console_exporter("my-svc", "2.0.0", {"env": "test"})
            assert result is True
            mock_resource.create.assert_called_once()
            attrs = mock_resource.create.call_args[0][0]
            assert attrs["sn"] == "my-svc"
            assert attrs["sv"] == "2.0.0"
            assert attrs["env"] == "test"
            mock_trace.set_tracer_provider.assert_called_once()

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    def test_import_error_returns_false(self):
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": None,
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_console_exporter,
            )

            # The inner import will raise ImportError when module is
            # None in sys.modules.
            assert setup_console_exporter("svc") is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.Resource")
    def test_generic_exception_returns_false(self, mock_resource):
        mock_resource.create.side_effect = RuntimeError("boom")
        from mohflow.opentelemetry.exporters import (
            setup_console_exporter,
        )

        assert setup_console_exporter("svc") is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_no_extra_resource_attributes(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_console_exporter,
            )

            result = setup_console_exporter("my-svc")
            assert result is True
            attrs = mock_resource.create.call_args[0][0]
            assert "env" not in attrs


class TestSetupJaegerExporter:
    """Tests for setup_jaeger_exporter."""

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", False)
    def test_returns_false_when_otel_missing(self):
        from mohflow.opentelemetry.exporters import (
            setup_jaeger_exporter,
        )

        assert setup_jaeger_exporter("svc") is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_collector_endpoint(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_jaeger_exporter,
            )

            result = setup_jaeger_exporter(
                "svc",
                collector_endpoint="http://jaeger:14268",
            )
            assert result is True
            mock_jaeger_cls.assert_called_once_with(
                collector_endpoint="http://jaeger:14268",
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_jaeger_endpoint_fallback(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_jaeger_exporter,
            )

            result = setup_jaeger_exporter(
                "svc",
                jaeger_endpoint="http://jaeger:14268",
            )
            assert result is True
            mock_jaeger_cls.assert_called_once_with(
                collector_endpoint="http://jaeger:14268",
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_udp_agent(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_jaeger_exporter,
            )

            result = setup_jaeger_exporter(
                "svc",
                agent_host="jaeger-host",
                agent_port=9999,
            )
            assert result is True
            mock_jaeger_cls.assert_called_once_with(
                agent_host_name="jaeger-host",
                agent_port=9999,
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_resource_attributes_merged(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_jaeger_exporter,
            )

            setup_jaeger_exporter(
                "svc",
                resource_attributes={"deployment": "prod"},
            )
            attrs = mock_resource.create.call_args[0][0]
            assert attrs["deployment"] == "prod"

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    def test_import_error_returns_false(self):
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": None,
                "opentelemetry.exporter.jaeger": None,
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_jaeger_exporter,
            )

            assert setup_jaeger_exporter("svc") is False


class TestSetupOtlpExporter:
    """Tests for setup_otlp_exporter."""

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", False)
    def test_returns_false_when_otel_missing(self):
        from mohflow.opentelemetry.exporters import (
            setup_otlp_exporter,
        )

        assert setup_otlp_exporter("svc") is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_explicit_endpoint(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_otlp_cls = MagicMock()
        grpc_mod = MagicMock()
        grpc_mod.OTLPSpanExporter = mock_otlp_cls
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc"
                ".trace_exporter": grpc_mod,
                "opentelemetry.exporter.otlp.proto.grpc": MagicMock(),
                "opentelemetry.exporter.otlp.proto": MagicMock(),
                "opentelemetry.exporter.otlp": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_otlp_exporter,
            )

            result = setup_otlp_exporter(
                "svc",
                otlp_endpoint="http://collector:4317",
                headers={"auth": "token"},
                insecure=True,
            )
            assert result is True
            mock_otlp_cls.assert_called_once_with(
                endpoint="http://collector:4317",
                headers={"auth": "token"},
                insecure=True,
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_endpoint_from_env(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_otlp_cls = MagicMock()
        grpc_mod = MagicMock()
        grpc_mod.OTLPSpanExporter = mock_otlp_cls
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc"
                ".trace_exporter": grpc_mod,
                "opentelemetry.exporter.otlp.proto.grpc": MagicMock(),
                "opentelemetry.exporter.otlp.proto": MagicMock(),
                "opentelemetry.exporter.otlp": MagicMock(),
            },
        ):
            with patch.dict(
                os.environ,
                {
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": (
                        "http://from-env:4317"
                    )
                },
            ):
                from mohflow.opentelemetry.exporters import (
                    setup_otlp_exporter,
                )

                setup_otlp_exporter("svc")
                used_endpoint = mock_otlp_cls.call_args[1]["endpoint"]
                assert used_endpoint == "http://from-env:4317"

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_default_endpoint_when_nothing_set(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_otlp_cls = MagicMock()
        grpc_mod = MagicMock()
        grpc_mod.OTLPSpanExporter = mock_otlp_cls
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc"
                ".trace_exporter": grpc_mod,
                "opentelemetry.exporter.otlp.proto.grpc": MagicMock(),
                "opentelemetry.exporter.otlp.proto": MagicMock(),
                "opentelemetry.exporter.otlp": MagicMock(),
            },
        ):
            env = os.environ.copy()
            env.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
            with patch.dict(os.environ, env, clear=True):
                from mohflow.opentelemetry.exporters import (
                    setup_otlp_exporter,
                )

                setup_otlp_exporter("svc")
                used_endpoint = mock_otlp_cls.call_args[1]["endpoint"]
                assert used_endpoint == "http://localhost:4317"

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    def test_import_error_returns_false(self):
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc"
                ".trace_exporter": None,
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_otlp_exporter,
            )

            assert setup_otlp_exporter("svc") is False


class TestSetupMultiExporter:
    """Tests for setup_multi_exporter."""

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", False)
    def test_returns_false_when_otel_missing(self):
        from mohflow.opentelemetry.exporters import (
            setup_multi_exporter,
        )

        assert setup_multi_exporter("svc", exporters=[]) is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    def test_returns_false_when_no_exporters(self):
        from mohflow.opentelemetry.exporters import (
            setup_multi_exporter,
        )

        assert setup_multi_exporter("svc", exporters=None) is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_console_exporter_in_multi(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            result = setup_multi_exporter(
                "svc", exporters=[{"type": "console"}]
            )
            assert result is True

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_jaeger_collector_in_multi(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            result = setup_multi_exporter(
                "svc",
                exporters=[
                    {
                        "type": "jaeger",
                        "collector_endpoint": "http://j:14268",
                    }
                ],
            )
            assert result is True
            mock_jaeger_cls.assert_called_once_with(
                collector_endpoint="http://j:14268"
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_jaeger_udp_in_multi(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            result = setup_multi_exporter(
                "svc",
                exporters=[
                    {
                        "type": "jaeger",
                        "agent_host": "jhost",
                        "agent_port": 7777,
                    }
                ],
            )
            assert result is True
            mock_jaeger_cls.assert_called_once_with(
                agent_host_name="jhost",
                agent_port=7777,
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_otlp_in_multi(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_otlp_cls = MagicMock()
        grpc_mod = MagicMock()
        grpc_mod.OTLPSpanExporter = mock_otlp_cls
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc": MagicMock(
                    trace_exporter=grpc_mod
                ),
                "opentelemetry.exporter.otlp.proto": MagicMock(),
                "opentelemetry.exporter.otlp": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            result = setup_multi_exporter(
                "svc",
                exporters=[
                    {
                        "type": "otlp",
                        "endpoint": "http://c:4317",
                        "headers": {"x": "y"},
                        "insecure": True,
                    }
                ],
            )
            assert result is True
            mock_otlp_cls.assert_called_once_with(
                endpoint="http://c:4317",
                headers={"x": "y"},
                insecure=True,
            )

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_unknown_exporter_skipped(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        from mohflow.opentelemetry.exporters import (
            setup_multi_exporter,
        )

        result = setup_multi_exporter("svc", exporters=[{"type": "unknown"}])
        assert result is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_import_error_in_one_exporter_continues(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        """If one exporter fails to import, the rest still work."""
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                ),
                "opentelemetry.exporter.jaeger.thrift": None,
                "opentelemetry.exporter.jaeger": None,
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            result = setup_multi_exporter(
                "svc",
                exporters=[
                    {"type": "jaeger"},
                    {"type": "console"},
                ],
            )
            assert result is True

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.Resource")
    def test_top_level_exception_returns_false(self, mock_resource):
        mock_resource.create.side_effect = RuntimeError("boom")
        from mohflow.opentelemetry.exporters import (
            setup_multi_exporter,
        )

        result = setup_multi_exporter("svc", exporters=[{"type": "console"}])
        assert result is False

    @patch("mohflow.opentelemetry.exporters.HAS_OPENTELEMETRY", True)
    @patch("mohflow.opentelemetry.exporters.trace")
    @patch("mohflow.opentelemetry.exporters.TracerProvider")
    @patch("mohflow.opentelemetry.exporters.BatchSpanProcessor")
    @patch("mohflow.opentelemetry.exporters.Resource")
    @patch("mohflow.opentelemetry.exporters.SERVICE_NAME", "sn")
    @patch("mohflow.opentelemetry.exporters.SERVICE_VERSION", "sv")
    def test_resource_attributes_merged_in_multi(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.exporters import (
                setup_multi_exporter,
            )

            setup_multi_exporter(
                "svc",
                exporters=[{"type": "console"}],
                resource_attributes={"region": "us-east-1"},
            )
            attrs = mock_resource.create.call_args[0][0]
            assert attrs["region"] == "us-east-1"


class TestSetupExporterFromEnv:
    """Tests for setup_exporter_from_env."""

    @patch("mohflow.opentelemetry.exporters.setup_console_exporter")
    def test_defaults_to_console(self, mock_console):
        mock_console.return_value = True
        env = os.environ.copy()
        env.pop("OTEL_TRACES_EXPORTER", None)
        with patch.dict(os.environ, env, clear=True):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            result = setup_exporter_from_env("svc")
            assert result is True
            mock_console.assert_called_once()

    @patch("mohflow.opentelemetry.exporters.setup_console_exporter")
    def test_explicit_console(self, mock_console):
        mock_console.return_value = True
        with patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "console"}):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            result = setup_exporter_from_env("svc")
            assert result is True

    @patch("mohflow.opentelemetry.exporters.setup_jaeger_exporter")
    def test_jaeger_from_env(self, mock_jaeger):
        mock_jaeger.return_value = True
        env_vars = {
            "OTEL_TRACES_EXPORTER": "jaeger",
            "OTEL_EXPORTER_JAEGER_ENDPOINT": "http://j:14268",
            "OTEL_EXPORTER_JAEGER_AGENT_HOST": "jhost",
            "OTEL_EXPORTER_JAEGER_AGENT_PORT": "7777",
        }
        with patch.dict(os.environ, env_vars):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            result = setup_exporter_from_env("svc", "2.0")
            assert result is True
            mock_jaeger.assert_called_once_with(
                service_name="svc",
                service_version="2.0",
                jaeger_endpoint="http://j:14268",
                agent_host="jhost",
                agent_port=7777,
                resource_attributes=None,
            )

    @patch("mohflow.opentelemetry.exporters.setup_otlp_exporter")
    def test_otlp_from_env(self, mock_otlp):
        mock_otlp.return_value = True
        env_vars = {
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": ("http://c:4317"),
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": ("key1=val1,key2=val2"),
        }
        with patch.dict(os.environ, env_vars):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            result = setup_exporter_from_env("svc")
            assert result is True
            _, kwargs = mock_otlp.call_args
            assert kwargs["headers"] == {
                "key1": "val1",
                "key2": "val2",
            }

    @patch("mohflow.opentelemetry.exporters.setup_otlp_exporter")
    def test_otlp_bad_headers_parsed_as_none(self, mock_otlp):
        mock_otlp.return_value = True
        env_vars = {
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "bad-format",
        }
        with patch.dict(os.environ, env_vars):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            setup_exporter_from_env("svc")
            _, kwargs = mock_otlp.call_args
            assert kwargs["headers"] is None

    @patch("mohflow.opentelemetry.exporters.setup_console_exporter")
    def test_unknown_exporter_falls_back_to_console(self, mock_console):
        mock_console.return_value = True
        with patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "zipkin"}):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            result = setup_exporter_from_env("svc")
            assert result is True
            mock_console.assert_called_once()

    @patch("mohflow.opentelemetry.exporters.setup_otlp_exporter")
    def test_otlp_no_headers_env(self, mock_otlp):
        mock_otlp.return_value = True
        env = os.environ.copy()
        env["OTEL_TRACES_EXPORTER"] = "otlp"
        env.pop("OTEL_EXPORTER_OTLP_TRACES_HEADERS", None)
        env.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
        with patch.dict(os.environ, env, clear=True):
            from mohflow.opentelemetry.exporters import (
                setup_exporter_from_env,
            )

            setup_exporter_from_env("svc")
            _, kwargs = mock_otlp.call_args
            assert kwargs["headers"] is None


# ------------------------------------------------------------------ #
#  propagators.py                                                     #
# ------------------------------------------------------------------ #


class TestSetupTracePropagation:
    """Tests for setup_trace_propagation."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_false_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        assert setup_trace_propagation() is False

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.propagate")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    @patch("mohflow.opentelemetry.propagators.W3CBaggagePropagator")
    @patch("mohflow.opentelemetry.propagators.CompositePropagator")
    def test_default_propagators(
        self,
        mock_composite,
        mock_baggage,
        mock_tc,
        mock_propagate,
    ):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation()
        assert result is True
        mock_composite.assert_called_once()
        mock_propagate.set_global_textmap.assert_called_once()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.propagate")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_single_propagator_no_composite(self, mock_tc, mock_propagate):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation(["tracecontext"])
        assert result is True
        mock_propagate.set_global_textmap.assert_called_once_with(
            mock_tc.return_value
        )

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.propagate")
    @patch("mohflow.opentelemetry.propagators.B3MultiFormat")
    def test_b3_propagator(self, mock_b3, mock_propagate):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation(["b3"])
        assert result is True

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.propagate")
    @patch("mohflow.opentelemetry.propagators.B3SingleFormat")
    def test_b3single_propagator(self, mock_b3single, mock_propagate):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation(["b3single"])
        assert result is True

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.propagate")
    @patch("mohflow.opentelemetry.propagators.JaegerPropagator")
    def test_jaeger_propagator(self, mock_jaeger, mock_propagate):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation(["jaeger"])
        assert result is True

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    def test_empty_list_returns_false(self):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        result = setup_trace_propagation([])
        assert result is False

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator",
        side_effect=RuntimeError("boom"),
    )
    def test_exception_returns_false(self, mock_tc):
        from mohflow.opentelemetry.propagators import (
            setup_trace_propagation,
        )

        assert setup_trace_propagation(["tracecontext"]) is False


class TestExtractTraceContext:
    """Tests for extract_trace_context."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_none_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        assert extract_trace_context({}) is None

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_extracts_valid_context(self, mock_tc_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_tc_cls.return_value = mock_propagator
        extracted = MagicMock()
        mock_propagator.extract.return_value = extracted
        # Ensure it is different from current context
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context(
            {"traceparent": "00-abc-def-01"},
            ["tracecontext"],
        )
        assert result is extracted

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_returns_none_when_context_same_as_current(
        self, mock_tc_cls, mock_ctx
    ):
        current = MagicMock()
        mock_ctx.get_current.return_value = current
        mock_propagator = MagicMock()
        mock_tc_cls.return_value = mock_propagator
        mock_propagator.extract.return_value = current

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["tracecontext"])
        assert result is None

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.B3MultiFormat")
    def test_b3_extraction(self, mock_b3_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_b3_cls.return_value = mock_propagator
        extracted = MagicMock()
        mock_propagator.extract.return_value = extracted
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["b3"])
        assert result is extracted

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.B3SingleFormat")
    def test_b3single_extraction(self, mock_b3single_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_b3single_cls.return_value = mock_propagator
        extracted = MagicMock()
        mock_propagator.extract.return_value = extracted
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["b3single"])
        assert result is extracted

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.JaegerPropagator")
    def test_jaeger_extraction(self, mock_jaeger_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_jaeger_cls.return_value = mock_propagator
        extracted = MagicMock()
        mock_propagator.extract.return_value = extracted
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["jaeger"])
        assert result is extracted

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators" ".W3CBaggagePropagator")
    def test_baggage_extraction(self, mock_baggage_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_baggage_cls.return_value = mock_propagator
        extracted = MagicMock()
        mock_propagator.extract.return_value = extracted
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["baggage"])
        assert result is extracted

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    def test_unknown_propagator_skipped(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["unknown"])
        assert result is None

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_exception_in_propagator_continues(self, mock_tc_cls, mock_ctx):
        mock_tc_cls.return_value.extract.side_effect = RuntimeError("bad")

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["tracecontext"])
        assert result is None

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_extract_returns_none_on_falsy_ctx(self, mock_tc_cls, mock_ctx):
        mock_tc_cls.return_value.extract.return_value = None

        from mohflow.opentelemetry.propagators import (
            extract_trace_context,
        )

        result = extract_trace_context({}, ["tracecontext"])
        assert result is None


class TestInjectTraceContext:
    """Tests for inject_trace_context."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_headers_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        h = {"existing": "header"}
        result = inject_trace_context(h)
        assert result == {"existing": "header"}

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_injects_with_current_context(self, mock_tc_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_tc_cls.return_value = mock_propagator
        current = MagicMock()
        mock_ctx.get_current.return_value = current

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        result = inject_trace_context({}, propagator_types=["tracecontext"])
        mock_propagator.inject.assert_called_once()
        assert isinstance(result, dict)

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_injects_with_explicit_context(self, mock_tc_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_tc_cls.return_value = mock_propagator
        explicit_ctx = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        inject_trace_context(
            {}, ctx=explicit_ctx, propagator_types=["tracecontext"]
        )
        mock_propagator.inject.assert_called_once_with(
            mock_propagator.inject.call_args[0][0],
            context=explicit_ctx,
        )

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.B3MultiFormat")
    def test_b3_injection(self, mock_b3_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_b3_cls.return_value = mock_propagator
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        inject_trace_context({}, propagator_types=["b3"])
        mock_propagator.inject.assert_called_once()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.B3SingleFormat")
    def test_b3single_injection(self, mock_b3single_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_b3single_cls.return_value = mock_propagator
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        inject_trace_context({}, propagator_types=["b3single"])
        mock_propagator.inject.assert_called_once()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.JaegerPropagator")
    def test_jaeger_injection(self, mock_jaeger_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_jaeger_cls.return_value = mock_propagator
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        inject_trace_context({}, propagator_types=["jaeger"])
        mock_propagator.inject.assert_called_once()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators" ".W3CBaggagePropagator")
    def test_baggage_injection(self, mock_baggage_cls, mock_ctx):
        mock_propagator = MagicMock()
        mock_baggage_cls.return_value = mock_propagator
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        inject_trace_context({}, propagator_types=["baggage"])
        mock_propagator.inject.assert_called_once()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    def test_unknown_propagator_skipped_in_inject(self, mock_ctx):
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        result = inject_trace_context({"x": "y"}, propagator_types=["unknown"])
        assert result == {"x": "y"}

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch(
        "mohflow.opentelemetry.propagators" ".TraceContextTextMapPropagator"
    )
    def test_exception_in_inject_continues(self, mock_tc_cls, mock_ctx):
        mock_tc_cls.return_value.inject.side_effect = RuntimeError("bad")
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        result = inject_trace_context(
            {"x": "y"}, propagator_types=["tracecontext"]
        )
        assert result == {"x": "y"}

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    def test_does_not_mutate_original_headers(self, mock_ctx):
        mock_ctx.get_current.return_value = MagicMock()

        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        original = {"a": "1"}
        result = inject_trace_context(original, propagator_types=[])
        assert result is not original
        assert result == {"a": "1"}

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch(
        "mohflow.opentelemetry.propagators.context",
        side_effect=RuntimeError("outer"),
    )
    def test_outer_exception_returns_original(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            inject_trace_context,
        )

        h = {"k": "v"}
        result = inject_trace_context(h)
        assert result == h


class TestTracePropagationMiddleware:
    """Tests for TracePropagationMiddleware."""

    def test_init_defaults(self):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        assert mw.propagator_types == ["tracecontext", "baggage"]
        assert mw.logger is None

    def test_init_custom(self):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        logger = logging.getLogger("test")
        mw = TracePropagationMiddleware(propagator_types=["b3"], logger=logger)
        assert mw.propagator_types == ["b3"]
        assert mw.logger is logger

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_extract_returns_none_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = False
        assert mw.extract_from_headers({}) is None

    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_extract_logs_on_success(self, mock_extract):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        logger = MagicMock()
        mw = TracePropagationMiddleware(logger=logger)
        mw._otel_available = True
        mock_extract.return_value = MagicMock()

        mw.extract_from_headers({"traceparent": "x"})
        logger.debug.assert_called_once()

    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_extract_no_log_when_ctx_is_none(self, mock_extract):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        logger = MagicMock()
        mw = TracePropagationMiddleware(logger=logger)
        mw._otel_available = True
        mock_extract.return_value = None

        result = mw.extract_from_headers({})
        assert result is None
        logger.debug.assert_not_called()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_inject_returns_headers_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = False
        h = {"x": "y"}
        assert mw.inject_to_headers(h) == h

    @patch("mohflow.opentelemetry.propagators.inject_trace_context")
    def test_inject_logs_debug(self, mock_inject):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        logger = MagicMock()
        mw = TracePropagationMiddleware(logger=logger)
        mw._otel_available = True
        mock_inject.return_value = {"x": "y"}

        mw.inject_to_headers({})
        logger.debug.assert_called_once()

    @patch("mohflow.opentelemetry.propagators.inject_trace_context")
    def test_inject_no_logger(self, mock_inject):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = True
        mock_inject.return_value = {"x": "y"}

        result = mw.inject_to_headers({})
        assert result == {"x": "y"}

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_create_child_returns_none_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = False
        assert mw.create_child_context() is None

    @patch("mohflow.opentelemetry.propagators.context")
    def test_create_child_context_attaches_parent(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = True
        parent = MagicMock()
        mock_ctx.attach.return_value = "token123"

        token = mw.create_child_context(parent)
        assert token == "token123"
        mock_ctx.attach.assert_called_once_with(parent)

    @patch("mohflow.opentelemetry.propagators.context")
    def test_create_child_context_no_parent(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = True

        assert mw.create_child_context(None) is None

    @patch("mohflow.opentelemetry.propagators.context")
    def test_create_child_exception_returns_none(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            TracePropagationMiddleware,
        )

        mw = TracePropagationMiddleware()
        mw._otel_available = True
        mock_ctx.attach.side_effect = RuntimeError("boom")

        assert mw.create_child_context(MagicMock()) is None


class TestGetTraceHeaders:
    """Tests for get_trace_headers."""

    @patch("mohflow.opentelemetry.propagators.inject_trace_context")
    def test_delegates_to_inject(self, mock_inject):
        mock_inject.return_value = {"traceparent": "x"}

        from mohflow.opentelemetry.propagators import (
            get_trace_headers,
        )

        result = get_trace_headers(ctx=MagicMock(), propagator_types=["b3"])
        assert result == {"traceparent": "x"}

    @patch("mohflow.opentelemetry.propagators.inject_trace_context")
    def test_passes_empty_dict(self, mock_inject):
        mock_inject.return_value = {}

        from mohflow.opentelemetry.propagators import (
            get_trace_headers,
        )

        get_trace_headers()
        mock_inject.assert_called_once_with({}, None, None)


class TestCreateTraceLogger:
    """Tests for create_trace_logger."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_logger_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger("test")
        assert isinstance(logger, logging.Logger)

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    def test_returns_logger_when_no_headers(self):
        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger("test")
        assert isinstance(logger, logging.Logger)

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    @patch("mohflow.opentelemetry.propagators.context")
    def test_attaches_context_when_extracted(self, mock_ctx, mock_extract):
        extracted = MagicMock()
        mock_extract.return_value = extracted
        mock_ctx.attach.return_value = "token"

        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger("test", headers={"traceparent": "x"})
        mock_ctx.attach.assert_called_once_with(extracted)
        assert hasattr(logger, "_otel_cleanup")
        # Exercise the cleanup
        logger._otel_cleanup()
        mock_ctx.detach.assert_called_once_with("token")

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_no_cleanup_when_extract_fails(self, mock_extract):
        mock_extract.return_value = None

        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger(
            "test_no_cleanup", headers={"traceparent": "x"}
        )
        assert not hasattr(logger, "_otel_cleanup")

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    @patch("mohflow.opentelemetry.propagators.context")
    def test_cleanup_swallows_detach_errors(self, mock_ctx, mock_extract):
        extracted = MagicMock()
        mock_extract.return_value = extracted
        mock_ctx.attach.return_value = "token"
        mock_ctx.detach.side_effect = RuntimeError("detach fail")

        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger("test", headers={"traceparent": "x"})
        # Should not raise
        logger._otel_cleanup()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch(
        "mohflow.opentelemetry.propagators.extract_trace_context",
        side_effect=RuntimeError("bad"),
    )
    def test_exception_during_setup_swallowed(self, mock_extract):
        from mohflow.opentelemetry.propagators import (
            create_trace_logger,
        )

        logger = create_trace_logger("test", headers={"traceparent": "x"})
        assert isinstance(logger, logging.Logger)


class TestFlaskTraceMiddleware:
    """Tests for flask_trace_middleware."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_app_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            flask_trace_middleware,
        )

        app = MagicMock()
        result = flask_trace_middleware(app)
        assert result is app

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    def test_returns_app_when_flask_missing(self):
        with patch.dict("sys.modules", {"flask": None}):
            from mohflow.opentelemetry.propagators import (
                flask_trace_middleware,
            )

            app = MagicMock()
            result = flask_trace_middleware(app)
            assert result is app


class TestDjangoTraceMiddleware:
    """Tests for django_trace_middleware."""

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_none_when_otel_missing(self):
        from mohflow.opentelemetry.propagators import (
            django_trace_middleware,
        )

        assert django_trace_middleware() is None

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    def test_returns_middleware_class(self, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            django_trace_middleware,
        )

        cls = django_trace_middleware()
        assert cls is not None
        assert cls.__name__ == "OpenTelemetryMiddleware"

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_django_middleware_call(self, mock_extract, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            django_trace_middleware,
        )

        cls = django_trace_middleware()
        get_response = MagicMock()
        get_response.return_value = MagicMock()

        mw = cls(get_response)

        request = MagicMock()
        request.META = {
            "HTTP_TRACEPARENT": "00-abc-def-01",
            "HTTP_TRACESTATE": "vendor=opaque",
            "SERVER_NAME": "localhost",
        }

        # ctx is found
        extracted_ctx = MagicMock()
        mock_extract.return_value = extracted_ctx
        mock_ctx.attach.return_value = "token"

        response = mw(request)
        get_response.assert_called_once_with(request)
        mock_ctx.attach.assert_called_once_with(extracted_ctx)
        mock_ctx.detach.assert_called_once_with("token")

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_django_middleware_no_ctx(self, mock_extract, mock_ctx):
        from mohflow.opentelemetry.propagators import (
            django_trace_middleware,
        )

        cls = django_trace_middleware()
        get_response = MagicMock()
        mw = cls(get_response)

        request = MagicMock()
        request.META = {}
        mock_extract.return_value = None

        mw(request)
        mock_ctx.attach.assert_not_called()
        mock_ctx.detach.assert_not_called()

    @patch(
        "mohflow.opentelemetry.propagators.HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.propagators.context")
    @patch("mohflow.opentelemetry.propagators.extract_trace_context")
    def test_django_middleware_detach_swallows_errors(
        self, mock_extract, mock_ctx
    ):
        from mohflow.opentelemetry.propagators import (
            django_trace_middleware,
        )

        cls = django_trace_middleware()
        get_response = MagicMock()
        mw = cls(get_response)

        request = MagicMock()
        request.META = {"HTTP_TRACEPARENT": "x"}
        mock_extract.return_value = MagicMock()
        mock_ctx.attach.return_value = "tok"
        mock_ctx.detach.side_effect = RuntimeError("detach fail")

        # Should not raise even though detach fails
        mw(request)


# ------------------------------------------------------------------ #
#  trace_integration.py                                               #
# ------------------------------------------------------------------ #


class TestTraceContext:
    """Tests for TraceContext dataclass."""

    def test_defaults(self):
        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext()
        assert tc.trace_id is None
        assert tc.span_id is None
        assert tc.trace_flags is None
        assert tc.trace_state is None
        assert tc.baggage is None
        assert tc.service_name is None
        assert tc.service_version is None

    def test_to_dict_all_fields(self):
        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext(
            trace_id="abc",
            span_id="def",
            trace_flags="01",
            trace_state="vendor=val",
            baggage={"user_id": "42"},
            service_name="my-svc",
            service_version="1.2.3",
        )
        d = tc.to_dict()
        assert d["trace_id"] == "abc"
        assert d["span_id"] == "def"
        assert d["trace_flags"] == "01"
        assert d["trace_state"] == "vendor=val"
        assert d["service_name"] == "my-svc"
        assert d["service_version"] == "1.2.3"
        assert d["user_id"] == "42"

    def test_to_dict_empty(self):
        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext()
        assert tc.to_dict() == {}

    def test_to_dict_partial(self):
        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext(trace_id="abc", span_id="def")
        d = tc.to_dict()
        assert d == {"trace_id": "abc", "span_id": "def"}
        assert "trace_flags" not in d

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        False,
    )
    def test_from_current_span_without_otel(self):
        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.trace_id is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_no_recording(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False
        mock_trace.get_current_span.return_value = mock_span

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.trace_id is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_none_span(self, mock_trace):
        mock_trace.get_current_span.return_value = None

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.trace_id is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.get_all_baggage")
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_valid(self, mock_trace, mock_baggage):
        span_ctx = MagicMock()
        span_ctx.is_valid = True
        span_ctx.trace_id = 0xABCDEF1234567890ABCDEF1234567890
        span_ctx.span_id = 0x1234567890ABCDEF
        span_ctx.trace_flags = 1
        span_ctx.trace_state = MagicMock()
        span_ctx.trace_state.to_header.return_value = "vendor=opaque"

        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = span_ctx
        mock_trace.get_current_span.return_value = mock_span

        # Resource with service info
        mock_resource = MagicMock()
        mock_resource.attributes = {
            "service.name": "my-svc",
            "service.version": "1.0.0",
        }
        mock_provider = MagicMock()
        mock_provider._resource = mock_resource
        mock_trace.get_tracer_provider.return_value = mock_provider

        mock_baggage.return_value = {"user_id": "42"}

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
            SERVICE_NAME,
            SERVICE_VERSION,
        )

        # Patch the constants to match mock resource attributes
        with patch(
            "mohflow.opentelemetry.trace_integration" ".SERVICE_NAME",
            "service.name",
        ), patch(
            "mohflow.opentelemetry.trace_integration" ".SERVICE_VERSION",
            "service.version",
        ):
            tc = TraceContext.from_current_span()

        assert tc.trace_id == "abcdef1234567890abcdef1234567890"
        assert tc.span_id == "1234567890abcdef"
        assert tc.trace_flags == "01"
        assert tc.trace_state == "vendor=opaque"
        assert tc.baggage == {"user_id": "42"}
        assert tc.service_name == "my-svc"
        assert tc.service_version == "1.0.0"

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.get_all_baggage")
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_invalid_span_context(
        self, mock_trace, mock_baggage
    ):
        span_ctx = MagicMock()
        span_ctx.is_valid = False

        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = span_ctx
        mock_trace.get_current_span.return_value = mock_span
        mock_baggage.return_value = {}

        mock_provider = MagicMock(spec=[])
        mock_trace.get_tracer_provider.return_value = mock_provider

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.trace_id is None
        assert tc.span_id is None
        assert tc.trace_flags is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.get_all_baggage")
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_no_trace_state(self, mock_trace, mock_baggage):
        span_ctx = MagicMock()
        span_ctx.is_valid = True
        span_ctx.trace_id = 0x1
        span_ctx.span_id = 0x2
        span_ctx.trace_flags = 0
        span_ctx.trace_state = None

        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = span_ctx
        mock_trace.get_current_span.return_value = mock_span
        mock_baggage.return_value = {}

        mock_provider = MagicMock(spec=[])
        mock_trace.get_tracer_provider.return_value = mock_provider

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.trace_state is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.get_all_baggage")
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_from_current_span_resource_exception(
        self, mock_trace, mock_baggage
    ):
        span_ctx = MagicMock()
        span_ctx.is_valid = False

        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value = span_ctx
        mock_trace.get_current_span.return_value = mock_span
        mock_baggage.return_value = {}
        mock_trace.get_tracer_provider.side_effect = RuntimeError("boom")

        from mohflow.opentelemetry.trace_integration import (
            TraceContext,
        )

        tc = TraceContext.from_current_span()
        assert tc.service_name is None


class TestOpenTelemetryEnricher:
    """Tests for OpenTelemetryEnricher."""

    def test_defaults(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher()
        assert e.include_trace_id is True
        assert e.include_span_id is True
        assert e.include_trace_flags is False
        assert e.include_trace_state is False
        assert e.include_baggage is True
        assert e.include_service_info is True
        assert e.trace_id_field == "trace_id"
        assert e.span_id_field == "span_id"
        assert e.baggage_prefix == ""

    def test_custom_fields(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher(
            trace_id_field="otel.trace",
            span_id_field="otel.span",
            baggage_prefix="bg_",
        )
        assert e.trace_id_field == "otel.trace"
        assert e.span_id_field == "otel.span"
        assert e._get_baggage_field_name("key") == "bg_key"

    def test_baggage_field_name_no_prefix(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher(baggage_prefix="")
        assert e._get_baggage_field_name("user_id") == "user_id"

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        False,
    )
    def test_enrich_record_noop_without_otel(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher()
        e._otel_available = False
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        result = e.enrich_record(record)
        assert result is record
        assert not hasattr(record, "trace_id")

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_record_with_full_context(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
            span_id="def",
            trace_flags="01",
            trace_state="vendor=val",
            baggage={"user_id": "42"},
            service_name="svc",
            service_version="1.0",
        )

        e = OpenTelemetryEnricher(
            include_trace_flags=True,
            include_trace_state=True,
        )
        e._otel_available = True
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )

        result = e.enrich_record(record)
        assert result.trace_id == "abc"
        assert result.span_id == "def"
        assert result.trace_flags == "01"
        assert result.trace_state == "vendor=val"
        assert result.otel_service_name == "svc"
        assert result.otel_service_version == "1.0"
        assert result.user_id == "42"

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_record_excludes_disabled_fields(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
            span_id="def",
            trace_flags="01",
            trace_state="vendor=val",
            baggage={"user_id": "42"},
            service_name="svc",
            service_version="1.0",
        )

        e = OpenTelemetryEnricher(
            include_trace_id=False,
            include_span_id=False,
            include_trace_flags=False,
            include_trace_state=False,
            include_baggage=False,
            include_service_info=False,
        )
        e._otel_available = True
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        e.enrich_record(record)
        assert not hasattr(record, "trace_id")
        assert not hasattr(record, "span_id")
        assert not hasattr(record, "trace_flags")
        assert not hasattr(record, "trace_state")
        assert not hasattr(record, "otel_service_name")
        assert not hasattr(record, "user_id")

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_record_baggage_prefix(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            baggage={"tenant": "acme"},
        )

        e = OpenTelemetryEnricher(baggage_prefix="bg_")
        e._otel_available = True
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        e.enrich_record(record)
        assert record.bg_tenant == "acme"

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        False,
    )
    def test_enrich_dict_noop_without_otel(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher()
        e._otel_available = False
        data = {"message": "hello"}
        result = e.enrich_dict(data)
        assert result == {"message": "hello"}

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_dict_full_context(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
            span_id="def",
            trace_flags="01",
            trace_state="vendor=val",
            baggage={"user_id": "42"},
            service_name="svc",
            service_version="1.0",
        )

        e = OpenTelemetryEnricher(
            include_trace_flags=True,
            include_trace_state=True,
        )
        e._otel_available = True
        data = {"message": "hello"}
        result = e.enrich_dict(data)

        assert result["trace_id"] == "abc"
        assert result["span_id"] == "def"
        assert result["trace_flags"] == "01"
        assert result["trace_state"] == "vendor=val"
        assert result["otel_service_name"] == "svc"
        assert result["otel_service_version"] == "1.0"
        assert result["user_id"] == "42"
        assert result["message"] == "hello"

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_dict_does_not_mutate_original(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
        )

        e = OpenTelemetryEnricher()
        e._otel_available = True
        original = {"message": "hello"}
        result = e.enrich_dict(original)
        assert "trace_id" not in original
        assert result["trace_id"] == "abc"

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_dict_excludes_disabled(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
            span_id="def",
            service_name="svc",
            service_version="1.0",
            baggage={"x": "y"},
        )

        e = OpenTelemetryEnricher(
            include_trace_id=False,
            include_span_id=False,
            include_service_info=False,
            include_baggage=False,
        )
        e._otel_available = True
        result = e.enrich_dict({})
        assert "trace_id" not in result
        assert "span_id" not in result
        assert "otel_service_name" not in result
        assert "x" not in result

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_dict_baggage_prefix(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            baggage={"tenant": "acme"},
        )

        e = OpenTelemetryEnricher(baggage_prefix="bg_")
        e._otel_available = True
        result = e.enrich_dict({})
        assert result["bg_tenant"] == "acme"

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_enrich_dict_custom_field_names(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryEnricher,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc", span_id="def"
        )

        e = OpenTelemetryEnricher(
            trace_id_field="otel.trace",
            span_id_field="otel.span",
        )
        e._otel_available = True
        result = e.enrich_dict({})
        assert result["otel.trace"] == "abc"
        assert result["otel.span"] == "def"


class TestSetupOtelLogging:
    """Tests for setup_otel_logging."""

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        False,
    )
    def test_returns_false_without_otel(self):
        from mohflow.opentelemetry.trace_integration import (
            setup_otel_logging,
        )

        assert setup_otel_logging("svc") is False

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_console_exporter(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            result = setup_otel_logging("svc", exporter_type="console")
            assert result is True

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_jaeger_exporter(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_jaeger_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.jaeger.thrift": MagicMock(
                    JaegerExporter=mock_jaeger_cls
                ),
                "opentelemetry.exporter.jaeger": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            result = setup_otel_logging("svc", exporter_type="jaeger")
            assert result is True

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_otlp_exporter(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_otlp_cls = MagicMock()
        grpc_mod = MagicMock()
        grpc_mod.OTLPSpanExporter = mock_otlp_cls
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.otlp.proto.grpc"
                ".trace_exporter": grpc_mod,
                "opentelemetry.exporter.otlp.proto.grpc": (MagicMock()),
                "opentelemetry.exporter.otlp.proto": MagicMock(),
                "opentelemetry.exporter.otlp": MagicMock(),
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            result = setup_otel_logging(
                "svc",
                exporter_type="otlp",
                endpoint="http://c:4317",
            )
            assert result is True
            mock_otlp_cls.assert_called_once_with(endpoint="http://c:4317")

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_unknown_exporter_defaults_to_console(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            result = setup_otel_logging("svc", exporter_type="zipkin")
            assert result is True

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_resource_attributes_merged(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            setup_otel_logging(
                "svc",
                resource_attributes={"env": "staging"},
            )
            attrs = mock_resource.create.call_args[0][0]
            assert attrs["env"] == "staging"

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    def test_exception_returns_false(self, mock_resource):
        mock_resource.create.side_effect = RuntimeError("boom")
        from mohflow.opentelemetry.trace_integration import (
            setup_otel_logging,
        )

        assert setup_otel_logging("svc") is False

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    @patch("mohflow.opentelemetry.trace_integration.TracerProvider")
    @patch("mohflow.opentelemetry.trace_integration" ".BatchSpanProcessor")
    @patch("mohflow.opentelemetry.trace_integration.Resource")
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_NAME",
        "sn",
    )
    @patch(
        "mohflow.opentelemetry.trace_integration.SERVICE_VERSION",
        "sv",
    )
    def test_otlp_without_endpoint_falls_back_to_console(
        self,
        mock_resource,
        mock_bsp,
        mock_tp,
        mock_trace,
    ):
        """When exporter_type='otlp' but endpoint is None, falls
        back to console."""
        mock_console_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.exporter.console": MagicMock(
                    ConsoleSpanExporter=mock_console_cls
                )
            },
        ):
            from mohflow.opentelemetry.trace_integration import (
                setup_otel_logging,
            )

            result = setup_otel_logging("svc", exporter_type="otlp")
            assert result is True


class TestGetCurrentTraceContext:
    """Tests for get_current_trace_context."""

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_delegates_to_from_current_span(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            get_current_trace_context,
            TraceContext,
        )

        expected = TraceContext(trace_id="abc")
        mock_from_span.return_value = expected

        result = get_current_trace_context()
        assert result is expected


class TestTraceCorrelationMiddleware:
    """Tests for trace_correlation_middleware context manager."""

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        False,
    )
    def test_noop_without_otel(self):
        from mohflow.opentelemetry.trace_integration import (
            trace_correlation_middleware,
        )

        with trace_correlation_middleware("op") as span:
            assert span is None

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_yields_span(self, mock_trace):
        from mohflow.opentelemetry.trace_integration import (
            trace_correlation_middleware,
        )

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with trace_correlation_middleware("my_op") as span:
            assert span is mock_span

        mock_trace.get_tracer.assert_called_once()

    @patch(
        "mohflow.opentelemetry.trace_integration" ".HAS_OPENTELEMETRY",
        True,
    )
    @patch("mohflow.opentelemetry.trace_integration.trace")
    def test_records_exception(self, mock_trace):
        from mohflow.opentelemetry.trace_integration import (
            trace_correlation_middleware,
        )

        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(
            return_value=False
        )

        with pytest.raises(ValueError, match="test error"):
            with trace_correlation_middleware("op") as span:
                raise ValueError("test error")

        mock_span.record_exception.assert_called_once()
        mock_span.set_status.assert_called_once()


class TestOpenTelemetryFilter:
    """Tests for OpenTelemetryFilter."""

    def test_default_enricher(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryFilter,
            OpenTelemetryEnricher,
        )

        f = OpenTelemetryFilter()
        assert isinstance(f.enricher, OpenTelemetryEnricher)

    def test_custom_enricher(self):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryFilter,
            OpenTelemetryEnricher,
        )

        e = OpenTelemetryEnricher(
            include_trace_id=False,
        )
        f = OpenTelemetryFilter(enricher=e)
        assert f.enricher is e

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_filter_always_returns_true(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryFilter,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext()
        f = OpenTelemetryFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        assert f.filter(record) is True

    @patch(
        "mohflow.opentelemetry.trace_integration"
        ".TraceContext.from_current_span"
    )
    def test_filter_enriches_record(self, mock_from_span):
        from mohflow.opentelemetry.trace_integration import (
            OpenTelemetryFilter,
            TraceContext,
        )

        mock_from_span.return_value = TraceContext(
            trace_id="abc",
        )
        f = OpenTelemetryFilter()
        f.enricher._otel_available = True
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        f.filter(record)
        assert record.trace_id == "abc"


class TestAddOtelContextToLogger:
    """Tests for add_otel_context_to_logger."""

    def test_adds_filter_to_logger(self):
        from mohflow.opentelemetry.trace_integration import (
            add_otel_context_to_logger,
            OpenTelemetryFilter,
        )

        logger = logging.getLogger("test_add_otel")
        initial_count = len(logger.filters)
        add_otel_context_to_logger(logger)
        assert len(logger.filters) == initial_count + 1
        assert isinstance(logger.filters[-1], OpenTelemetryFilter)
        # Cleanup
        logger.removeFilter(logger.filters[-1])

    def test_adds_custom_enricher_filter(self):
        from mohflow.opentelemetry.trace_integration import (
            add_otel_context_to_logger,
            OpenTelemetryEnricher,
            OpenTelemetryFilter,
        )

        logger = logging.getLogger("test_add_otel_custom")
        enricher = OpenTelemetryEnricher(
            include_trace_id=False,
        )
        add_otel_context_to_logger(logger, enricher)
        f = logger.filters[-1]
        assert isinstance(f, OpenTelemetryFilter)
        assert f.enricher is enricher
        # Cleanup
        logger.removeFilter(f)
