import React, { useState, useEffect } from 'react';
import { withJsonFormsControlProps } from '@jsonforms/react';
import {
  Autocomplete,
  TextField,
  Box,
  Typography,
  ToggleButtonGroup,
  ToggleButton,
  Chip,
} from '@mui/material';
import KeyIcon from '@mui/icons-material/Key';
import TextFieldsIcon from '@mui/icons-material/TextFields';

const SecretControl = (props) => {
  const { data, handleChange, path, label, description, schema, enabled } = props;
  const [mode, setMode] = useState('value'); // 'value' or 'secret'
  const [secrets, setSecrets] = useState([]);
  const [loading, setLoading] = useState(false);

  const allowDirectValue = schema?.haSecretAllowValue === true; // Default to false

  // Determine if current data is a secret reference or a direct value
  useEffect(() => {
    if (typeof data === 'string' && data.startsWith('!secret ')) {
      setMode('secret');
    } else {
      setMode('value');
    }
  }, [data]);

  // Fetch secrets from backend
  useEffect(() => {
    const fetchSecrets = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/settings/secrets.json');
        if (response.ok) {
          const secretsData = await response.json();
          // Extract secret keys
          const secretKeys = Object.keys(secretsData || {});
          setSecrets(secretKeys);
        } else {
          console.error('Failed to fetch secrets:', response.statusText);
          setSecrets([]);
        }
      } catch (error) {
        console.error('Error fetching secrets:', error);
        setSecrets([]);
      } finally {
        setLoading(false);
      }
    };

    if (schema?.haSecret) {
      fetchSecrets();
    }
  }, [schema]);

  const handleModeChange = (event, newMode) => {
    if (newMode !== null) {
      setMode(newMode);
      if (newMode === 'value') {
        // Switch to value mode - clear secret reference
        handleChange(path, schema?.default || '');
      } else {
        // Switch to secret mode - clear value
        handleChange(path, '');
      }
    }
  };

  const handleValueChange = (event) => {
    handleChange(path, event.target.value);
  };

  const handleSecretChange = (event, newValue) => {
    if (newValue) {
      // Store as !secret <key>
      handleChange(path, `!secret ${newValue}`);
    }
  };

  // Extract secret key from "!secret key_name" format
  const getSecretKey = () => {
    if (typeof data === 'string' && data.startsWith('!secret ')) {
      return data.substring(8); // Remove "!secret " prefix
    }
    return '';
  };

  if (!enabled) {
    return null;
  }

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
        <Typography variant="subtitle2">
          {label}
        </Typography>
        {allowDirectValue && (
          <Chip 
            label="Secret Reference" 
            size="small" 
            color="secondary" 
            variant="outlined"
          />
        )}
      </Box>
      
      {allowDirectValue && (
        <ToggleButtonGroup
          value={mode}
          exclusive
          onChange={handleModeChange}
          size="small"
          sx={{ mb: 1 }}
        >
          <ToggleButton value="value">
            <TextFieldsIcon sx={{ mr: 0.5 }} fontSize="small" />
            Direct Value
          </ToggleButton>
          <ToggleButton value="secret">
            <KeyIcon sx={{ mr: 0.5 }} fontSize="small" />
            Secret
          </ToggleButton>
        </ToggleButtonGroup>
      )}

      {mode === 'value' && allowDirectValue ? (
        <TextField
          fullWidth
          type={schema?.format === 'password' ? 'password' : 'text'}
          value={data || ''}
          onChange={handleValueChange}
          helperText={description}
          placeholder="Enter value directly"
        />
      ) : (
        <Autocomplete
          fullWidth
          options={secrets}
          value={getSecretKey()}
          onChange={handleSecretChange}
          loading={loading}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Select secret from secrets.json"
              helperText="Secrets are stored in secrets.json and referenced as !secret <key>"
            />
          )}
        />
      )}
      
      {mode === 'secret' && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          The actual value will be read from secrets.json at runtime
        </Typography>
      )}
    </Box>
  );
};

export default withJsonFormsControlProps(SecretControl);
