import React, { useContext } from 'react'
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
  Autocomplete,
  Link,
} from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { SecretsContext } from '../../App'

/**
 * Secret picker renderer for x-ui-widget: "secret-picker"
 * Allows selection of secrets defined in secrets.json using !secret key_name syntax
 */
const SecretPickerRenderer: React.FC<ControlProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
  visible,
  required,
  errors,
}) => {
  const { secrets } = useContext(SecretsContext)
  
  if (!visible) {
    return null
  }

  const help = uischema?.options?.help
  const unit = uischema?.options?.unit
  const validationHint = uischema?.options?.validationHint
  const docsUrl = uischema?.options?.docsUrl
  
  const hasError = Boolean(errors && errors.length > 0)
  const errorMessage = hasError ? errors : undefined
  
  // Get available secret keys
  const secretKeys = Object.keys(secrets)
  
  // Parse current value - could be plain string or !secret reference
  const isSecretRef = typeof data === 'string' && data.startsWith('!secret ')
  const currentSecretKey = isSecretRef ? data.substring(8) : ''
  const displayValue = isSecretRef ? data : (data || '')

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
      {(description || hasError || validationHint) && (
        <Typography variant="body2" sx={{ mb: 1 }}>
          {description && <span style={{ color: 'text.secondary' }}>{description}</span>}
          {description && hasError && <span> • </span>}
          {hasError && <span style={{ color: '#d32f2f' }}>{errorMessage}</span>}
          {validationHint && <span style={{ color: 'text.secondary', fontStyle: 'italic' }}> ({validationHint})</span>}
        </Typography>
      )}
      
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Autocomplete
          freeSolo
          options={secretKeys}
          value={currentSecretKey}
          onChange={(_, newValue) => {
            if (newValue) {
              handleChange(path, `!secret ${newValue}`)
            } else {
              handleChange(path, '')
            }
          }}
          onInputChange={(_, newInputValue) => {
            if (newInputValue && !newInputValue.startsWith('!secret ')) {
              handleChange(path, `!secret ${newInputValue}`)
            }
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              placeholder="Select or type secret key"
              error={hasError}
            />
          )}
          sx={{ flex: 1 }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 100 }}>
          {secretKeys.length} secret{secretKeys.length !== 1 ? 's' : ''} available
        </Typography>
      </Box>
      {displayValue && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Current: {displayValue}
        </Typography>
      )}
    </Box>
  )
}

// Tester that matches SecretStr fields by refType in UISchema options
export const secretPickerTester = rankWith(
  15, // High priority
  (uischema, _schema) => {
    // Check UISchema options for refType metadata
    return uischema.options?.refType === 'SecretStr'
  }
)

export default withJsonFormsControlProps(SecretPickerRenderer)
