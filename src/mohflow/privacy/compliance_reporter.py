"""
Compliance reporting for privacy and data protection regulations.

Provides automated compliance reporting for GDPR, HIPAA, PCI-DSS,
and other standards.
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import json

from .pii_detector import PIILevel, PIIDetectionResult


class ComplianceStandard(Enum):
    """Supported compliance standards."""

    GDPR = "gdpr"  # General Data Protection Regulation
    HIPAA = "hipaa"  # Health Insurance Portability and Accountability Act
    PCI_DSS = "pci_dss"  # Payment Card Industry Data Security Standard
    CCPA = "ccpa"  # California Consumer Privacy Act
    SOX = "sox"  # Sarbanes-Oxley Act
    CUSTOM = "custom"  # Custom compliance requirements


@dataclass
class ComplianceRule:
    """Definition of a compliance rule."""

    rule_id: str
    standard: ComplianceStandard
    description: str
    severity: str  # "critical", "high", "medium", "low"
    pii_types: Set[str]
    max_acceptable_level: PIILevel
    remediation_action: str


@dataclass
class ComplianceViolation:
    """A compliance violation detected in logs."""

    rule_id: str
    standard: ComplianceStandard
    severity: str
    description: str
    field_path: str
    detected_pii: PIIDetectionResult
    remediation_required: str
    timestamp: datetime


class ComplianceReporter:
    """
    Compliance reporting engine for privacy regulations.

    Monitors logging patterns and generates compliance reports
    for various data protection standards.
    """

    def __init__(
        self, enabled_standards: Optional[List[ComplianceStandard]] = None
    ):
        """
        Initialize compliance reporter.

        Args:
            enabled_standards: List of compliance standards to monitor
        """
        self.enabled_standards = enabled_standards or [
            ComplianceStandard.GDPR,
            ComplianceStandard.HIPAA,
            ComplianceStandard.PCI_DSS,
        ]

        self.compliance_rules = self._setup_compliance_rules()
        self.violations_log: List[ComplianceViolation] = []

        # Reporting configuration
        self.max_violations_to_store = 10000
        self.reporting_window_hours = 24

    def _setup_compliance_rules(self) -> List[ComplianceRule]:
        """Setup compliance rules for different standards."""
        rules = []

        # GDPR Rules
        if ComplianceStandard.GDPR in self.enabled_standards:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="GDPR-001",
                        standard=ComplianceStandard.GDPR,
                        description=(
                            "Personal identifiers must not appear in logs"
                        ),
                        severity="critical",
                        pii_types={"name", "email", "phone", "address"},
                        max_acceptable_level=PIILevel.NONE,
                        remediation_action=(
                            "Remove or pseudonymize personal identifiers"
                        ),
                    ),
                    ComplianceRule(
                        rule_id="GDPR-002",
                        standard=ComplianceStandard.GDPR,
                        description=(
                            "High-risk personal data requires encryption"
                        ),
                        severity="high",
                        pii_types={"ssn", "passport", "date_birth"},
                        max_acceptable_level=PIILevel.LOW,
                        remediation_action=(
                            "Encrypt or hash high-risk personal data"
                        ),
                    ),
                    ComplianceRule(
                        rule_id="GDPR-003",
                        standard=ComplianceStandard.GDPR,
                        description=(
                            "IP addresses are personal data under GDPR"
                        ),
                        severity="medium",
                        pii_types={"ip_address"},
                        max_acceptable_level=PIILevel.LOW,
                        remediation_action="Anonymize IP addresses in logs",
                    ),
                ]
            )

        # HIPAA Rules
        if ComplianceStandard.HIPAA in self.enabled_standards:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="HIPAA-001",
                        standard=ComplianceStandard.HIPAA,
                        description=(
                            "Protected Health Information (PHI) must not "
                            "be logged"
                        ),
                        severity="critical",
                        pii_types={
                            "medical_record",
                            "ssn",
                            "name",
                            "date_birth",
                        },
                        max_acceptable_level=PIILevel.NONE,
                        remediation_action="Remove all PHI from log messages",
                    ),
                    ComplianceRule(
                        rule_id="HIPAA-002",
                        standard=ComplianceStandard.HIPAA,
                        description=(
                            "Patient identifiers require de-identification"
                        ),
                        severity="high",
                        pii_types={"phone", "email", "address"},
                        max_acceptable_level=PIILevel.LOW,
                        remediation_action="De-identify patient information",
                    ),
                ]
            )

        # PCI-DSS Rules
        if ComplianceStandard.PCI_DSS in self.enabled_standards:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="PCI-001",
                        standard=ComplianceStandard.PCI_DSS,
                        description="Credit card numbers must never be logged",
                        severity="critical",
                        pii_types={"credit_card"},
                        max_acceptable_level=PIILevel.NONE,
                        remediation_action=(
                            "Remove all credit card numbers from logs"
                        ),
                    ),
                    ComplianceRule(
                        rule_id="PCI-002",
                        standard=ComplianceStandard.PCI_DSS,
                        description=(
                            "Sensitive authentication data must be protected"
                        ),
                        severity="critical",
                        pii_types={"token", "username"},
                        max_acceptable_level=PIILevel.LOW,
                        remediation_action=(
                            "Protect sensitive authentication data"
                        ),
                    ),
                ]
            )

        # CCPA Rules
        if ComplianceStandard.CCPA in self.enabled_standards:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="CCPA-001",
                        standard=ComplianceStandard.CCPA,
                        description=(
                            "Personal information must be minimized in logs"
                        ),
                        severity="high",
                        pii_types={
                            "name",
                            "email",
                            "phone",
                            "address",
                            "ip_address",
                        },
                        max_acceptable_level=PIILevel.LOW,
                        remediation_action=(
                            "Minimize personal information in logs"
                        ),
                    )
                ]
            )

        return rules

    def check_compliance(
        self, pii_detections: Dict[str, PIIDetectionResult]
    ) -> List[ComplianceViolation]:
        """
        Check PII detections against compliance rules.

        Args:
            pii_detections: Dictionary of field paths to PII detection results

        Returns:
            List of compliance violations found
        """
        violations = []

        for field_path, detection_result in pii_detections.items():
            for rule in self.compliance_rules:
                # Check if this rule applies to the detected PII types
                if any(
                    pii_type in rule.pii_types
                    for pii_type in detection_result.detected_types
                ):
                    # Check if the PII level exceeds acceptable threshold
                    if self._violates_level_threshold(
                        detection_result.level, rule.max_acceptable_level
                    ):
                        violation = ComplianceViolation(
                            rule_id=rule.rule_id,
                            standard=rule.standard,
                            severity=rule.severity,
                            description=rule.description,
                            field_path=field_path,
                            detected_pii=detection_result,
                            remediation_required=rule.remediation_action,
                            timestamp=datetime.now(),
                        )
                        violations.append(violation)

        return violations

    def _violates_level_threshold(
        self, detected_level: PIILevel, max_acceptable: PIILevel
    ) -> bool:
        """
        Check if detected PII level violates the maximum acceptable level.
        """
        level_hierarchy = {
            PIILevel.NONE: 0,
            PIILevel.LOW: 1,
            PIILevel.MEDIUM: 2,
            PIILevel.HIGH: 3,
            PIILevel.CRITICAL: 4,
        }

        return (
            level_hierarchy[detected_level] > level_hierarchy[max_acceptable]
        )

    def log_violations(self, violations: List[ComplianceViolation]) -> None:
        """Log compliance violations for reporting."""
        for violation in violations:
            self.violations_log.append(violation)

        # Maintain log size limit
        if len(self.violations_log) > self.max_violations_to_store:
            # Remove oldest violations
            excess = len(self.violations_log) - self.max_violations_to_store
            self.violations_log = self.violations_log[excess:]

    def generate_compliance_report(
        self,
        window_hours: Optional[int] = None,
        standards: Optional[List[ComplianceStandard]] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive compliance report.

        Args:
            window_hours: Hours to look back for violations (default: 24)
            standards: Specific standards to report on (default: all enabled)

        Returns:
            Detailed compliance report
        """
        window_hours = window_hours or self.reporting_window_hours
        standards = standards or self.enabled_standards

        # Filter violations by time window and standards
        cutoff_time = datetime.now() - timedelta(hours=window_hours)
        relevant_violations = [
            v
            for v in self.violations_log
            if v.timestamp >= cutoff_time and v.standard in standards
        ]

        # Aggregate violations by standard and severity
        violations_by_standard = {}
        violations_by_severity = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        violation_types = {}

        for violation in relevant_violations:
            # By standard
            standard_name = violation.standard.value
            if standard_name not in violations_by_standard:
                violations_by_standard[standard_name] = []
            violations_by_standard[standard_name].append(violation)

            # By severity
            violations_by_severity[violation.severity] += 1

            # By PII type
            for pii_type in violation.detected_pii.detected_types:
                if pii_type not in violation_types:
                    violation_types[pii_type] = 0
                violation_types[pii_type] += 1

        # Calculate compliance score (0-100, higher is better)
        total_possible_violations = (
            len(self.compliance_rules) * 100
        )  # Theoretical max

        # Weight violations by severity
        weighted_violations = (
            violations_by_severity["critical"] * 4
            + violations_by_severity["high"] * 3
            + violations_by_severity["medium"] * 2
            + violations_by_severity["low"] * 1
        )

        compliance_score = max(
            0,
            100
            - (weighted_violations / max(1, total_possible_violations // 10))
            * 100,
        )

        # Determine compliance status
        if compliance_score >= 90:
            status = "COMPLIANT"
        elif compliance_score >= 75:
            status = "MOSTLY_COMPLIANT"
        elif compliance_score >= 50:
            status = "NON_COMPLIANT"
        else:
            status = "CRITICAL_NON_COMPLIANCE"

        # Generate remediation recommendations
        recommendations = self._generate_remediation_recommendations(
            relevant_violations
        )

        return {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "reporting_window_hours": window_hours,
                "standards_checked": [s.value for s in standards],
                "total_violations": len(relevant_violations),
            },
            "compliance_summary": {
                "overall_status": status,
                "compliance_score": round(compliance_score, 2),
                "violations_by_severity": violations_by_severity,
                "violations_by_standard": {
                    k: len(v) for k, v in violations_by_standard.items()
                },
                "most_common_violation_types": dict(
                    sorted(
                        violation_types.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                ),
            },
            "detailed_violations": [
                {
                    "rule_id": v.rule_id,
                    "standard": v.standard.value,
                    "severity": v.severity,
                    "description": v.description,
                    "field_path": v.field_path,
                    "pii_types": v.detected_pii.detected_types,
                    "pii_level": v.detected_pii.level.value,
                    "confidence": v.detected_pii.confidence_score,
                    "timestamp": v.timestamp.isoformat(),
                    "remediation": v.remediation_required,
                }
                for v in relevant_violations[-50:]  # Last 50 violations
            ],
            "remediation_plan": recommendations,
            "compliance_rules_checked": [
                {
                    "rule_id": rule.rule_id,
                    "standard": rule.standard.value,
                    "description": rule.description,
                    "severity": rule.severity,
                }
                for rule in self.compliance_rules
                if rule.standard in standards
            ],
        }

    def _generate_remediation_recommendations(
        self, violations: List[ComplianceViolation]
    ) -> List[Dict[str, Any]]:
        """Generate prioritized remediation recommendations."""
        recommendations = []

        # Group violations by remediation action
        remediation_groups = {}
        for violation in violations:
            action = violation.remediation_required
            if action not in remediation_groups:
                remediation_groups[action] = []
            remediation_groups[action].append(violation)

        # Create prioritized recommendations
        severity_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}

        for action, action_violations in remediation_groups.items():
            # Calculate priority based on severity and count
            max_severity = max(v.severity for v in action_violations)
            priority = severity_priority[max_severity]

            recommendations.append(
                {
                    "priority": priority,
                    "priority_label": max_severity.upper(),
                    "action": action,
                    "affected_violations": len(action_violations),
                    "standards_impacted": list(
                        set(v.standard.value for v in action_violations)
                    ),
                    "estimated_effort": self._estimate_remediation_effort(
                        action, len(action_violations)
                    ),
                    "compliance_impact": (
                        f"Resolves {len(action_violations)} violation(s)"
                    ),
                }
            )

        # Sort by priority (highest first)
        recommendations.sort(key=lambda x: x["priority"], reverse=True)

        return recommendations

    def _estimate_remediation_effort(
        self, action: str, violation_count: int
    ) -> str:
        """Estimate effort required for remediation."""
        base_effort = {
            "Remove": "Low",
            "Encrypt": "Medium",
            "Anonymize": "Medium",
            "De-identify": "High",
            "Pseudonymize": "High",
        }

        # Find matching base effort
        effort = "Medium"  # Default
        for keyword, base in base_effort.items():
            if keyword.lower() in action.lower():
                effort = base
                break

        # Adjust based on violation count
        if violation_count > 50:
            effort_levels = ["Low", "Medium", "High", "Very High"]
            current_index = effort_levels.index(effort)
            effort = effort_levels[
                min(current_index + 1, len(effort_levels) - 1)
            ]

        return effort

    def export_compliance_report(
        self, report: Dict[str, Any], format: str = "json"
    ) -> str:
        """
        Export compliance report in various formats.

        Args:
            report: Compliance report dictionary
            format: Export format ("json", "csv", "html")

        Returns:
            Formatted report string
        """
        if format.lower() == "json":
            return json.dumps(report, indent=2, default=str)

        elif format.lower() == "csv":
            return self._export_csv_report(report)

        elif format.lower() == "html":
            return self._export_html_report(report)

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_csv_report(self, report: Dict[str, Any]) -> str:
        """Export report as CSV format."""
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Write summary
        writer.writerow(["Compliance Report Summary"])
        writer.writerow(
            ["Generated At", report["report_metadata"]["generated_at"]]
        )
        writer.writerow(
            ["Status", report["compliance_summary"]["overall_status"]]
        )
        writer.writerow(
            ["Score", report["compliance_summary"]["compliance_score"]]
        )
        writer.writerow([])

        # Write violations
        writer.writerow(["Detailed Violations"])
        writer.writerow(
            [
                "Rule ID",
                "Standard",
                "Severity",
                "Field Path",
                "PII Types",
                "Timestamp",
            ]
        )

        for violation in report["detailed_violations"]:
            writer.writerow(
                [
                    violation["rule_id"],
                    violation["standard"],
                    violation["severity"],
                    violation["field_path"],
                    ", ".join(violation["pii_types"]),
                    violation["timestamp"],
                ]
            )

        return output.getvalue()

    def _export_html_report(self, report: Dict[str, Any]) -> str:
        """Export report as HTML format."""
        # Build HTML in parts to avoid long lines
        html = "<!DOCTYPE html><html><head><title>Compliance Report</title>"
        html += "<style>"
        html += "body { font-family: Arial, sans-serif; margin: 20px; }"
        html += ".header { background-color: #f0f0f0; padding: 10px; "
        html += "border-radius: 5px; }"
        html += ".status-compliant { color: green; font-weight: bold; }"
        html += ".status-non-compliant { color: red; font-weight: bold; }"
        html += "table { border-collapse: collapse; width: 100%; "
        html += "margin-top: 20px; }"
        html += "th, td { border: 1px solid #ddd; padding: 8px; "
        html += "text-align: left; }"
        html += "th { background-color: #f2f2f2; }"
        html += ".critical { background-color: #ffebee; }"
        html += ".high { background-color: #fff3e0; }"
        html += "</style></head><body>"
        html += '<div class="header"><h1>Compliance Report</h1>'
        html += "<p><strong>Generated:</strong> "
        html += f"{report['report_metadata']['generated_at']}</p>"

        status = report["compliance_summary"]["overall_status"]
        html += '<p><strong>Status:</strong> <span class="status-'
        html += f'{status.lower().replace("_", "-")}">{status}</span></p>'
        html += "<p><strong>Score:</strong> "
        html += f"{report['compliance_summary']['compliance_score']}/100</p>"
        html += "</div><h2>Violations by Severity</h2><table>"
        html += "<tr><th>Severity</th><th>Count</th></tr>"

        for severity, count in report["compliance_summary"][
            "violations_by_severity"
        ].items():
            html += (
                f"<tr class='{severity}'><td>{severity.title()}</td>"
                f"<td>{count}</td></tr>"
            )

        html += "</table><h2>Recent Violations</h2><table>"
        html += "<tr><th>Rule</th><th>Standard</th><th>Severity</th>"
        html += "<th>Field</th><th>PII Types</th><th>Time</th></tr>"

        for violation in report["detailed_violations"][:20]:  # Show last 20
            html += f"<tr class='{violation['severity']}'>"
            html += f"<td>{violation['rule_id']}</td>"
            html += f"<td>{violation['standard']}</td>"
            html += f"<td>{violation['severity'].title()}</td>"
            html += f"<td>{violation['field_path']}</td>"
            html += f"<td>{', '.join(violation['pii_types'])}</td>"
            html += f"<td>{violation['timestamp'][:19]}</td>"
            html += "</tr>"

        html += "</table></body></html>"

        return html

    def get_compliance_statistics(self) -> Dict[str, Any]:
        """Get compliance monitoring statistics."""
        total_violations = len(self.violations_log)

        if total_violations == 0:
            return {
                "total_violations_logged": 0,
                "violations_by_standard": {},
                "violations_by_severity": {},
                "average_violations_per_day": 0,
                "most_recent_violation": None,
            }

        # Count by standard and severity
        by_standard = {}
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for violation in self.violations_log:
            standard = violation.standard.value
            by_standard[standard] = by_standard.get(standard, 0) + 1
            by_severity[violation.severity] += 1

        # Calculate daily average
        if self.violations_log:
            oldest = min(v.timestamp for v in self.violations_log)
            days_span = max(1, (datetime.now() - oldest).days)
            avg_per_day = total_violations / days_span
        else:
            avg_per_day = 0

        return {
            "total_violations_logged": total_violations,
            "violations_by_standard": by_standard,
            "violations_by_severity": by_severity,
            "average_violations_per_day": round(avg_per_day, 2),
            "most_recent_violation": (
                max(
                    self.violations_log, key=lambda v: v.timestamp
                ).timestamp.isoformat()
                if self.violations_log
                else None
            ),
            "compliance_rules_active": len(self.compliance_rules),
            "enabled_standards": [s.value for s in self.enabled_standards],
        }
