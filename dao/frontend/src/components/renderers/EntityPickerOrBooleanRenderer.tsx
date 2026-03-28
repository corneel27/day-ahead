import React, { useState } from 'react'
import {
  ControlProps,
  rankWith,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  Box,
  Typography,
  IconButton,
  Tooltip,
  ToggleButtonGroup,
  ToggleButton,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import { EntityPickerRenderer } from './EntityPickerRenderer'

const EntityPickerOrBooleanRenderer: React.FC<ControlProps> = (props) => {
  const {
    data,
    handleChange,
    path,
    label,
    description,
    uischema,
    visible,
    required,
    errors,
  } = props
  
  // Initialize mode based on current data type
  const [mode, setMode] = useState<'boolean' | 'entity'>(() => {
    if (typeof data === 'string') return 'entity'
    if (typeof data === 'object' && data && 'entity' in data) return 'entity'
    return 'boolean'
  })
  
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const unit = uischema?.options?.unit
  const validationHint = uischema?.options?.validationHint
  
  const hasError = Boolean(errors && errors.length > 0)
  const errorMessage = hasError ? errors : undefined

  // Extract display value for boolean mode
  const booleanValue = typeof data === 'boolean' ? data : null

  // Extract entity value for entity mode
  const entityValue = (() => {
    if (typeof data === 'string') return data
    if (typeof data === 'object' && data && 'entity' in data) {
      return (data as { entity: string }).entity
    }
    return ''
  })()

  /**
   * Handle mode change
   */
  const handleModeChange = (_: React.MouseEvent<HTMLElement>, newMode: 'boolean' | 'entity' | null) => {
    if (newMode !== null && newMode !== mode) {
      setMode(newMode)
      handleChange(path, null) // Clear value when switching modes
    }
  }

  /**
   * Handle boolean value change
   */
  const handleBooleanChange = (_: React.MouseEvent<HTMLElement>, newValue: boolean | null) => {
    if (newValue !== null) {
      handleChange(path, newValue)
    }
  }

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
          {label}
          {unit && ` (${unit})`}
          {required && <span style={{ color: 'red' }}> *</span>}
        </Typography>
        {help && (
          <Tooltip title={help} arrow>
            <IconButton size="small" sx={{ p: 0 }}>
              <HelpOutlineIcon sx={{ fontSize: 18, color: 'text.secondary' }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {(description || hasError || validationHint) && (
        <Typography variant="body2" sx={{ mb: 1 }}>
          {description && <span style={{ color: 'text.secondary' }}>{description}</span>}
          {description && hasError && <span> • </span>}
          {hasError && <span style={{ color: '#d32f2f' }}>{errorMessage}</span>}
          {validationHint && <span style={{ color: 'text.secondary', fontStyle: 'italic' }}> ({validationHint})</span>}
        </Typography>
      )}

      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
        <ToggleButtonGroup
          value={mode}
          exclusive
          onChange={handleModeChange}
          size="small"
          sx={{ mt: 0.5 }}
        >
          <ToggleButton value="boolean">
            Boolean
          </ToggleButton>
          <ToggleButton value="entity">
            Entity
          </ToggleButton>
        </ToggleButtonGroup>
        
        <Box sx={{ flexGrow: 1 }}>
          {mode === 'boolean' ? (
            <ToggleButtonGroup
              value={booleanValue}
              exclusive
              onChange={handleBooleanChange}
              size="small"
              fullWidth
            >
              <ToggleButton value={true}>
                True
              </ToggleButton>
              <ToggleButton value={false}>
                False
              </ToggleButton>
            </ToggleButtonGroup>
          ) : (
            <EntityPickerRenderer
              {...props}
              data={entityValue}
              handleChange={(_, value) => {
                handleChange(path, value || null)
              }}
              label=""
              description=""
              required={false}
              uischema={{
                ...uischema,
                options: {
                  ...uischema.options,
                  help: undefined,
                  unit: undefined,
                  validationHint: undefined,
                }
              }}
            />
          )}
        </Box>
      </Box>
    </Box>
  )
}

// Tester that matches FlexBool fields by refType in UISchema options
export const entityPickerOrBooleanTester = rankWith(
  15, // High priority
  (uischema, _schema) => {
    // Check UISchema options for refType metadata
    return uischema.options?.refType === 'FlexBool'
  }
)

export default withJsonFormsControlProps(EntityPickerOrBooleanRenderer)
