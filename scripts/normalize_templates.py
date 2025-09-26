#!/usr/bin/env python3
"""
Template Normalization Script

Finds templates with over-escaping and optionally normalizes them for review.
Fixes MarkdownV2 templates that have been entirely escaped instead of just user variables.
"""

import sys
import os
import re
import argparse
import ast
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging import get_logger, setup_logging
from utils.messaging import validate_template, escape_markdown_v2, render_markdown_v2

# Setup logging
setup_logging(console_log_level=20)  # INFO level  
logger = get_logger(__name__)


class TemplateIssue:
    """Represents a template with formatting issues."""
    
    def __init__(
        self,
        file_path: str,
        line_number: int,
        original_template: str,
        issue_type: str,
        severity: str = "MEDIUM",
        suggested_fix: Optional[str] = None
    ):
        self.file_path = file_path
        self.line_number = line_number
        self.original_template = original_template
        self.issue_type = issue_type
        self.severity = severity
        self.suggested_fix = suggested_fix
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            'file': self.file_path,
            'line': self.line_number,
            'issue_type': self.issue_type,
            'severity': self.severity,
            'original': self.original_template[:100] + "..." if len(self.original_template) > 100 else self.original_template,
            'suggested_fix': self.suggested_fix[:100] + "..." if self.suggested_fix and len(self.suggested_fix) > 100 else self.suggested_fix
        }


def detect_over_escaped_templates(content: str, file_path: str) -> List[TemplateIssue]:
    """Detect templates that have been entirely escaped."""
    
    issues = []
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        # Look for string literals that might be templates
        if '"' in line or "'" in line:
            # Extract string literals from the line
            string_literals = extract_string_literals(line)
            
            for literal in string_literals:
                issues.extend(analyze_template_string(literal, file_path, line_num))
    
    return issues


