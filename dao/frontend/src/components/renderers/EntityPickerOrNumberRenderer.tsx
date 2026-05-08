import React, { useState } from 'react'
import {
  ControlProps,
  rankWith,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  TextField,
  Box,
  Typography,
  IconButton,
  Tooltip,
  ToggleButtonGroup,
  ToggleButton,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import { EntityPickerRenderer } from './EntityPickerRenderer'

interface EntityPickerOrNumberRendererProps extends ControlProps {
  data: number | string | object | undefined
}

const EntityPickerOrNumberRenderer: React.FC<EntityPickerOrNumberRendererProps> = (props) => {
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
  const [mode, setMode] = useState<'number' | 'entity'>(() => {
    if (typeof data === 'string') return 'entity'
    if (typeof data === 'object' && data && 'entity' in data) return 'entity'
    return 'number'
  })
  
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const unit = uischema?.options?.unit
  const validationHint = uischema?.options?.validationHint
  
  const hasError = Boolean(errors && errors.length > 0)
  const errorMessage = hasError ? errors : undefined

  // Extract display value for number mode
  const displayValue = typeof data === 'number' ? data.toString() : ''

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
  const handleModeChange = (_: React.MouseEvent<HTMLElement>, newMode: 'number' | 'entity' | null) => {
    if (newMode !== null && newMode !== mode) {
      setMode(newMode)
      handleChange(path, null) // Clear value when switching modes
    }
  }

  /**
   * Handle value change for number mode
   */
  const handleValueChange = (value: string) => {
    if (value === '') {
      handleChange(path, null)
    } else {
      const numValue = parseFloat(value)
      if (!isNaN(numValue)) {
        handleChange(path, numValue)
      }
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
          <ToggleButton value="number">
            Number
          </ToggleButton>
          <ToggleButton value="entity">
            Entity
          </ToggleButton>
        </ToggleButtonGroup>
        
        <Box sx={{ flexGrow: 1 }}>
          {mode === 'number' ? (
            <TextField
              type="number"
              value={displayValue}
              onChange={(e) => handleValueChange(e.target.value)}
              fullWidth
              size="small"
              placeholder={validationHint || 'Enter number'}
              error={hasError}
              inputProps={{
                step: 0.01,
              }}
            />
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

// Tester that matches FlexInt/FlexFloat fields by refType in UISchema options
export const entityPickerOrNumberTester = rankWith(
  15, // High priority
  (uischema, _schema) => {
    // Check UISchema options for refType metadata
    const refType = uischema.options?.refType
    return refType === 'FlexInt' || refType === 'FlexFloat'
  }
)

export default withJsonFormsControlProps(EntityPickerOrNumberRenderer)
