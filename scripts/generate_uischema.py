#!/usr/bin/env python3
"""
Generate UISchema from Pydantic models with embedded UI metadata.

Extracts x-ui-* properties from Field json_schema_extra and generates
a complete JSONForms UISchema with proper grouping, ordering, and controls.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Any, Dict, Tuple
from collections import defaultdict
import subprocess

# Global flag for quiet mode
QUIET = False


def flatten_optional_anyof(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten Optional-style anyOf patterns to avoid JSONForms combinator rendering.
    
    Converts: {"anyOf": [{"$ref": "#/$defs/Model"}, {"type": "null"}]}
    To: {"$ref": "#/$defs/Model"} (and ensures field is not in required array)
    
    This prevents JSONForms from showing ANYOF-1/ANYOF-2 tabs for optional fields.
    Only flattens simple Optional patterns (Model | null), not complex unions.
    """
    if isinstance(schema, dict):
        # Check if this is a simple Optional pattern: anyOf with exactly 2 items,
        # one being a $ref or simple type, the other being null
        if "anyOf" in schema and isinstance(schema["anyOf"], list) and len(schema["anyOf"]) == 2:
            has_null = False
            non_null_item = None
            
            for item in schema["anyOf"]:
                if isinstance(item, dict) and item.get("type") == "null":
                    has_null = True
                elif isinstance(item, dict):
                    non_null_item = item
            
            # If we have exactly one null and one non-null, flatten it
            if has_null and non_null_item is not None:
                # Replace anyOf with the non-null item
                del schema["anyOf"]
                # Copy all properties from non_null_item to schema
                for key, value in non_null_item.items():
                    if key not in schema:  # Don't overwrite existing keys like 'default', 'description'
                        schema[key] = value
        
        # Recursively process nested objects and arrays
        for key, value in schema.items():
            if isinstance(value, dict):
                schema[key] = flatten_optional_anyof(value)
            elif isinstance(value, list):
                schema[key] = [flatten_optional_anyof(item) if isinstance(item, dict) else item for item in value]
    
    return schema