def extract_string_literals(line: str) -> List[str]:
    """Extract string literals from a line of Python code."""
    
    literals = []
    
    try:
        # Try to parse as Python AST to find string literals
        # This is a simplified approach - in practice you'd need more robust parsing
        
        # Look for common string patterns
        patterns = [
            r'"([^"]*\\[^"]*)"',  # Double-quoted strings with escapes
            r"'([^']*\\[^']*)'",  # Single-quoted strings with escapes
            r'f"([^"]*{[^}]*}[^"]*)"',  # f-strings
            r"f'([^']*{[^}]*}[^']*)'",  # f-strings with single quotes
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                literals.append(match.group(1))
                
    except Exception as e:
        logger.debug(f"Error parsing line: {e}")
    
    return literals


def analyze_template_string(template: str, file_path: str, line_num: int) -> List[TemplateIssue]:
    """Analyze a template string for issues."""
    
    issues = []
    
    # Check for over-escaping patterns
    if is_over_escaped(template):
        suggested_fix = fix_over_escaping(template)
        issue = TemplateIssue(
            file_path=file_path,
            line_number=line_num,
            original_template=template,
            issue_type="OVER_ESCAPED",
            severity="HIGH",
            suggested_fix=suggested_fix
        )
        issues.append(issue)
    
    # Check for missing variable placeholders
    if has_missing_variables(template):
        issue = TemplateIssue(
            file_path=file_path,
            line_number=line_num,
            original_template=template,
            issue_type="MISSING_VARIABLES",
            severity="MEDIUM"
        )
        issues.append(issue)
    
    # Check for unsafe markdown patterns
    if has_unsafe_markdown(template):
        issue = TemplateIssue(
            file_path=file_path,
            line_number=line_num,
            original_template=template,
            issue_type="UNSAFE_MARKDOWN",
            severity="LOW"
        )
        issues.append(issue)
    
    return issues


def is_over_escaped(template: str) -> bool:
    """Check if template is over-escaped (entire template escaped vs just variables)."""
    
    # Count escape characters
    escape_count = template.count('\\')
    
    # If more than 20% of characters are escapes, likely over-escaped
    if len(template) > 0 and (escape_count / len(template)) > 0.2:
        return True
    
    # Look for specific over-escaping patterns
    over_escape_patterns = [
        r'\\\*[^{]*\\\*',  # \*text\* instead of *{var}*
        r'\\\\_[^{]*\\\\_',  # \\_text\_ instead of _{var}_
        r'\\\\n',  # Double-escaped newlines
        r'\\\\\.',  # Escaped periods in template structure
        r'\\\\!',   # Escaped exclamations in template structure
    ]
    
    for pattern in over_escape_patterns:
        if re.search(pattern, template):
            return True
    
    return False


def has_missing_variables(template: str) -> bool:
    """Check if template appears to have hardcoded values instead of variables."""
    
    # Look for patterns that should probably be variables
    hardcoded_patterns = [
        r'\b\d+\.\d+\b',  # Numbers like amounts
        r'\b[A-Z]{3,}\b',  # Currency codes, etc.
        r'@\w+',          # Usernames
        r'https?://\S+',  # URLs
    ]
    
    for pattern in hardcoded_patterns:
        if re.search(pattern, template):
            # Check if it's in a variable placeholder
            matches = re.finditer(pattern, template)
            for match in matches:
                start, end = match.span()
                # Simple check if it's inside {}
                before = template[:start]
                after = template[end:]
                if before.count('{') == before.count('}') and after.count('{') == after.count('}'):
                    return True
    
    return False


def has_unsafe_markdown(template: str) -> bool:
    """Check for potentially unsafe markdown patterns."""
    
    unsafe_patterns = [
        r'\*\*[^*]+\*\*',  # Double asterisks (not MarkdownV2)
        r'__[^_]+__',      # Double underscores (not MarkdownV2)
        r'\[([^\]]+)\]\(([^)]+)\).*\[([^\]]+)\]\(([^)]+)\)',  # Multiple links without spacing
    ]
    
    for pattern in unsafe_patterns:
        if re.search(pattern, template):
            return True
    
    return False


def fix_over_escaping(template: str) -> str:
    """Attempt to fix over-escaped template."""
    
    # Remove excessive escaping from template structure
    fixed = template
    
    # Remove double escaping
    fixed = fixed.replace('\\\\', '\\')
    
    # Fix common over-escaping patterns
    fixes = [
        (r'\\\*([^{]*?)\\\*', r'*\1*'),  # \*text\* -> *text*
        (r'\\\\_([^{]*?)\\\\_', r'_\1_'),  # \\_text\_ -> _text_
        (r'\\\.', '.'),  # \\. -> .
        (r'\\!', '!'),   # \\! -> !
        (r'\\n', '\n'),  # \\n -> \n (actual newline)
    ]
    
    for pattern, replacement in fixes:
        fixed = re.sub(pattern, replacement, fixed)
    
    # Validate the fix doesn't break the template
    try:
        # Test with dummy variables
        test_vars = {'username': 'test', 'amount': '100', 'provider_name': 'test'}
        render_markdown_v2(fixed, **test_vars)
        return fixed
    except Exception:
        # If fix breaks template, return original with warning
        return template + " [FIX_FAILED]"


def scan_directory(directory: str, extensions: List[str] = None) -> List[TemplateIssue]:
    """Scan directory for template issues."""
    
    if extensions is None:
        extensions = ['.py']
    
    issues = []
    
    for file_path in Path(directory).rglob('*'):
        if file_path.suffix.lower() in extensions:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_issues = detect_over_escaped_templates(content, str(file_path))
                    issues.extend(file_issues)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
    
    return issues


def generate_report(issues: List[TemplateIssue], output_file: str):
    """Generate HTML report of template issues."""
    
    if not issues:
        logger.info("No template issues found")
        return
    
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Template Issues Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .issue { border: 1px solid #ddd; margin: 10px 0; padding: 10px; }
        .high { border-left: 5px solid #d73527; }
        .medium { border-left: 5px solid #f0ad4e; }
        .low { border-left: 5px solid #5cb85c; }
        .code { background: #f5f5f5; padding: 5px; font-family: monospace; }
        .fix { background: #e8f5e8; padding: 5px; font-family: monospace; }
    </style>
</head>
<body>
    <h1>Template Issues Report</h1>
    <p>Generated: {timestamp}</p>
    <p>Total Issues: {total_issues}</p>
""".format(
        timestamp=datetime.utcnow().isoformat(),
        total_issues=len(issues)
    )
    
    # Group by severity
    by_severity = {}
    for issue in issues:
        severity = issue.severity.lower()
        if severity not in by_severity:
            by_severity[severity] = []
        by_severity[severity].append(issue)
    
    for severity in ['high', 'medium', 'low']:
        if severity in by_severity:
            html_content += f"<h2>{severity.title()} Priority Issues ({len(by_severity[severity])})</h2>\n"
            
            for issue in by_severity[severity]:
                html_content += f"""
    <div class="issue {severity}">
        <h3>{issue.issue_type} in {issue.file_path}:{issue.line_number}</h3>
        <p><strong>Original:</strong></p>
        <div class="code">{escape_html(issue.original_template)}</div>
"""
                
                if issue.suggested_fix:
                    html_content += f"""
        <p><strong>Suggested Fix:</strong></p>
        <div class="fix">{escape_html(issue.suggested_fix)}</div>
"""
                
                html_content += "    </div>\n"
    
    html_content += """
</body>
</html>
"""
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    logger.info(f"Generated report: {output_file}")


def escape_html(text: str) -> str:
    """Escape HTML characters."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def apply_fixes(issues: List[TemplateIssue], dry_run: bool = True) -> int:
    """Apply fixes to template issues."""
    
    fixes_applied = 0
    
    # Group issues by file
    by_file = {}
    for issue in issues:
        if issue.file_path not in by_file:
            by_file[issue.file_path] = []
        by_file[issue.file_path].append(issue)
    
    for file_path, file_issues in by_file.items():
        if not any(issue.suggested_fix for issue in file_issues):
            continue
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            # Apply fixes (in reverse line order to maintain line numbers)
            for issue in sorted(file_issues, key=lambda x: x.line_number, reverse=True):
                if issue.suggested_fix and issue.line_number <= len(lines):
                    old_line = lines[issue.line_number - 1]
                    # Simple replacement - in practice would need more sophisticated matching
                    new_line = old_line.replace(issue.original_template, issue.suggested_fix)
                    
                    if new_line != old_line:
                        if not dry_run:
                            lines[issue.line_number - 1] = new_line
                        fixes_applied += 1
                        logger.info(f"{'Would fix' if dry_run else 'Fixed'} {file_path}:{issue.line_number}")
            
            # Write back the file
            if not dry_run and fixes_applied > 0:
                with open(file_path, 'w') as f:
                    f.writelines(lines)
                    
        except Exception as e:
            logger.error(f"Error applying fixes to {file_path}: {e}")
    
    return fixes_applied


def main():
    """Main function."""
    
    parser = argparse.ArgumentParser(description="Normalize over-escaped templates")
    parser.add_argument('directory', nargs='?', default='.',
                       help='Directory to scan (default: current)')
    parser.add_argument('--extensions', nargs='+', default=['.py'],
                       help='File extensions to scan')
    parser.add_argument('--report', '-r', default='template_issues.html',
                       help='Output report file')
    parser.add_argument('--fix', action='store_true',
                       help='Apply suggested fixes')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Dry run mode (default: true)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(10)  # DEBUG level
    
    logger.info(f"Scanning {args.directory} for template issues...")
    
    # Scan for issues
    issues = scan_directory(args.directory, args.extensions)
    
    logger.info(f"Found {len(issues)} template issues")
    
    # Generate report
    generate_report(issues, args.report)
    
    # Apply fixes if requested
    if args.fix:
        fixes_applied = apply_fixes(issues, dry_run=args.dry_run)
        mode = "would apply" if args.dry_run else "applied"
        logger.info(f"{mode} {fixes_applied} fixes")
    
    logger.info("Template normalization completed")
    
    return 0 if not issues else 1


if __name__ == "__main__":
    from datetime import datetime
    exit(main())