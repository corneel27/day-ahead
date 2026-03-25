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
  Link,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'

interface StringRendererProps extends ControlProps {
  data: string | null | undefined
}

const StringRenderer: React.FC<StringRendererProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
  visible,
  required,
}) => {
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const validationHint = uischema?.options?.validationHint
  const docsUrl = uischema?.options?.docsUrl

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
          {label}
          {required && <span style={{ color: 'red' }}> *</span>}
        </Typography>
        {help && (
          <Tooltip title={help} arrow>
            <IconButton size="small" sx={{ p: 0 }}>
              <HelpOutlineIcon sx={{ fontSize: 18, color: 'text.secondary' }} />
            </IconButton>
          </Tooltip>
        )}
        {docsUrl && (
          <Tooltip title="External Documentation" arrow>
            <IconButton
              size="small"
              sx={{ p: 0 }}
              component={Link}
              href={docsUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              <OpenInNewIcon sx={{ fontSize: 18, color: 'primary.main' }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {description}
        </Typography>
      )}
      <TextField
        value={data || ''}
        onChange={(e) => handleChange(path, e.target.value || null)}
        fullWidth
        size="small"
        placeholder={validationHint || 'Enter value'}
      />
    </Box>
  )
}

// Tester that matches all string types (including nullable and union types with string)
export const stringTester = rankWith(
  10, // Much higher than default (3) to ensure override
  and(
    schemaMatches((schema) => {
      // Direct string type
      if (schema.type === 'string') return true
      
      // anyOf with string (nullable strings, unions with SecretStr, etc.)
      if (schema.anyOf && Array.isArray(schema.anyOf)) {
        return schema.anyOf.some((s: any) => s.type === 'string')
      }
      
      return false
    }),
    // Exclude enums - they use EnumRenderer
    schemaMatches((schema) => !schema.enum)
  )
)

export default withJsonFormsControlProps(StringRenderer)