def resolve_ref(ref: str, defs: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a $ref pointer to its definition."""
    if ref.startswith("#/$defs/"):
        def_name = ref.replace("#/$defs/", "")
        return defs.get(def_name, {})
    return {}


def rewrite_rule_scopes(rule: Any, parent_prop_path: str) -> Any:
    """
    Recursively rewrite scope paths in x-ui-rules for nested properties.
    
    When a model is nested (e.g., database_ha), its x-ui-rules contain relative
    scope paths like "#/properties/engine". These need to be rewritten to absolute
    paths like "#/properties/database_ha/properties/engine" for JSONForms to find them.
    
    Args:
        rule: The x-ui-rules structure (can be dict, list, or primitive)
        parent_prop_path: The parent property path (e.g., "database_ha")
    
    Returns:
        The rule structure with rewritten scope paths
    """
    if isinstance(rule, dict):
        result = {}
        for key, value in rule.items():
            if key == "scope" and isinstance(value, str) and value.startswith("#/properties/"):
                # Rewrite the scope path to include the parent property
                # "#/properties/engine" -> "#/properties/database_ha/properties/engine"
                prop_path = value.replace("#/properties/", "")
                result[key] = f"#/properties/{parent_prop_path}/properties/{prop_path}"
            else:
                # Recursively process nested structures
                result[key] = rewrite_rule_scopes(value, parent_prop_path)
        return result
    elif isinstance(rule, list):
        return [rewrite_rule_scopes(item, parent_prop_path) for item in rule]
    else:
        # Primitive value, return as-is
        return rule


def extract_x_ui_group_from_property(prop_schema: Dict[str, Any], defs: Dict[str, Any]) -> Tuple[str, int]:
    """
    Extract x-ui-group and x-order from a property schema.
    
    Cascade priority for x-ui-group (highest to lowest):
    1. Field-level x-ui-group (in property schema)
    2. Model-level x-ui-group (in model's json_schema_extra)
    3. Parent model-level x-ui-group (recursive up the hierarchy)
    4. Default to "General"
    
    For x-order: field-level first, then model-level, default to 999
    """
    group = None
    order = None
    
    # 1. Check field-level x-ui-group and x-order (highest priority)
    if "x-ui-group" in prop_schema:
        group = prop_schema["x-ui-group"]
    if "x-order" in prop_schema:
        order = prop_schema["x-order"]
    
    # If group found at field level, return early
    if group is not None:
        return group, order if order is not None else 999
    
    # 2. Check model-level and parent hierarchy for x-ui-group and x-order
    resolved_model = None
    
    # Check in $ref
    if "$ref" in prop_schema:
        resolved_model = resolve_ref(prop_schema["$ref"], defs)
    
    # Check in anyOf options (for Optional types)
    elif "anyOf" in prop_schema:
        for option in prop_schema["anyOf"]:
            # Skip null types
            if isinstance(option, dict) and option.get("type") == "null":
                continue
            # Check if this option has a $ref
            if isinstance(option, dict) and "$ref" in option:
                resolved_model = resolve_ref(option["$ref"], defs)
                break
    
    # Check in oneOf options (for discriminated unions)
    elif "oneOf" in prop_schema:
        for option in prop_schema["oneOf"]:
            # Check if this option has a $ref
            if isinstance(option, dict) and "$ref" in option:
                resolved_model = resolve_ref(option["$ref"], defs)
                # For discriminated unions, use the first variant's metadata
                break
    
    # Check in array items
    elif prop_schema.get("type") == "array" and "items" in prop_schema:
        items = prop_schema["items"]
        if "$ref" in items:
            resolved_model = resolve_ref(items["$ref"], defs)
    
    # Extract group and order from model hierarchy
    if resolved_model is not None:
        # Check model-level x-ui-group
        if group is None and "x-ui-group" in resolved_model:
            group = resolved_model["x-ui-group"]
        
        # Check model-level x-order
        if order is None and "x-order" in resolved_model:
            order = resolved_model["x-order"]
    
    # Fallback defaults
    if group is None:
        group = "General"
    if order is None:
        order = 999
    
    return group, order


def validate_entity_id_filters(schema: Dict[str, Any], defs: Dict[str, Any]) -> None:
    """
    Validate that all EntityId fields have x-ui-widget-filter defined.
    
    Detects EntityId fields by checking $ref to #/$defs/EntityId.
    This is cleaner than checking x-ui-widget values.
    
    Raises ValueError if any EntityId field is missing the filter property.
    """
    violations = []
    
    def check_property(prop_name: str, prop_schema: Dict[str, Any], path: str = "") -> None:
        """Recursively check a property and its nested properties."""
        full_path = f"{path}.{prop_name}" if path else prop_name
        
        # Check if $ref points to EntityId
        if "$ref" in prop_schema:
            ref = prop_schema["$ref"]
            if ref.endswith("/EntityId"):
                # Single EntityId field
                if "x-ui-widget-filter" not in prop_schema:
                    violations.append(f"{full_path} (EntityId)")
            
            # Recursively check nested properties in resolved definition
            resolved = resolve_ref(ref, defs)
            if "properties" in resolved:
                for nested_name, nested_schema in resolved["properties"].items():
                    check_property(nested_name, nested_schema, full_path)
        
        # Check array items for list[EntityId]
        if prop_schema.get("type") == "array" and "items" in prop_schema:
            items = prop_schema["items"]
            if "$ref" in items:
                ref = items["$ref"]
                if ref.endswith("/EntityId"):
                    # List of EntityId fields
                    if "x-ui-widget-filter" not in prop_schema:
                        violations.append(f"{full_path}[] (list[EntityId])")
                
                # Recursively check nested properties in array item definition
                resolved = resolve_ref(ref, defs)
                if "properties" in resolved:
                    for nested_name, nested_schema in resolved["properties"].items():
                        check_property(nested_name, nested_schema, f"{full_path}[]")
        
        # Check in anyOf options (for Optional[EntityId])
        if "anyOf" in prop_schema:
            for option in prop_schema["anyOf"]:
                if isinstance(option, dict) and option.get("type") != "null":
                    if "$ref" in option:
                        ref = option["$ref"]
                        if ref.endswith("/EntityId"):
                            if "x-ui-widget-filter" not in prop_schema:
                                violations.append(f"{full_path} (Optional[EntityId])")
                        
                        # Recursively check nested properties
                        resolved = resolve_ref(ref, defs)
                        if "properties" in resolved:
                            for nested_name, nested_schema in resolved["properties"].items():
                                check_property(nested_name, nested_schema, full_path)
        
        # Recursively check properties in inline objects
        if "properties" in prop_schema:
            for nested_name, nested_schema in prop_schema["properties"].items():
                check_property(nested_name, nested_schema, full_path)
    
    # Check all root properties
    properties = schema.get("properties", {})
    for prop_name, prop_schema in properties.items():
        check_property(prop_name, prop_schema)
    
    if violations:
        error_msg = (
            "❌ EntityId fields missing x-ui-widget-filter:\n" +
            "\n".join(f"  - {v}" for v in violations) +
            "\n\nAll EntityId fields must have x-ui-widget-filter defined for domain filtering."
        )
        raise ValueError(error_msg)


def generate_uischema_for_property(prop_name: str, prop_schema: Dict[str, Any], defs: Dict[str, Any], source_class: str = None) -> Dict[str, Any] | list[Dict[str, Any]]:
    """
    Generate UISchema element(s) for a single property from the root schema.
    
    Handles objects, arrays, anyOf (complex unions), $refs, and primitive types.
    
    For arrays with help text, returns a list: [HelpButton, Control]
    Otherwise returns a single Control dict.
    
    Args:
        prop_name: Property name
        prop_schema: Property JSON schema
        defs: Schema definitions
        source_class: Python class name for source tracking (e.g., "PricingConfig")
    """
    scope = f"#/properties/{prop_name}"
    
    # Extract options from the property
    options = {}
    if "x-help" in prop_schema:
        options["help"] = prop_schema["x-help"]
    if "description" in prop_schema:
        options["description"] = prop_schema["description"]
    if "x-unit" in prop_schema:
        options["unit"] = prop_schema["x-unit"]
    if "x-ui-widget" in prop_schema:
        options["widget"] = prop_schema["x-ui-widget"]
    if "x-ui-widget-filter" in prop_schema:
        options["widgetFilter"] = prop_schema["x-ui-widget-filter"]
    if "x-docs-url" in prop_schema:
        options["docsUrl"] = prop_schema["x-docs-url"]
    if "x-enum-values" in prop_schema:
        options["enumValues"] = prop_schema["x-enum-values"]  # For FlexEnum
    
    # Preserve $ref type information for renderer detection
    # This survives $ref resolution and allows testers to identify custom types
    if "$ref" in prop_schema:
        ref_type = prop_schema["$ref"].split("/")[-1]  # Extract type name from $ref path
        options["refType"] = ref_type  # e.g., "EntityId", "FlexInt", "SecretStr", "FlexEnum"
    
    # Add source location for debugging
    if source_class:
        options["x-source"] = f"{source_class}.{prop_name}"
    
    # Extract rule from x-ui-rules
    rule = None
    if "x-ui-rules" in prop_schema:
        rule = prop_schema["x-ui-rules"]
    
    # For direct $ref (flattened Optional types), extract metadata from definition
    if "$ref" in prop_schema:
        resolved = resolve_ref(prop_schema["$ref"], defs)
        if "x-help" in resolved and "help" not in options:
            options["help"] = resolved.get("x-help")
        if "description" in resolved and "description" not in options:
            options["description"] = resolved.get("description")
        if "x-unit" in resolved and "unit" not in options:
            options["unit"] = resolved.get("x-unit")
        if "x-ui-widget" in resolved and "widget" not in options:
            options["widget"] = resolved.get("x-ui-widget")
        if "x-ui-widget-filter" in resolved and "widgetFilter" not in options:
            options["widgetFilter"] = resolved.get("x-ui-widget-filter")
        if "x-ui-rules" in resolved and rule is None:
            rule = resolved.get("x-ui-rules")
        
        # Generate detail UISchema for nested objects (like HADatabaseConfig)
        if "properties" in resolved:
            # Extract source class from resolved definition
            nested_class = resolved.get("title", prop_name)
            detail_elements = generate_detail_uischema(resolved, defs, nested_class)
            if detail_elements:
                options["detail"] = {
                    "type": "VerticalLayout",
                    "elements": detail_elements
                }
    
    # For arrays, check items definition for metadata AND generate detail UISchema
    if prop_schema.get("type") == "array":
        if "items" in prop_schema and "$ref" in prop_schema["items"]:
            # Preserve array item $ref type for renderer detection
            items_ref_type = prop_schema["items"]["$ref"].split("/")[-1]
            options["itemsRefType"] = items_ref_type  # e.g., "EntityId" for list[EntityId]
            
            resolved = resolve_ref(prop_schema["items"]["$ref"], defs)
            # Extract all relevant metadata from the array item model
            if "x-help" in resolved and "help" not in options:
                options["help"] = resolved.get("x-help")
            if "description" in resolved and "description" not in options:
                options["description"] = resolved.get("description")
            if "title" in resolved and "title" not in options:
                options["title"] = resolved.get("title")
            if "x-docs-url" in resolved and "docsUrl" not in options:
                options["docsUrl"] = resolved.get("x-docs-url")
            
            # Generate detail UISchema for array items
            nested_class = resolved.get("title", prop_name)
            detail_elements = generate_detail_uischema(resolved, defs, nested_class)
            if detail_elements:
                options["detail"] = {
                    "type": "VerticalLayout",
                    "elements": detail_elements
                }
    
    # For anyOf (complex unions that weren't flattened), check inside for metadata
    if "anyOf" in prop_schema:
        for option_item in prop_schema["anyOf"]:
            # Skip null types
            if isinstance(option_item, dict) and option_item.get("type") == "null":
                continue
            # Check if this option has a $ref - resolve it for metadata
            if isinstance(option_item, dict) and "$ref" in option_item:
                resolved = resolve_ref(option_item["$ref"], defs)
                # Extract metadata from resolved definition if not already present
                if "x-help" in resolved and "help" not in options:
                    options["help"] = resolved.get("x-help")
                if "description" in resolved and "description" not in options:
                    options["description"] = resolved.get("description")
                if "x-unit" in resolved and "unit" not in options:
                    options["unit"] = resolved.get("x-unit")
                if "x-ui-widget" in resolved and "widget" not in options:
                    options["widget"] = resolved.get("x-ui-widget")
                if "x-ui-widget-filter" in resolved and "widgetFilter" not in options:
                    options["widgetFilter"] = resolved.get("x-ui-widget-filter")
                if "x-ui-rules" in resolved and rule is None:
                    rule = resolved.get("x-ui-rules")
                # Found the main type, stop looking
                break
    
    control = {
        "type": "Control",
        "scope": scope,
        "options": options if options else {}
    }
    
    # Add rule if present
    if rule:
        control["rule"] = rule
    
    # For arrays with help text, return a list with HelpButton + Control
    # This matches the pattern used for nested objects
    if prop_schema.get("type") == "array" and "help" in options:
        help_text = options["help"]
        # Remove help from control options since we're showing it as a button
        del options["help"]
        
        help_button = {
            "type": "HelpButton",
            "options": {
                "helpText": help_text,
                "helpTitle": "Help"
            }
        }
        
        # Add docsUrl if present
        if "docsUrl" in options:
            help_button["options"]["docsUrl"] = options["docsUrl"]
        
        return [help_button, control]
    
    return control


def extract_section_info(prop_schema: Dict[str, Any], defs: Dict[str, Any], use_general_default: bool = False) -> Tuple[str, Any]:
    """
    Extract x-ui-section and x-ui-collapse from a property schema.
    
    Cascade priority (highest to lowest):
    1. Field-level x-ui-section (in property schema)
    2. Model-level x-ui-section (in model's json_schema_extra)
    3. Parent model-level x-ui-section (recursive up the hierarchy)
    4. Model class name (title field) OR "General" if use_general_default=True
    
    Args:
        prop_schema: Property schema to extract from
        defs: Schema definitions
        use_general_default: If True, default to "General" instead of model class name (for detail views)
    
    Returns (section_name, collapse_state) where collapse_state is:
    - None: not collapsible
    - True: collapsible and collapsed by default
    - False: collapsible and expanded by default
    """
    section = None
    collapse = None
    
    # 1. Check field-level x-ui-section (highest priority)
    if "x-ui-section" in prop_schema:
        section = prop_schema["x-ui-section"]
    if "x-ui-collapse" in prop_schema:
        collapse = prop_schema["x-ui-collapse"]
    
    # If section found at field level, return early
    if section is not None:
        return section, collapse
    
    # 2. Check model-level and parent hierarchy for x-ui-section
    resolved_model = None
    
    # Check in $ref
    if "$ref" in prop_schema:
        resolved_model = resolve_ref(prop_schema["$ref"], defs)
    
    # Check in anyOf options (for Optional types)
    elif "anyOf" in prop_schema:
        for option in prop_schema["anyOf"]:
            if isinstance(option, dict) and option.get("type") != "null":
                if "$ref" in option:
                    resolved_model = resolve_ref(option["$ref"], defs)
                    break
    
    # Extract section from model hierarchy
    if resolved_model is not None:
        # Check model-level x-ui-section
        if "x-ui-section" in resolved_model:
            section = resolved_model["x-ui-section"]
        
        # Check model-level x-ui-collapse
        if collapse is None and "x-ui-collapse" in resolved_model:
            collapse = resolved_model["x-ui-collapse"]
        
        # If not found, use model class name (title) as default, or "General" if requested
        if section is None:
            if use_general_default:
                section = "General"
            else:
                section = resolved_model.get("title", "General")
    
    # Fallback to "General" if nothing found
    if section is None:
        section = "General"
    
    return section, collapse


def group_controls_by_section(controls_with_meta: list, model_help: str = None, model_docs_url: str = None) -> list:
    """
    Group controls by x-ui-section and create Group layouts.
    
    Args:
        controls_with_meta: List of (control_dict, section_name, collapse_state, order) tuples
        model_help: Optional model-level help text to prepend to first section
        model_docs_url: Optional model-level documentation URL to include with help
    
    Returns:
        List of Group elements or flat Control elements if only one section
    """
    # Group controls by section with order
    sections = defaultdict(lambda: {"controls": [], "collapse": None, "min_order": 999})
    
    for control, section_name, collapse_state, order in controls_with_meta:
        sections[section_name]["controls"].append((control, order))
        # Track the minimum order value for section ordering
        if order < sections[section_name]["min_order"]:
            sections[section_name]["min_order"] = order
        # Use the first non-None collapse state found for this section
        if sections[section_name]["collapse"] is None and collapse_state is not None:
            sections[section_name]["collapse"] = collapse_state
    
    # If only one section and it's "General", return flat controls
    if len(sections) == 1 and "General" in sections:
        # Sort by order and extract just the controls (not the order values)
        sorted_controls = sorted(sections["General"]["controls"], key=lambda x: x[1])
        return [control for control, order in sorted_controls]
    
    # Create Group elements for each section
    elements = []
    # Sort sections by their minimum order value, then alphabetically
    section_names = sorted(sections.keys(), key=lambda name: (sections[name]["min_order"], name))
    
    for idx, section_name in enumerate(section_names):
        section_data = sections[section_name]
        section_elements = []
        
        # Add model-level help as a HelpButton in first section
        if idx == 0 and model_help:
            help_button = {
                "type": "HelpButton",
                "options": {
                    "helpText": model_help,
                    "helpTitle": "Help"
                }
            }
            # Add docsUrl if present
            if model_docs_url:
                help_button["options"]["docsUrl"] = model_docs_url
            section_elements.append(help_button)
        
        # Sort controls by order and add to section
        sorted_controls = sorted(section_data["controls"], key=lambda x: x[1])
        section_elements.extend([control for control, order in sorted_controls])
        
        group = {
            "type": "Group",
            "label": section_name,
            "elements": section_elements
        }
        
        # Add collapsible options if x-ui-collapse was specified
        if section_data["collapse"] is not None:
            group["options"] = {
                "collapsed": section_data["collapse"]
            }
        
        elements.append(group)
    
    return elements


def generate_detail_uischema(item_def: Dict[str, Any], defs: Dict[str, Any], source_class: str = None) -> list:
    """
    Generate UISchema elements for properties within an array item or nested object.
    
    Extracts x-* extensions, creates Control elements with proper options,
    and groups them by x-ui-section into Group layouts.
    
    If the item_def has x-help at root level, adds a collapsible Help section at the bottom.
    
    Args:
        item_def: Item definition with properties
        defs: Schema definitions
        source_class: Python class name for source tracking
    """
    if "properties" not in item_def:
        return []
    
    elements = []
    
    # Collect all controls with their section information
    controls_with_meta = []
    
    for prop_name, prop_schema in item_def["properties"].items():
        # Extract section information (use "General" as default instead of model class name)
        section_name, collapse_state = extract_section_info(prop_schema, defs, use_general_default=True)
        
        # Extract order (default to 999 if not specified)
        order = prop_schema.get("x-order", 999)
        
        # Extract options from the property
        options = {}
        rule = None
        
        # Check direct properties first
        for x_key, option_key in [
            ("x-help", "help"),
            ("description", "description"),
            ("x-unit", "unit"),
            ("x-ui-widget", "widget"),
            ("x-ui-widget-filter", "widgetFilter"),
            ("x-validation-hint", "validationHint"),
            ("x-enum-values", "enumValues")  # For FlexEnum
        ]:
            if x_key in prop_schema:
                options[option_key] = prop_schema[x_key]
        
        if "x-ui-rules" in prop_schema:
            rule = prop_schema["x-ui-rules"]
        
        # For $ref, resolve and extract metadata
        if "$ref" in prop_schema:
            # Preserve $ref type information for renderer detection
            ref_type = prop_schema["$ref"].split("/")[-1]
            options["refType"] = ref_type  # e.g., "EntityId", "FlexInt", "SecretStr"
            
            resolved = resolve_ref(prop_schema["$ref"], defs)
            # Extract order from resolved if not in prop_schema
            if order == 999 and "x-order" in resolved:
                order = resolved["x-order"]
            
            for x_key, option_key in [
                ("x-help", "help"),
                ("description", "description"),
                ("x-unit", "unit"),
                ("x-ui-widget", "widget"),
                ("x-ui-widget-filter", "widgetFilter"),
                ("x-validation-hint", "validationHint"),
                ("x-enum-values", "enumValues")  # For FlexEnum
            ]:
                if x_key in resolved and option_key not in options:
                    options[option_key] = resolved[x_key]
            
            if "x-ui-rules" in resolved and rule is None:
                rule = resolved["x-ui-rules"]
        
        # For anyOf, check options for metadata
        if "anyOf" in prop_schema:
            for option_item in prop_schema["anyOf"]:
                if isinstance(option_item, dict) and option_item.get("type") != "null":
                    if "$ref" in option_item:
                        # Preserve $ref type information
                        ref_type = option_item["$ref"].split("/")[-1]
                        options["refType"] = ref_type
                        
                        resolved = resolve_ref(option_item["$ref"], defs)
                        # Extract order from resolved if not set
                        if order == 999 and "x-order" in resolved:
                            order = resolved["x-order"]
                        
                        for x_key, option_key in [
                            ("x-help", "help"),
                            ("description", "description"),
                            ("x-unit", "unit"),
                            ("x-ui-widget", "widget"),
                            ("x-ui-widget-filter", "widgetFilter"),
                            ("x-validation-hint", "validationHint"),
                            ("x-enum-values", "enumValues")  # For FlexEnum
                        ]:
                            if x_key in resolved and option_key not in options:
                                options[option_key] = resolved[x_key]
                        
                        if "x-ui-rules" in resolved and rule is None:
                            rule = resolved["x-ui-rules"]
                        break
        
        control = {
            "type": "Control",
            "scope": f"#/properties/{prop_name}",
            "options": options if options else {}
        }
        
        # Add source location for debugging
        if source_class:
            control["options"]["x-source"] = f"{source_class}.{prop_name}"
        
        # Add rule if present
        if rule:
            control["rule"] = rule
        
        controls_with_meta.append((control, section_name, collapse_state, order))
    
    # Extract model-level help and docsUrl if present
    model_help = item_def.get("x-help")
    model_docs_url = item_def.get("x-docs-url")
    
    # Group controls by section and create Group layouts, passing model help and docsUrl
    grouped_controls = group_controls_by_section(controls_with_meta, model_help, model_docs_url)
    elements.extend(grouped_controls)
    
    return elements


def validate_uischema(uischema: Dict[str, Any]) -> None:
    """
    Validate the generated UISchema using TypeScript type checking.
    
    This validates against JSONForms' official TypeScript type definitions,
    ensuring type safety and automatic sync with JSONForms updates.
    
    Prerequisites: Run 'source activate.sh' before running this script
    Uses: pnpm run validate-uischema (tsc --noEmit validate-uischema.ts)
    
    Args:
        uischema: The generated UISchema (already written to file)
        
    Raises:
        RuntimeError: If TypeScript validation fails
    """
    # Use the new frontend directory (not config-gui-poc which will be removed)
    project_root = Path(__file__).parent.parent
    frontend_dir = project_root / "dao" / "frontend"
    
    try:
        # Run TypeScript validation using pnpm
        result = subprocess.run(
            ["pnpm", "run", "validate-uischema"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            if not QUIET:
                print("✅ UISchema TypeScript validation passed")
        else:
            print("\n❌ UISchema TypeScript Validation Failed:")
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            sys.exit(1)
            
    except subprocess.TimeoutExpired:
        print("⚠️  TypeScript validation timed out")
        sys.exit(1)
    except FileNotFoundError:
        if not QUIET:
            print("⚠️  pnpm not found - install it with: npm install -g pnpm")
        return


def main(output_dir: str = None):
    """Generate UISchema and JSON Schema from ConfigurationV0 root model.
    
    Args:
        output_dir: Directory to write schema files. Defaults to dao/webserver/app/static/schemas/
    """
    # Import root configuration model - add dao/prog to sys.path
    project_root = Path(__file__).parent.parent
    prog_path = project_root / "dao" / "prog"
    sys.path.insert(0, str(prog_path))
    from config.versions.v0 import ConfigurationV0
    
    # Set default output directory
    if output_dir is None:
        project_root = Path(__file__).parent.parent
        output_dir = str(project_root / "dao" / "webserver" / "app" / "static" / "schemas")
    
    output_path = Path(output_dir)
    
    if not QUIET:
        print("Generating schema from ConfigurationV0...")
    
    # Generate JSON Schema from root model
    # Use by_alias=False to get Python field names (with underscores) instead of aliases
    schema = ConfigurationV0.model_json_schema(mode='serialization', by_alias=False)
    
    # Flatten Optional-style anyOf to prevent ANYOF tabs in JSONForms
    schema = flatten_optional_anyof(schema)
    
    # Get properties and definitions
    properties = schema.get("properties", {})
    defs = schema.get("$defs", {})
    
    if not QUIET:
        print(f"Found {len(properties)} root properties")
        print(f"Found {len(defs)} definitions")
    
    # Validate EntityId fields have filters defined
    if not QUIET:
        print("\nValidating EntityId fields...")
    validate_entity_id_filters(schema, defs)
    if not QUIET:
        print("✅ All EntityId fields have filters")
    
    # Group properties by x-ui-group
    # Structure: {group_name: [(order, prop_name, prop_schema, source_class, parent_prop_name, parent_section)]}
    # parent_prop_name is None for root properties, or the root property name for nested fields
    # parent_section is None for root properties, or the parent model's x-ui-section for nested fields
    groups = defaultdict(list)
    
    for prop_name, prop_schema in properties.items():
        # Skip const fields (non-configurable like config_version)
        if "const" in prop_schema:
            continue
        
        # Extract source class name from $ref if present
        source_class = None
        resolved_model = None
        is_union_type = False
        
        if "$ref" in prop_schema:
            ref_name = prop_schema["$ref"].split("/")[-1]
            ref_def = defs.get(ref_name, {})
            source_class = ref_def.get("title", ref_name)
            resolved_model = ref_def
        elif "anyOf" in prop_schema:
            # Union types (like str | SecretStr) should NOT be expanded
            # They should be rendered as a single control
            is_union_type = True
            for option in prop_schema["anyOf"]:
                if isinstance(option, dict) and option.get("type") != "null" and "$ref" in option:
                    ref_name = option["$ref"].split("/")[-1]
                    ref_def = defs.get(ref_name, {})
                    source_class = ref_def.get("title", ref_name)
                    # Don't set resolved_model for union types - prevents expansion
                    break
        elif "oneOf" in prop_schema:
            # For discriminated unions with boolean discriminators, expand the "True" variant
            # This treats it like a regular nested object, eliminating special handling
            discriminator = prop_schema.get("discriminator", {})
            discriminator_prop = discriminator.get("propertyName")
            
            if discriminator_prop:
                # Find the variant where discriminator = True
                for option in prop_schema["oneOf"]:
                    if isinstance(option, dict) and "$ref" in option:
                        ref_name = option["$ref"].split("/")[-1]
                        ref_def = defs.get(ref_name, {})
                        disc_prop_schema = ref_def.get("properties", {}).get(discriminator_prop, {})
                        
                        # Check if this is the "enabled" variant (const: true)
                        if disc_prop_schema.get("const") == True:
                            source_class = ref_def.get("title", ref_name)
                            resolved_model = ref_def
                            # NOT a union type - we want to expand it
                            is_union_type = False
                            break
                        # If this is the "disabled" variant, still get source_class but mark as union
                        elif disc_prop_schema.get("const") == False:
                            if source_class is None:  # Only set if we haven't found True variant
                                source_class = ref_def.get("title", ref_name)
                            is_union_type = True
            else:
                # oneOf without discriminator - treat as union type
                is_union_type = True
                for option in prop_schema["oneOf"]:
                    if isinstance(option, dict) and "$ref" in option:
                        ref_name = option["$ref"].split("/")[-1]
                        ref_def = defs.get(ref_name, {})
                        source_class = ref_def.get("title", ref_name)
                        break
        
        # Check if this is a nested object that should be expanded
        # Skip union types (anyOf, oneOf) - they should be rendered as single controls
        if resolved_model and "properties" in resolved_model and not is_union_type:
            # This is a nested object - expand its fields and add them to groups
            nested_class = resolved_model.get("title", prop_name)
            parent_group = resolved_model.get("x-ui-group", None)
            parent_section = resolved_model.get("x-ui-section", None)
            
            for nested_prop_name, nested_prop_schema in resolved_model["properties"].items():
                # Extract group for the nested field
                nested_group, nested_order = extract_x_ui_group_from_property(nested_prop_schema, defs)
                
                # If still "General", use parent model's x-ui-group if available
                if nested_group == "General" and parent_group:
                    nested_group = parent_group
                
                # Add to groups with parent property name and section for scope construction and section cascade
                groups[nested_group].append((nested_order, nested_prop_name, nested_prop_schema, nested_class, prop_name, parent_section))
                if not QUIET:
                    print(f"  {prop_name}.{nested_prop_name} -> {nested_group} (order: {nested_order})")
        else:
            # Regular property - add to groups
            group, order = extract_x_ui_group_from_property(prop_schema, defs)
            groups[group].append((order, prop_name, prop_schema, source_class, None, None))
            if not QUIET:
                print(f"  {prop_name} -> {group} (order: {order})")
    
    # Extract category-level metadata (icon, docsUrl) from models
    # Structure: {group_name: {'icon': '...', 'docsUrl': '...'}}
    category_metadata = {}
    
    for group_name, props_list in groups.items():
        # Sort by order to prioritize lower-order items for metadata extraction
        props_list.sort(key=lambda x: x[0])
        
        # Find the first model in this group that defines x-icon or x-docs-url
        for order, prop_name, prop_schema, source_class, parent_prop_name, parent_section in props_list:
            # Try to resolve the model definition
            resolved_model = None
            
            if "$ref" in prop_schema:
                resolved_model = resolve_ref(prop_schema["$ref"], defs)
            elif "anyOf" in prop_schema:
                for option in prop_schema["anyOf"]:
                    if isinstance(option, dict) and option.get("type") != "null" and "$ref" in option:
                        resolved_model = resolve_ref(option["$ref"], defs)
                        break
            elif "oneOf" in prop_schema:
                for option in prop_schema["oneOf"]:
                    if isinstance(option, dict) and "$ref" in option:
                        resolved_model = resolve_ref(option["$ref"], defs)
                        # For discriminated unions, use first variant's metadata
                        break
            elif prop_schema.get("type") == "array" and "items" in prop_schema and "$ref" in prop_schema["items"]:
                resolved_model = resolve_ref(prop_schema["items"]["$ref"], defs)
            
            # Check if this model defines x-ui-group and matches our group_name
            if resolved_model and resolved_model.get("x-ui-group") == group_name:
                metadata = {}
                if "x-docs-url" in resolved_model:
                    metadata["docsUrl"] = resolved_model["x-docs-url"]
                
                # Only store if we found metadata
                if metadata:
                    category_metadata[group_name] = metadata
                    if not QUIET:
                        print(f"Category '{group_name}' metadata: {metadata}")
                    break  # Use the first model that defines metadata for this group
    
    # Generate UISchema with Categorization (tabs)
    # Define fixed order for predefined tabs
    FIXED_TAB_ORDER = ["DAO", "HASS"]
    
    categories = []
    
    # First, add predefined tabs in fixed order (if they exist)
    for group_name in FIXED_TAB_ORDER:
        if group_name in groups:
            props_list = groups[group_name]
            # Sort properties within group by order
            props_list.sort(key=lambda x: x[0])
            
            # Collect controls with their section information
            controls_with_meta = []
            for order, prop_name, prop_schema, source_class, parent_prop_name, parent_section in props_list:
                # If parent_prop_name is set, this is a nested field - generate control directly
                if parent_prop_name:
                    # Generate control for nested field
                    scope = f"#/properties/{parent_prop_name}/properties/{prop_name}"
                    control = {"type": "Control", "scope": scope, "options": {}}
                    
                    # Extract metadata
                    if "x-help" in prop_schema:
                        control["options"]["help"] = prop_schema["x-help"]
                    if "description" in prop_schema:
                        control["options"]["description"] = prop_schema["description"]
                    if "x-unit" in prop_schema:
                        control["options"]["unit"] = prop_schema["x-unit"]
                    if "x-ui-widget" in prop_schema:
                        control["options"]["widget"] = prop_schema["x-ui-widget"]
                    if "x-ui-widget-filter" in prop_schema:
                        control["options"]["widgetFilter"] = prop_schema["x-ui-widget-filter"]
                    if "x-validation-hint" in prop_schema:
                        control["options"]["validationHint"] = prop_schema["x-validation-hint"]
                    
                    # Add refType for $ref properties (for custom renderer detection)
                    if "$ref" in prop_schema:
                        ref_type = prop_schema["$ref"].split("/")[-1]
                        control["options"]["refType"] = ref_type
                    
                    # Add itemsRefType for array properties (for EntityListPicker detection)
                    if prop_schema.get("type") == "array" and "items" in prop_schema and "$ref" in prop_schema["items"]:
                        items_ref_type = prop_schema["items"]["$ref"].split("/")[-1]
                        control["options"]["itemsRefType"] = items_ref_type
                    
                    # Add source tracking
                    control["options"]["x-source"] = f"{source_class}.{prop_name}"
                    
                    # Add rule if present - rewrite scope paths for nested properties
                    if "x-ui-rules" in prop_schema:
                        control["rule"] = rewrite_rule_scopes(prop_schema["x-ui-rules"], parent_prop_name)
                    
                    # Extract section for nested field
                    section_name, collapse_state = extract_section_info(prop_schema, defs, use_general_default=False)
                    # If still "General", use parent model's x-ui-section if available
                    if section_name == "General" and parent_section:
                        section_name = parent_section
                    
                    controls_with_meta.append((control, section_name, collapse_state, order))
                else:
                    # Regular field - generate control normally
                    section_name, collapse_state = extract_section_info(prop_schema, defs)
                    element = generate_uischema_for_property(prop_name, prop_schema, defs, source_class)
                    # Handle both single elements and lists (arrays with help text return [HelpButton, Control])
                    if isinstance(element, list):
                        for elem in element:
                            controls_with_meta.append((elem, section_name, collapse_state, order))
                    else:
                        controls_with_meta.append((element, section_name, collapse_state, order))
            
            # Group controls by section and create Group layouts
            group_elements = group_controls_by_section(controls_with_meta)
            
            # Build category object
            category = {
                "type": "Category",
                "label": group_name,
                "elements": group_elements
            }
            
            # Add metadata if available
            if group_name in category_metadata:
                category["options"] = category_metadata[group_name]
            
            categories.append(category)
    
    # Then, add remaining groups in sorted order
    remaining_groups = sorted(set(groups.keys()) - set(FIXED_TAB_ORDER))
    for group_name in remaining_groups:
        props_list = groups[group_name]
        # Sort properties within group by order
        props_list.sort(key=lambda x: x[0])
        
        # Collect controls with their section information
        controls_with_meta = []
        for order, prop_name, prop_schema, source_class, parent_prop_name, parent_section in props_list:
            # If parent_prop_name is set, this is a nested field - generate control directly
            if parent_prop_name:
                # Generate control for nested field
                scope = f"#/properties/{parent_prop_name}/properties/{prop_name}"
                control = {"type": "Control", "scope": scope, "options": {}}
                
                # Extract metadata
                if "x-help" in prop_schema:
                    control["options"]["help"] = prop_schema["x-help"]
                if "description" in prop_schema:
                    control["options"]["description"] = prop_schema["description"]
                if "x-unit" in prop_schema:
                    control["options"]["unit"] = prop_schema["x-unit"]
                if "x-ui-widget" in prop_schema:
                    control["options"]["widget"] = prop_schema["x-ui-widget"]
                if "x-ui-widget-filter" in prop_schema:
                    control["options"]["widgetFilter"] = prop_schema["x-ui-widget-filter"]
                if "x-validation-hint" in prop_schema:
                    control["options"]["validationHint"] = prop_schema["x-validation-hint"]
                
                # Check if this is a discriminator field (has const: true/false)
                # These should render as toggle switches, not text fields
                if "const" in prop_schema and isinstance(prop_schema["const"], bool):
                    control["options"]["format"] = "boolean"
                    control["options"]["toggle"] = True
                
                # Add refType for $ref properties (for custom renderer detection)
                if "$ref" in prop_schema:
                    ref_type = prop_schema["$ref"].split("/")[-1]
                    control["options"]["refType"] = ref_type
                
                # Add itemsRefType for array properties (for EntityListPicker detection)
                if prop_schema.get("type") == "array" and "items" in prop_schema and "$ref" in prop_schema["items"]:
                    items_ref_type = prop_schema["items"]["$ref"].split("/")[-1]
                    control["options"]["itemsRefType"] = items_ref_type
                
                # Add source tracking
                control["options"]["x-source"] = f"{source_class}.{prop_name}"
                
                # Add rule if present - rewrite scope paths for nested properties
                if "x-ui-rules" in prop_schema:
                    control["rule"] = rewrite_rule_scopes(prop_schema["x-ui-rules"], parent_prop_name)
                
                # Extract section for nested field
                section_name, collapse_state = extract_section_info(prop_schema, defs, use_general_default=False)
                # If still "General", use parent model's x-ui-section if available
                if section_name == "General" and parent_section:
                    section_name = parent_section
                
                controls_with_meta.append((control, section_name, collapse_state, order))
            else:
                # Regular field - generate control normally
                section_name, collapse_state = extract_section_info(prop_schema, defs)
                element = generate_uischema_for_property(prop_name, prop_schema, defs, source_class)
                # Handle both single elements and lists (arrays with help text return [HelpButton, Control])
                if isinstance(element, list):
                    for elem in element:
                        controls_with_meta.append((elem, section_name, collapse_state, order))
                else:
                    controls_with_meta.append((element, section_name, collapse_state, order))
        
        # Group controls by section and create Group layouts
        group_elements = group_controls_by_section(controls_with_meta)
        
        # Build category object
        category = {
            "type": "Category",
            "label": group_name,
            "elements": group_elements
        }
        
        # Add metadata if available
        if group_name in category_metadata:
            category["options"] = category_metadata[group_name]
        
        categories.append(category)
    
    combined_uischema = {
        "type": "Categorization",
        "elements": categories
    }
    
    # Write UISchema first
    output_path.mkdir(parents=True, exist_ok=True)
    uischema_file = output_path / "uischema.json"
    
    with open(uischema_file, "w") as f:
        json.dump(combined_uischema, f, indent=2)
    
    # Now validate the written file with TypeScript
    if not QUIET:
        print("\nValidating UISchema...")
    validate_uischema(combined_uischema)
    
    # Write JSON Schema
    schema_file = output_path / "schema.json"
    
    with open(schema_file, "w") as f:
        json.dump(schema, f, indent=2)
    
    if not QUIET:
        print(f"\n✅ Generated UISchema: {uischema_file}")
        print(f"✅ Generated JSON Schema: {schema_file}")
        print(f"   Properties: {len(properties)}")
        print(f"   Definitions: {len(defs)}")
        print(f"   Tabs created: {', '.join([cat['label'] for cat in categories])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate UISchema and JSON Schema from Pydantic models"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for schema files (default: dao/webserver/app/static/schemas/)"
    )
    args = parser.parse_args()
    
    QUIET = args.quiet
    main(output_dir=args.output_dir)
