import React from 'react'
import {
  ControlProps,
  rankWith,
  schemaMatches,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  TextField,
  Box,
} from '@mui/material'

interface OptionalStringRendererProps extends ControlProps {
  data: string | null | undefined
}

const OptionalStringRenderer: React.FC<OptionalStringRendererProps> = (props) => {
  const {
    data,
    handleChange,
    path,
    label,
    description,
    uischema,
    visible,
  } = props
  
  const help = uischema?.options?.help || description
  const validationHint = uischema?.options?.validationHint

  // Respect visibility from rules
  if (!visible) {
    return null
  }

  return (
    <Box sx={{ mb: 2 }}>
      <TextField
        label={label}
        value={data || ''}
        onChange={(e) => handleChange(path, e.target.value || null)}
        fullWidth
        helperText={help || validationHint}
        placeholder="Enter value or leave empty"
        size="small"
      />
    </Box>
  )
}

// Tester for anyOf with string, $ref, and null (optional string fields)
export const optionalStringTester = rankWith(
  6, // Higher rank than default to override
  schemaMatches((schema) => {
    if (!schema.anyOf || !Array.isArray(schema.anyOf)) return false
    
    // Check if it's a nullable string with possible $ref (like SecretStr)
    const hasString = schema.anyOf.some((s: any) => s.type === 'string')
    const hasNull = schema.anyOf.some((s: any) => s.type === 'null')
    
    // Match: string + null, or string + ref + null
    return hasString && hasNull && schema.anyOf.length <= 3
  })
)

export default withJsonFormsControlProps(OptionalStringRenderer)
