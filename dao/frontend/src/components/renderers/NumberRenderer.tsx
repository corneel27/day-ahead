import React from 'react'
import {
  ControlProps,
  rankWith,
  and,
  schemaMatches,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  TextField,
  Box,
  Typography,
  IconButton,
  Tooltip,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'

interface NumberRendererProps extends ControlProps {
  data: number | null | undefined
}

const NumberRenderer: React.FC<NumberRendererProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
  visible,
  required,
  schema,
  errors,
}) => {
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const unit = uischema?.options?.unit
  const validationHint = uischema?.options?.validationHint
  
  const isInteger = schema.type === 'integer'
  const hasError = errors && errors.length > 0
  const errorMessage = hasError ? errors : undefined

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
      {(description || hasError) && (
        <Typography variant="body2" sx={{ mb: 1 }}>
          {description && <span style={{ color: 'text.secondary' }}>{description}</span>}
          {description && hasError && <span> • </span>}
          {hasError && <span style={{ color: '#d32f2f' }}>{errorMessage}</span>}
        </Typography>
      )}
      <TextField
        type="number"
        value={data ?? ''}
        onChange={(e) => {
          const value = e.target.value
          if (value === '') {
            handleChange(path, null)
          } else {
            const numValue = isInteger ? parseInt(value, 10) : parseFloat(value)
            if (!isNaN(numValue)) {
              handleChange(path, numValue)
            }
          }
        }}
        fullWidth
        size="small"
        placeholder={validationHint || 'Enter number'}
        inputProps={{
          step: isInteger ? 1 : 0.01,
        }}
      />
    </Box>
  )
}

// Tester that matches number and integer types
export const numberTester = rankWith(
  10, // Much higher than default (3) to ensure override
  and(
    schemaMatches((schema) => {
      // Direct number/integer type
      if (schema.type === 'number' || schema.type === 'integer') return true
      
      // anyOf with number/integer (nullable numbers)
      if (schema.anyOf && Array.isArray(schema.anyOf)) {
        return schema.anyOf.some((s: any) => 
          s.type === 'number' || s.type === 'integer'
        )
      }
      
      return false
    })
  )
)

export default withJsonFormsControlProps(NumberRenderer)
