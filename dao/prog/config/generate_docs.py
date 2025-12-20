#!/usr/bin/env python3
"""Generate configuration documentation and JSON schema from Pydantic models.

This script generates both config_schema.json and SETTINGS.md from the Pydantic models,
ensuring they stay perfectly in sync. The models are the single source of truth.

Usage:
    python -m dao.prog.config.generate_docs
    
Exit codes:
    0: Success - all fields have documentation
    1: Failure - one or more fields missing description
"""

import json
import sys
from pathlib import Path
from typing import Any
from collections import defaultdict

from dao.prog.config.versions.v0 import ConfigurationV0


# Icon mapping for x-icon values
ICON_MAP = {
    'battery-charging': '🔋',
    'solar-panel': '☀️',
    'car-electric': '🚗',
    'heat-pump': '🌡️',
    'water-boiler': '💧',
    'washing-machine': '🧺',
    'database': '💾',
    'currency-eur': '💰',
    'transmission-tower': '⚡',
    'chart-line': '📈',
    'bell': '🔔',
    'database-clock': '⏰',
    'view-dashboard': '📊',
    'chart-bar': '📉',
    'clock-outline': '🕐',
    'lightning-bolt': '⚡',
    'home-assistant': '🏠',
}


def generate_markdown_from_schema(schema: dict[str, Any], title_prefix: str = "", defs: dict[str, Any] = None) -> tuple[str, list[str]]:
    """Generate markdown documentation from a JSON schema.
    
    Args:
        schema: The JSON schema dictionary
        title_prefix: Prefix for markdown headers (e.g., "##" or "###")
        defs: The $defs dictionary for resolving references
        
    Returns:
        Tuple of (markdown_string, validation_errors)
    """
    validation_errors = []
    lines = []
    defs = defs or {}
    
    # Get model title and description
    model_title = schema.get('title', 'Unknown')
    model_desc = schema.get('description', '')
    
    # Get extension fields
    x_icon = schema.get('x-icon', '')
    x_help = schema.get('x-help', '')
    x_docs_url = schema.get('x-docs-url', '')
    x_category = schema.get('x-category', '')
    
    if title_prefix:
        # Add icon if available
        icon_emoji = ICON_MAP.get(x_icon, '')
        title_line = f"{title_prefix}{icon_emoji} {model_title}" if icon_emoji else f"{title_prefix}{model_title}"
        lines.append(title_line)
        lines.append("")
        
        # Add short description
        if model_desc:
            lines.append(f"_{model_desc}_")
            lines.append("")
        
        # Add category badge
        if x_category:
            lines.append(f"**Category:** `{x_category}`")
            lines.append("")
        
        # Add detailed help if available
        if x_help:
            lines.append(x_help)
            lines.append("")
        
        # Add external docs link if available
        if x_docs_url:
            lines.append(f"📚 [**View detailed documentation →**]({x_docs_url})")
            lines.append("")
    
    # Get properties
    properties = schema.get('properties', {})
    required = set(schema.get('required', []))
    
    if not properties:
        lines.append("*No configuration fields.*")
        lines.append("")
        return "\n".join(lines), validation_errors
    
    # Create table header
    lines.append("| Field | Type | Required | Default | Description |")
    lines.append("|-------|------|----------|---------|-------------|")
    
    for field_name, field_schema in properties.items():
        # Extract field info from JSON schema
        field_type = get_type_from_schema(field_schema, defs)
        is_required = field_name in required
        description = field_schema.get('description', '')
        
        # Validate description exists (use title as fallback for SecretStr/FlexValue internal fields)
        if not description:
            title = field_schema.get('title', '')
            if title:
                # For internal model fields like SecretStr.secret_key, use title
                description = title
            else:
                validation_errors.append(f"ERROR: {model_title}.{field_name} - Missing description")
                description = "MISSING DESCRIPTION"
        
        # Enhance description with extension fields
        x_unit = field_schema.get('x-unit', '')
        x_validation_hint = field_schema.get('x-validation-hint', '')
        
        # Add unit to description
        if x_unit:
            description = f"{description} (Unit: `{x_unit}`)"
        
        # Add validation hint
        if x_validation_hint:
            description = f"{description} _{x_validation_hint}_"
        
        # Append enum options to description if present
        if 'enum' in field_schema:
            enum_values = field_schema['enum']
            enum_str = ', '.join(f'`{v}`' for v in enum_values)
            description = f"{description}. Options: {enum_str}"
        
        # Format required column
        required_mark = "Yes" if is_required else "No"
        
        # Get default value for all field types
        default = get_default_from_schema(field_schema, is_required, defs)
        lines.append(f"| `{field_name}` | {field_type} | {required_mark} | {default} | {description} |")
    
    lines.append("")
    
    # Add field details section if any fields have x-help
    fields_with_help = [(name, props) for name, props in properties.items() if props.get('x-help')]
    if fields_with_help:
        lines.append("<details>")
        lines.append("<summary><b>📖 Field Details</b> (click to expand)</summary>")
        lines.append("")
        for field_name, field_props in fields_with_help:
            x_help = field_props.get('x-help', '')
            lines.append(f"**`{field_name}`**")
            lines.append("")
            lines.append(x_help)
            lines.append("")
        lines.append("</details>")
        lines.append("")
    
    return "\n".join(lines), validation_errors


