import React, { useState, useContext, forwardRef } from 'react'
import {
  ControlProps,
  rankWith,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  Box,
  ToggleButton,
  ToggleButtonGroup,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Typography,
  Autocomplete,
  CircularProgress,
  IconButton,
  Tooltip,
  Alert,
  ListSubheader,
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import { HAContext, API_ENDPOINTS } from '../../App'
import {
  fetchHAEntities,
  filterEntitiesByDomain,
  groupEntitiesByDomain,
  formatEntityLabel,
  getCachedEntities,
  type HAEntityOption,
} from '../../services/homeassistant'

/**
 * Custom listbox component that shows entity count in header
 */
const ListboxComponent = forwardRef<HTMLUListElement, React.HTMLAttributes<HTMLElement> & { entityCount?: number }>(function ListboxComponent(props, ref) {
  const { children, entityCount, ...other } = props
  return (
    <ul {...other} ref={ref}>
      {entityCount !== undefined && entityCount > 0 && (
        <ListSubheader sx={{ lineHeight: '32px', fontWeight: 600, bgcolor: 'action.hover' }}>
          {entityCount} {entityCount === 1 ? 'entity' : 'entities'} available
        </ListSubheader>
      )}
      {children}
    </ul>
  )
})

interface EntityPickerOrEnumRendererProps extends ControlProps {
  data: string | undefined
}

const EntityPickerOrEnumRenderer: React.FC<EntityPickerOrEnumRendererProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
}) => {
  const { config: haConfig, secrets } = useContext(HAContext)
  const help = uischema?.options?.help || description
  const enumValues = uischema?.options?.enumValues || []
  const widgetFilter = uischema?.options?.widgetFilter
  
  // Entity picker state
  const [entities, setEntities] = useState<HAEntityOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  
  // Determine initial mode based on data
  // Default to 'enum' mode unless data contains an entity ID (non-enum value)
  const isEnumValue = enumValues.includes(data)
  const hasEntityId = data && !isEnumValue
  const [mode, setMode] = useState<'enum' | 'entity'>(
    hasEntityId ? 'entity' : 'enum'
  )

  const handleModeChange = (_: React.MouseEvent, newMode: 'enum' | 'entity' | null) => {
    if (newMode) {
      setMode(newMode)
      // When switching to enum, use first value; when switching to entity, clear
      handleChange(path, newMode === 'enum' ? (enumValues[0] || '') : '')
    }
  }

  /**
   * Load entities from Home Assistant
   */
  const loadEntities = async (forceRefresh = false) => {
    // Check cache first
    if (!forceRefresh) {
      const cached = getCachedEntities()
      if (cached) {
        const filtered = filterEntitiesByDomain(cached, widgetFilter)
        setEntities(filtered)
        return
      }
    }
    
    setLoading(true)
    setError(null)
    
    try {
      const allEntities = await fetchHAEntities(API_ENDPOINTS.HA_STATES, haConfig, secrets)
      const filtered = filterEntitiesByDomain(allEntities, widgetFilter)
      setEntities(filtered)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load entities'
      setError(errorMsg)
      console.error('Failed to fetch HA entities:', err)
    } finally {
      setLoading(false)
    }
  }

  /**
   * Handle autocomplete open - load entities on demand
   */
  const handleOpen = () => {
    setOpen(true)
    if (entities.length === 0 && !error) {
      loadEntities()
    }
  }

  /**
   * Handle autocomplete close
   */
  const handleClose = () => {
    setOpen(false)
  }

  /**
   * Handle refresh button click
   */
  const handleRefresh = () => {
    loadEntities(true)
  }

  // Group entities by domain for organized display
  const groupedEntities = entities.length > 0 ? groupEntitiesByDomain(entities) : {}
  const sortedDomains = Object.keys(groupedEntities).sort()

  // Flatten for autocomplete options with group info
  const options: (HAEntityOption | { header: string })[] = []
  sortedDomains.forEach(domain => {
    options.push({ header: domain })
    options.push(...groupedEntities[domain])
  })

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
        <ToggleButton value="enum">Select</ToggleButton>
        <ToggleButton value="entity">Entity</ToggleButton>
      </ToggleButtonGroup>

      {mode === 'enum' ? (
        <FormControl fullWidth size="small">
          <InputLabel>{label}</InputLabel>
          <Select
            value={data && enumValues.includes(data) ? data : (enumValues[0] || '')}
            onChange={(e) => handleChange(path, e.target.value)}
            label={label}
          >
            {enumValues.map((value: string) => (
              <MenuItem key={value} value={value}>
                {value}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      ) : (
        <>
          {error && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              {error}
              <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                You can still enter an entity ID manually.
              </Typography>
            </Alert>
          )}
          
          <Autocomplete
            open={open}
            onOpen={handleOpen}
            onClose={handleClose}
            value={data || null}
            onChange={(_, newValue) => {
              if (typeof newValue === 'string') {
                handleChange(path, newValue || null)
              } else if (newValue && 'entity_id' in newValue) {
                handleChange(path, newValue.entity_id || null)
              } else {
                handleChange(path, null)
              }
            }}
            inputValue={data || ''}
            onInputChange={(_, newInputValue) => {
              handleChange(path, newInputValue || null)
            }}
            options={options}
            getOptionLabel={(option) => {
              if (typeof option === 'string') return option
              if ('header' in option) return ''
              return option.entity_id
            }}
            renderOption={(props, option) => {
              if ('header' in option) {
                return (
                  <ListSubheader key={option.header} sx={{ lineHeight: '32px' }}>
                    {option.header}
                  </ListSubheader>
                )
              }
              return (
                <li {...props} key={option.entity_id}>
                  <Box>
                    <Typography variant="body2">{formatEntityLabel(option)}</Typography>
                  </Box>
                </li>
              )
            }}
            renderInput={(params) => (
              <TextField
                {...params}
                placeholder="Select entity or type entity ID..."
                size="small"
                label="Entity"
                InputProps={{
                  ...params.InputProps,
                  endAdornment: (
                    <>
                      {loading ? <CircularProgress color="inherit" size={20} /> : null}
                      {entities.length > 0 && (
                        <Tooltip title="Refresh entities" arrow>
                          <IconButton
                            size="small"
                            onClick={handleRefresh}
                            disabled={loading}
                            edge="end"
                            sx={{ mr: 0.5 }}
                          >
                            <RefreshIcon sx={{ fontSize: 18 }} />
                          </IconButton>
                        </Tooltip>
                      )}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                }}
              />
            )}
            ListboxComponent={ListboxComponent}
            slotProps={{
              listbox: {
                entityCount: entities.length,
              } as any,
            }}
            freeSolo
            clearOnBlur={false}
            selectOnFocus
            handleHomeEndKeys
            loading={loading}
            filterOptions={(x) => x}
            isOptionEqualToValue={(option, value) => {
              if (typeof option === 'string' && typeof value === 'string') {
                return option === value
              }
              if (typeof option === 'object' && 'entity_id' in option && typeof value === 'string') {
                return option.entity_id === value
              }
              return false
            }}
          />
        </>
      )}
    </Box>
  )
}

// Tester for FlexEnum type (detected via refType in UISchema options)
export const entityPickerOrEnumTester = rankWith(
  15, // Higher priority than standard enum renderer
  (uischema) => {
    // Check if this is a FlexEnum by looking at refType preserved in UISchema options
    return uischema.options?.refType === 'FlexEnum'
  }
)

export default withJsonFormsControlProps(EntityPickerOrEnumRenderer)
