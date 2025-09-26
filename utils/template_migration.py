#!/usr/bin/env python3
"""
Template migration utility to fix over-escaped MarkdownV2 templates.
Identifies and fixes templates that escape entire content instead of just variables.
"""

import re
import os
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TemplateIssue:
    file_path: str
    line_number: int
    issue_type: str
    severity: str
    original_content: str
    suggested_fix: str
    description: str

def scan_for_over_escaped_templates(directory: str) -> List[TemplateIssue]:
    """
    Scan directory for over-escaped MarkdownV2 templates.
    
    Args:
        directory: Directory to scan
        
    Returns:
        List of template issues found
    """
    issues = []
    
    # Pattern for over-escaped templates (entire strings escaped)
    over_escaped_pattern = re.compile(r'["\']([^"\']*\\[_*\[\]()~`>#+=\-=|{}.!][^"\']*)["\']')
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                    for line_num, line in enumerate(lines, 1):
                        # Look for potential over-escaped templates
                        matches = over_escaped_pattern.findall(line)
                        for match in matches:
                            if _is_over_escaped_template(match):
                                issues.append(TemplateIssue(
                                    file_path=file_path,
                                    line_number=line_num,
                                    issue_type="over_escaped_template",
                                    severity="medium",
                                    original_content=match,
                                    suggested_fix=_suggest_template_fix(match),
                                    description="Template has escaped formatting instead of variable escaping"
                                ))
                                
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")
                    
    return issues

def _is_over_escaped_template(text: str) -> bool:
    """Check if text appears to be an over-escaped template."""
    # Look for escaped markdown formatting that should be unescaped
    problematic_patterns = [
        r'\\\*[^*]*\\\*',  # \*text\* instead of *text*
        r'\\_[^_]*\\_',    # \_text\_ instead of _text_
        r'\\`[^`]*\\`',    # \`text\` instead of `text`
        r'\\\[[^\]]*\\\]', # \[text\] instead of [text]
    ]
    
    for pattern in problematic_patterns:
        if re.search(pattern, text):
            return True
    return False

def _suggest_template_fix(text: str) -> str:
    """Suggest a fix for over-escaped template."""
    # Remove escaping from formatting characters but keep variable placeholders
    fixes = [
        (r'\\\*([^*{]*(?:\{[^}]+\}[^*{]*)*)\\\*', r'*\1*'),  # \*text\* → *text*
        (r'\\_([^_{]*(?:\{[^}]+\}[^_{]*)*)\\_', r'_\1_'),      # \_text\_ → _text_
        (r'\\`([^`{]*(?:\{[^}]+\}[^`{]*)*)`', r'`\1`'),       # \`text\` → `text`
        (r'\\\[([^\[{]*(?:\{[^}]+\}[^\[{]*)*)\\\]', r'[\1]'), # \[text\] → [text]
    ]
    
    result = text
    for pattern, replacement in fixes:
        result = re.sub(pattern, replacement, result)
    
    return result

def generate_migration_report(issues: List[TemplateIssue], output_file: str):
    """Generate a migration report."""
    with open(output_file, 'w') as f:
        f.write("# Template Migration Report\n\n")
        f.write(f"Found {len(issues)} template issues:\n\n")
        
        for issue in issues:
            f.write(f"## {issue.file_path}:{issue.line_number}\n")
            f.write(f"**Issue**: {issue.description}\n")
            f.write(f"**Severity**: {issue.severity}\n")
            f.write(f"**Original**: `{issue.original_content}`\n")
            f.write(f"**Suggested**: `{issue.suggested_fix}`\n\n")

if __name__ == "__main__":
    import sys
    
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    issues = scan_for_over_escaped_templates(directory)
    
    print(f"Found {len(issues)} template issues")
    
    if issues:
        generate_migration_report(issues, "template_migration_report.md")
        print("Report generated: template_migration_report.md")
    else:
        print("No template issues found!")