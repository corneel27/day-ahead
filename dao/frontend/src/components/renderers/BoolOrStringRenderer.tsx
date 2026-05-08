import React, { useState } from 'react'
import {
  ControlProps,
  rankWith,
  schemaMatches,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  Box,
  ToggleButton,
  ToggleButtonGroup,
  TextField,
  Checkbox,
  FormControlLabel,
  Typography,
} from '@mui/material'

interface BoolOrStringRendererProps extends ControlProps {
  data: boolean | string | undefined
}

const BoolOrStringRenderer: React.FC<BoolOrStringRendererProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
}) => {
  const help = uischema?.options?.help || description
  const isBoolean = typeof data === 'boolean'
  const [mode, setMode] = useState<'boolean' | 'string'>(
    isBoolean ? 'boolean' : 'string'
  )

  const handleModeChange = (_: React.MouseEvent, newMode: 'boolean' | 'string' | null) => {
    if (newMode) {
      setMode(newMode)
      handleChange(path, newMode === 'boolean' ? false : '')
    }
  }

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" gutterBottom>
        {label}
      </Typography>
      {help && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {help}
        </Typography>
      )}

      <ToggleButtonGroup
        value={mode}
        exclusive
        onChange={handleModeChange}
        size="small"
        sx={{ mb: 2 }}
      >
        <ToggleButton value="boolean">Boolean</ToggleButton>
        <ToggleButton value="string">Entity ID</ToggleButton>
      </ToggleButtonGroup>

      {mode === 'boolean' ? (
        <FormControlLabel
          control={
            <Checkbox
              checked={data === true}
              onChange={(e) => handleChange(path, e.target.checked)}
            />
          }
          label={label}
        />
      ) : (
        <TextField
          value={typeof data === 'string' ? data : ''}
          onChange={(e) => handleChange(path, e.target.value)}
          placeholder="e.g., binary_sensor.tax_refund"
          fullWidth
          size="small"
        />
      )}
    </Box>
  )
}

// Tester for anyOf with boolean and string
export const boolOrStringTester = rankWith(
  5,
  schemaMatches((schema) => {
    if (!schema.anyOf || !Array.isArray(schema.anyOf)) return false
    const types = schema.anyOf.map((s: any) => s.type).filter(Boolean)
    return types.includes('boolean') && types.includes('string')
  })
)

export default withJsonFormsControlProps(BoolOrStringRenderer)
