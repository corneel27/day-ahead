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

interface EntityPickerOrStringRendererProps extends ControlProps {
  data: string | undefined
}

/**
 * FlexStr renderer: Toggle between manual string input and entity picker
 * 
 * Detects FlexStr fields by $ref to FlexStr in schema.
 * Both modes accept strings - toggle just switches between:
 * - String mode: Manual text input
 * - Entity mode: Entity picker with autocomplete from HA
 */
const EntityPickerOrStringRenderer: React.FC<EntityPickerOrStringRendererProps> = (props) => {
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
  
  // Initialize mode based on current data - check if it looks like an entity ID
  const [mode, setMode] = useState<'string' | 'entity'>(() => {
    if (typeof data === 'string' && data.includes('.')) {
      // Looks like entity ID (has domain.object_id pattern)
      return 'entity'
    }
    return 'string'
  })
  
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const unit = uischema?.options?.unit
  const validationHint = uischema?.options?.validationHint
  
  const hasError = Boolean(errors && errors.length > 0)
  const errorMessage = hasError ? errors : undefined

  const stringValue = typeof data === 'string' ? data : ''

  /**
   * Handle mode change
   */
  const handleModeChange = (_: React.MouseEvent<HTMLElement>, newMode: 'string' | 'entity' | null) => {
    if (newMode !== null && newMode !== mode) {
      setMode(newMode)
      handleChange(path, null) // Clear value when switching modes
    }
  }

  /**
   * Handle value change for string mode
   */
  const handleValueChange = (value: string) => {
    handleChange(path, value || null)
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
          <ToggleButton value="string">
            String
          </ToggleButton>
          <ToggleButton value="entity">
            Entity
          </ToggleButton>
        </ToggleButtonGroup>
        
        <Box sx={{ flexGrow: 1 }}>
          {mode === 'string' ? (
            <TextField
              type="text"
              value={stringValue}
              onChange={(e) => handleValueChange(e.target.value)}
              fullWidth
              size="small"
              placeholder={validationHint || 'Enter string value'}
              error={hasError}
            />
          ) : (
            <EntityPickerRenderer
              {...props}
              data={stringValue}
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

// Tester that matches FlexStr fields by refType in UISchema options  
export const entityPickerOrStringTester = rankWith(
  15, // High priority
  (uischema, _schema) => {
    // Check UISchema options for refType metadata
    const refType = uischema.options?.refType;
    return refType === 'FlexStr';
  }
)

export default withJsonFormsControlProps(EntityPickerOrStringRenderer)
