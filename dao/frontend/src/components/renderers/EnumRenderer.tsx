import React from 'react'
import {
  ControlProps,
  rankWith,
  isEnumControl,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  FormControl,
  Select,
  MenuItem,
  Typography,
  Box,
  IconButton,
  Tooltip,
  Link,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'

interface EnumRendererProps extends ControlProps {
  data: string | undefined
}

const EnumRenderer: React.FC<EnumRendererProps> = ({
  data,
  handleChange,
  path,
  schema,
  label,
  description,
  uischema,
  visible,
}) => {
  if (!visible) {
    return null
  }

  const enumValues = schema.enum || []
  const help = uischema?.options?.help || description
  const docsUrl = uischema?.options?.docsUrl

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
          {label}
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
      <FormControl fullWidth size="small">
        <Select
          value={data || ''}
          onChange={(e) => handleChange(path, e.target.value)}
        >
          {enumValues.map((value: string) => (
            <MenuItem key={value} value={value}>
              {value}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  )
}

// Tester that matches enum fields
export const enumTester = rankWith(
  10, // Much higher than default material renderer
  isEnumControl
)

export default withJsonFormsControlProps(EnumRenderer)