def get_type_from_schema(field_schema: dict[str, Any], defs: dict[str, Any]) -> str:
    """Extract human-readable type description from JSON schema."""
    # Handle $ref
    if '$ref' in field_schema:
        ref_path = field_schema['$ref'].split('/')[-1]
        anchor = ref_path.lower()
        return f"[{ref_path}](#{anchor})"
    
    # Handle anyOf (used for Optional types and unions)
    if 'anyOf' in field_schema:
        types = []
        has_null = False
        for sub_schema in field_schema['anyOf']:
            if sub_schema.get('type') == 'null':
                has_null = True
            else:
                types.append(get_type_from_schema(sub_schema, defs))
        # Use 'or' for readability instead of pipe which breaks markdown tables
        if len(types) > 1:
            type_str = " or ".join(types)
        else:
            type_str = types[0] if types else "unknown"
        return f"{type_str} (optional)" if has_null else type_str
    
    # Handle arrays
    if field_schema.get('type') == 'array':
        item_type = get_type_from_schema(field_schema.get('items', {}), defs)
        return f"list[{item_type}]"
    
    # Handle basic types
    json_type = field_schema.get('type', 'unknown')
    type_map = {
        'string': 'string',
        'integer': 'integer',
        'number': 'number',
        'boolean': 'boolean',
        'object': 'object',
        'null': 'null',
    }
    
    return type_map.get(json_type, json_type)


def get_default_from_schema(field_schema: dict[str, Any], is_required: bool, defs: dict[str, Any]) -> str:
    """Extract default value representation from JSON schema."""
    if is_required:
        return "—"
    
    # Check if default is specified
    if 'default' not in field_schema:
        # Model references (not Optional) → uses default_factory, can omit but NOT set to null
        if '$ref' in field_schema:
            return "_See nested fields_"
        
        # Union types with model refs → may have default_factory
        if 'anyOf' in field_schema:
            for sub_schema in field_schema['anyOf']:
                if '$ref' in sub_schema:
                    # If it's Optional[ModelType], can be null
                    if any(s.get('type') == 'null' for s in field_schema['anyOf']):
                        return "`null`"
                    # Otherwise, has default_factory
                    return "_See nested fields_"
        
        # Simple types without default → defaults to None/null
        return "`null`"
    
    default = field_schema['default']
    
    if default is None:
        return "`null`"
    if isinstance(default, str):
        return f'`"{default}"`'
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    if isinstance(default, (int, float)):
        return f"`{default}`"
    if isinstance(default, list):
        return "`[]`" if not default else f"`{default}`"
    if isinstance(default, dict):
        return "`{{}}`" if not default else f"`{default}`"
    
    return f"`{default}`"


