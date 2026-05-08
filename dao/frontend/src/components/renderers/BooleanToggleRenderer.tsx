import React from 'react';
import {
  ControlProps,
  rankWith,
  and,
  uiTypeIs
} from '@jsonforms/core';
import { withJsonFormsControlProps } from '@jsonforms/react';
import {
  FormControl,
  FormControlLabel,
  FormHelperText,
  Switch,
  Box,
  Typography
} from '@mui/material';

/**
 * Custom renderer for boolean toggle fields.
 * 
 * Detects fields with options.format === "boolean" or options.toggle === true
 * (typically discriminator fields from discriminated unions).
 * 
 * Renders as a Material-UI Switch (toggle).
 */
const BooleanToggleRenderer = (props: ControlProps) => {
  const { data, handleChange, path, label, errors, enabled, visible, uischema,description } = props;

  const options = (uischema as any)?.options || {};
  const help = options.help;

  if (!visible) {
    return null;
  }

  const handleToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    handleChange(path, event.target.checked);
  };

  const hasError = !!(errors && errors.length > 0);

  return (
    <FormControl
      fullWidth
      error={hasError}
      disabled={!enabled}
      margin="normal"
    >
      <FormControlLabel
        control={
          <Switch
            checked={data || false}
            onChange={handleToggle}
            color="primary"
          />
        }
        label={
          <Box>
            <Typography variant="body1" component="span">
              {label}
            </Typography>
            {description && (
              <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
                {description}
              </Typography>
            )}
          </Box>
        }
      />
      
      {help && (
        <FormHelperText sx={{ ml: 0, mt: 0.5 }}>
          {help}
        </FormHelperText>
      )}
      
      {hasError && (
        <FormHelperText error>
          {errors}
        </FormHelperText>
      )}
    </FormControl>
  );
};

// Check if options has format: "boolean" or toggle: true
export const booleanToggleTester = rankWith(
  25, // Higher priority than default controls but lower than very specific renderers
  and(
    uiTypeIs('Control'),
    (uischema) => {
      const options = (uischema as any)?.options;
      return options?.format === 'boolean' || options?.toggle === true;
    }
  )
);

export default withJsonFormsControlProps(BooleanToggleRenderer);
