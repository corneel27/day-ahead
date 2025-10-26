# Home Assistant Entity Renderer

## Overview

The HA Entity Renderer is a custom JSONForms renderer that provides a special UI control for fields that can accept either a direct value OR a Home Assistant entity reference.

## Features

- **Toggle Mode**: Switch between direct value entry and HA entity selection
- **Autocomplete Search**: Live search of Home Assistant entities as you type
- **Domain Filtering**: Filter entities by domain (sensor, input_number, etc.)
- **Flexible Configuration**: Control behavior via schema properties

## How to Use

### Basic Setup

To enable the HA Entity Renderer for a field, add these custom properties to your JSON Schema:

```json
{
  "your_field": {
    "type": ["number", "string"],
    "default": 0.005,
    "description": "Your field description",
    "haEntityDomains": "input_number,sensor,number",
    "haEntityAllowValue": true,
    "minimum": 0,
    "maximum": 100
  }
}
```

### Schema Properties

#### Required Properties

- **`haEntityDomains`**: Comma-separated list of Home Assistant entity domains to filter by
  - Examples: `"sensor"`, `"input_number,sensor"`, `"input_number,sensor,number"`
  - Common domains: `sensor`, `input_number`, `input_text`, `input_boolean`, `binary_sensor`, `switch`, `number`

#### Optional Properties

- **`haEntityAllowValue`**: Boolean (default: `true`)
  - `true`: Shows toggle button to switch between value/entity modes
  - `false`: Only allows entity selection (no direct value input)

- **`type`**: Array of types
  - Use `["number", "string"]` for numeric fields that can also accept entity strings
  - Use `["string"]` for entity-only fields

- **`minimum`, `maximum`, `default`**: Standard JSON Schema validation
  - Used when entering direct values

### Examples

#### 1. Numeric Field with Entity Option
```json
"max_gap": {
  "type": ["number", "string"],
  "default": 0.005,
  "description": "Maximum gap between iterations",
  "haEntityDomains": "input_number,sensor,number",
  "haEntityAllowValue": true,
  "minimum": 0.00001,
  "maximum": 1.0
}
```

#### 2. Temperature Setpoint
```json
"entity setpoint": {
  "type": ["number", "string"],
  "default": 55,
  "description": "Boiler setpoint temperature in °C",
  "haEntityDomains": "input_number,sensor,number",
  "haEntityAllowValue": true,
  "minimum": 0,
  "maximum": 100
}
```

#### 3. Entity-Only Field (No Direct Value)
```json
"soc_entity": {
  "type": "string",
  "description": "Battery State of Charge entity",
  "haEntityDomains": "sensor",
  "haEntityAllowValue": false
}
```

## User Interface

When a field uses this renderer, users will see:

1. **Field Label** with an "HA Entity" chip badge
2. **Toggle Button Group** (if `haEntityAllowValue` is true):
   - **Value**: Direct numeric/text input
   - **HA Entity**: Entity autocomplete selector
3. **Input Field**:
   - Number field with min/max validation (when in Value mode)
   - Autocomplete with search (when in HA Entity mode)

## Technical Details

### Files

- `src/HaEntityControl.jsx`: Main component implementation
- `src/haEntityRenderer.js`: Renderer registration and tester function
- `src/App.jsx`: Renderer is registered in the JSONForms renderers array

### API Endpoint

The component calls: `/api/ha/entities/search?q=<search>&domain=<domains>`

This endpoint must return an array of entity objects:
```json
[
  {
    "entity_id": "sensor.example",
    "friendly_name": "Example Sensor",
    "domain": "sensor",
    "state": "25.5",
    "unit": "°C"
  }
]
```

### How It Works

1. The tester function checks if a schema property has `haEntityDomains` defined
2. If found, the custom renderer is used (priority 10, overrides default renderers)
3. Component reads domain filter from `schema.haEntityDomains`
4. Component reads value toggle setting from `schema.haEntityAllowValue`
5. Entity search is performed with minimum 2 characters typed
6. Results are filtered by domain on the backend

## Benefits

- **Reusable**: One renderer handles all HA entity fields
- **Flexible**: Controlled by schema properties, no code changes needed
- **Type-Safe**: Supports both direct values and entity references
- **User-Friendly**: Clear UI with autocomplete and visual feedback
- **Maintainable**: Add new fields by just updating the schema

## Adding New Fields

To add the HA Entity Renderer to a new field:

1. Open `dao/options_schema.json`
2. Find your field definition
3. Change `type` to `["number", "string"]` or `["string"]`
4. Add `"haEntityDomains": "domain1,domain2"`
5. Add `"haEntityAllowValue": true` (or `false` for entity-only)
6. Add validation properties (`minimum`, `maximum`, etc.) as needed
7. Rebuild: `npm run build`

That's it! The renderer will automatically be used for that field.