def main():
    """Generate both JSON schema and markdown documentation."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent.parent
    
    # Step 1: Generate JSON Schema
    print("Generating JSON schema from Pydantic models...")
    schema_path = repo_root / 'config_schema.json'
    
    schema = ConfigurationV0.model_json_schema(
        mode='serialization',
        by_alias=True,
    )
    
    # Add metadata
    schema['$schema'] = 'http://json-schema.org/draft-07/schema#'
    schema['title'] = 'Day Ahead Optimizer Configuration'
    schema['description'] = (
        'Configuration schema for the Day Ahead Optimizer Home Assistant add-on. '
        'This schema defines all available configuration options including battery settings, '
        'solar panels, pricing, scheduler, graphics, and more.'
    )
    
    # Save schema
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    
    print(f"Schema saved to: {schema_path}")
    print(f"Schema contains {len(schema.get('properties', {}))} top-level properties")
    print(f"Definitions: {len(schema.get('$defs', {}))} models defined")
    print()
    
    # Step 2: Generate Markdown Documentation
    print("Generating SETTINGS.md from JSON schema...")
    
    # Track all validation errors
    all_errors = []
    
    # Get all definitions
    defs = schema.get('$defs', {})
    
    # Organize models by x-ui-group
    # Structure: {x-ui-group: [(x_order, model_name, model_schema)]}
    grouped_models = defaultdict(list)
    for model_name, model_schema in defs.items():
        x_ui_group = model_schema.get('x-ui-group', 'Other')
        x_order = model_schema.get('x-order', 999)
        grouped_models[x_ui_group].append((x_order, model_name, model_schema))
    
    # Sort models within each group by x-order
    for group_name in grouped_models:
        grouped_models[group_name].sort()  # Sort by x-order
    
    # Generate markdown
    lines = []
    
    # Header
    lines.append("# Day Ahead Optimizer - Configuration Settings")
    lines.append("")
    lines.append("**Auto-generated from Pydantic models using JSON Schema**")
    lines.append("")
    lines.append(f"📋 **Configuration Version:** `{schema.get('properties', {}).get('config_version', {}).get('default', '0')}`")
    lines.append("")
    lines.append("> ⚠️ **Do not edit this file manually!**")
    lines.append("> This documentation is auto-generated from Pydantic models.")
    lines.append("> To update, modify the model docstrings and Field descriptions, then run:")
    lines.append("> ```bash")
    lines.append("> python -m dao.prog.config.generate_docs")
    lines.append("> ```")
    lines.append("")
    
    # Table of Contents
    lines.append("## 📑 Table of Contents")
    lines.append("")
    
    # Add quick reference section
    lines.append("- [Quick Reference](#quick-reference)")
    lines.append("")
    
    # Sort groups by minimum x-order of models in the group
    sorted_groups = sorted(
        grouped_models.items(),
        key=lambda item: min(order for order, _, _ in item[1])
    )
    
    # Add groups to TOC
    for group_name, models in sorted_groups:
        group_anchor = group_name.lower().replace(' ', '-').replace('&', 'and')
        lines.append(f"- [{group_name}](#{group_anchor})")
        
        for order, model_name, model_schema in models:
            model_anchor = model_name.lower().replace(' ', '-')
            icon = ICON_MAP.get(model_schema.get('x-icon', ''), '')
            icon_str = f"{icon} " if icon else ""
            lines.append(f"  - [{icon_str}{model_name}](#{model_anchor})")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Quick Reference section
    lines.append("## Quick Reference")
    lines.append("")
    lines.append("### Legend")
    lines.append("")
    lines.append("| Symbol | Meaning |")
    lines.append("|--------|---------|")
    lines.append("| 📖 | Field has detailed help text (expand for details) |")
    lines.append("| 📚 | External documentation available |")
    lines.append("")
    
    lines.append("### Required vs Optional")
    lines.append("")
    lines.append("| Value | Meaning |")
    lines.append("|-------|---------|")
    lines.append("| Yes | Required field - must be provided in configuration |")
    lines.append("| No | Optional field |")
    lines.append("")
    
    lines.append("### Default Values")
    lines.append("")
    lines.append("| Value | Meaning |")
    lines.append("|-------|---------|")
    lines.append("| `—` | No default (required field) |")
    lines.append("| `null` | Optional, defaults to null/none |")
    lines.append("| `value` | Optional with this default value |")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # Generate documentation grouped by x-ui-group
    for group_name, models in sorted_groups:
        lines.append(f"## {group_name}")
        lines.append("")
        
        group_anchor = group_name.lower().replace(' ', '-').replace('&', 'and')
        lines.append(f'<a id="{group_anchor}"></a>')
        lines.append("")
        
        # Generate docs for each model in this group
        for order, model_name, model_schema in models:
            doc, errors = generate_markdown_from_schema(model_schema, title_prefix="### ", defs=defs)
            lines.append(doc)
            all_errors.extend(errors)
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    # Write to file
    output_path = repo_root / "SETTINGS.md"
    content = "\n".join(lines)
    output_path.write_text(content)
    
    print(f"Documentation saved to: {output_path}")
    print(f"Generated {len(lines)} lines of documentation")
    print(f"Documented {len(schema.get('properties', {}))} top-level fields")
    print(f"Documented {len(defs)} nested models")
    print(f"Organized into {len(grouped_models)} groups")
    
    # Report validation errors
    if all_errors:
        print(f"\n⚠️ WARNING: Found {len(all_errors)} validation errors:\n")
        for error in all_errors:
            print(f"  {error}")
        print("\n💡 Add Field(description='...') to fix these errors")
        sys.exit(1)
    
    print("\n✅ Documentation and schema generation complete!")
    print()
    print("Generated files:")
    print(f"  - 📄 {schema_path.name} - JSON Schema for IDE autocomplete and validation")
    print(f"  - 📄 {output_path.name} - User-friendly markdown documentation")
    sys.exit(0)


if __name__ == "__main__":
    main()
