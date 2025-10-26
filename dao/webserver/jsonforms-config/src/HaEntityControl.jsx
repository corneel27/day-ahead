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
  Select,
  MenuItem,
  FormControl,
  FormHelperText,
} from '@mui/material';
import NumbersIcon from '@mui/icons-material/Numbers';
import SensorsIcon from '@mui/icons-material/Sensors';

const HaEntityControl = (props) => {
  const { data, handleChange, path, label, description, schema, enabled } = props;
  const [mode, setMode] = useState('value'); // 'value' or 'entity'
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState('');

  // Get domain filter from schema custom property
  const domainFilter = schema?.haEntityDomains || 'input_number,sensor,number';
  const allowDirectValue = schema?.haEntityAllowValue === true; // Default to false, only true if explicitly set
  
  // Detect field type from schema (handle oneOf for enum + entity pattern)
  let schemaType = Array.isArray(schema?.type) ? schema.type[0] : schema?.type;
  let isEnum = schema?.enum !== undefined;
  
  // Check if this is a oneOf with enum (enum field that also accepts entities)
  if (schema?.oneOf && !isEnum) {
    const enumSchema = schema.oneOf.find(s => s.enum !== undefined);
    if (enumSchema) {
      isEnum = true;
      schemaType = enumSchema.type;
      // Store enum values for rendering
      schema.enum = enumSchema.enum;
    }
  }
  
  const isBoolean = schemaType === 'boolean';
  const isNumber = schemaType === 'number';
  const isString = schemaType === 'string' && !isEnum;

  // Determine if current data is an entity or a value
  useEffect(() => {
    if (typeof data === 'string' && (data.includes('.') || data.startsWith('input_'))) {
      setMode('entity');
      setInputValue(data);
    } else {
      setMode('value');
    }
  }, [data]);

  // Fetch entities from HA
  const fetchEntities = async (search = '') => {
    if (search.length < 2) {
      setEntities([]);
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams({
        q: search,
        domain: domainFilter,
      });
      
      const response = await fetch(`/api/ha/entities/search?${params}`);
      if (response.ok) {
        const data = await response.json();
        // Extract entity_id from the results
        const entityList = Array.isArray(data) ? data.map(e => e.entity_id || e) : [];
        setEntities(entityList);
      } else {
        console.error('Failed to fetch entities:', response.statusText);
        setEntities([]);
      }
    } catch (error) {
      console.error('Error fetching entities:', error);
      setEntities([]);
    } finally {
      setLoading(false);
    }
  };

  const handleModeChange = (event, newMode) => {
    if (newMode !== null) {
      setMode(newMode);
      if (newMode === 'value') {
        // Switch to value mode - set appropriate default based on type
        if (isEnum && schema.enum.length > 0) {
          handleChange(path, schema.default || schema.enum[0]);
        } else if (isBoolean) {
          handleChange(path, schema.default || false);
        } else if (isNumber) {
          handleChange(path, schema.default || 0);
        } else {
          handleChange(path, schema.default || '');
        }
      } else {
        // Switch to entity mode - clear value
        handleChange(path, '');
        setInputValue('');
      }
    }
  };

  const handleValueChange = (event) => {
    const value = event.target.value;
    if (isNumber) {
      handleChange(path, value === '' ? undefined : Number(value));
    } else {
      handleChange(path, value);
    }
  };

  const handleEntityChange = (event, newValue) => {
    if (newValue) {
      handleChange(path, newValue);
      setInputValue(newValue);
    }
  };

  const handleInputChange = (event, newInputValue) => {
    setInputValue(newInputValue);
    fetchEntities(newInputValue);
  };

  // Render the appropriate input based on schema type
  const renderValueInput = () => {
    if (isEnum) {
      return (
        <FormControl fullWidth>
          <Select
            value={data || schema.default || (schema.enum.length > 0 ? schema.enum[0] : '')}
            onChange={handleValueChange}
          >
            {schema.enum.map((option) => (
              <MenuItem key={option} value={option}>
                {option}
              </MenuItem>
            ))}
          </Select>
          {description && <FormHelperText>{description}</FormHelperText>}
        </FormControl>
      );
    }
    
    if (isBoolean) {
      return (
        <FormControl fullWidth>
          <Select
            value={data !== undefined ? String(data) : String(schema.default || false)}
            onChange={(e) => handleChange(path, e.target.value === 'true')}
          >
            <MenuItem value="true">True</MenuItem>
            <MenuItem value="false">False</MenuItem>
          </Select>
          {description && <FormHelperText>{description}</FormHelperText>}
        </FormControl>
      );
    }
    
    if (isNumber) {
      return (
        <TextField
          fullWidth
          type="number"
          value={data !== undefined ? data : (schema.default || 0)}
          onChange={handleValueChange}
          helperText={description}
          inputProps={{
            min: schema?.minimum,
            max: schema?.maximum,
            step: schema?.multipleOf || 0.001,
          }}
        />
      );
    }
    
    // Default: string input
    return (
      <TextField
        fullWidth
        type="text"
        value={data || schema.default || ''}
        onChange={handleValueChange}
        helperText={description}
      />
    );
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
            label="Flex Setting" 
            size="small" 
            color="primary" 
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
            <NumbersIcon sx={{ mr: 0.5 }} fontSize="small" />
            Value
          </ToggleButton>
          <ToggleButton value="entity">
            <SensorsIcon sx={{ mr: 0.5 }} fontSize="small" />
            HA Entity
          </ToggleButton>
        </ToggleButtonGroup>
      )}

      {mode === 'value' && allowDirectValue ? (
        renderValueInput()
      ) : (
        <Autocomplete
          freeSolo
          fullWidth
          options={entities}
          value={data || ''}
          inputValue={inputValue}
          onChange={handleEntityChange}
          onInputChange={handleInputChange}
          loading={loading}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Search for HA entity"
              helperText={`Type to search Home Assistant entities (${domainFilter})`}
            />
          )}
          filterOptions={(x) => x} // Disable client-side filtering, we filter server-side
        />
      )}
      
      {mode === 'entity' && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          The entity value will be used dynamically from Home Assistant
        </Typography>
      )}
    </Box>
  );
};

export default withJsonFormsControlProps(HaEntityControl);
