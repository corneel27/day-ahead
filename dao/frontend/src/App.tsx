import { useState, useEffect, createContext } from 'react'
import { JsonForms } from '@jsonforms/react'
import { materialCells } from '@jsonforms/material-renderers'
import { allRenderers } from './components/renderers'
import { SecretsEditor } from './components/SecretsEditor'
import { useThemeMode } from './theme'
import './App.css'
import { 
  Box, 
  Container, 
  Typography, 
  Paper, 
  CircularProgress,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Toolbar,
  AppBar,
  Tabs,
  Tab,
  Alert,
  Tooltip,
  Snackbar,
  AlertTitle,
  List,
  ListItem,
  ListItemText
} from '@mui/material'
import SaveIcon from '@mui/icons-material/Save'
import LockIcon from '@mui/icons-material/Lock'
import UndoIcon from '@mui/icons-material/Undo'
import CloseIcon from '@mui/icons-material/Close'
import CodeIcon from '@mui/icons-material/Code'
import Brightness4Icon from '@mui/icons-material/Brightness4'
import Brightness7Icon from '@mui/icons-material/Brightness7'
import BrightnessAutoIcon from '@mui/icons-material/BrightnessAuto'
import { createAjv } from '@jsonforms/core'
import type { HAConnectionConfig } from './services/homeassistant'

// API Configuration
// In development: proxied through Vite to backend
// In production: backend API handles this endpoint
export const API_ENDPOINTS = {
  HA_STATES: '/api/v2/ha-proxy/states', // GET - Fetch all HA entities via backend proxy
} as const

// Context to share secrets with renderers
export const SecretsContext = createContext<{ secrets: Record<string, string> }>({
  secrets: {}
})

// Context to share Home Assistant connection config with renderers
export const HAContext = createContext<{
  config: HAConnectionConfig
  secrets: Record<string, string>
}>({
  config: {},
  secrets: {}
})

interface UISchema {
  type: string
  [key: string]: any
}

interface Schema {
  type: string
  [key: string]: any
}

interface ConfigData {
  [key: string]: any
}

function App() {
  const { mode, toggleTheme, isSystemDefault } = useThemeMode()
  const [uischema, setUISchema] = useState<UISchema | null>(null)
  const [schema, setSchema] = useState<Schema | null>(null)
  const [data, setData] = useState<ConfigData>({
    // Infrastructure
    grid: {
      max_power: 17
    },
    // Pricing
    pricing: {
      source_day_ahead: 'nordpool',
      entsoe_api_key: null,
      energy_taxes_consumption: { '2024-01-01': 0.05 },
      energy_taxes_production: { '2024-01-01': 0.0 },
      cost_supplier_consumption: { '2024-01-01': 0.02 },
      cost_supplier_production: { '2024-01-01': -0.02 },
      vat_consumption: { '2024-01-01': 21 },
      vat_production: { '2024-01-01': 21 },
      last_invoice: '2025-12-03',
      tax_refund: false
    },
    // Integration
    homeassistant: {
      ip_address: 'homeassistant.local',
      ip_port: 8123,
      hasstoken: '',
      protocol_api: 'http'
    },
    // Energy Storage - array of batteries
    battery: [],
    // Energy Production - array of solar configs
    solar: [],
    // Devices
    electric_vehicle: [],
    machines: []
  })
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [originalSecrets, setOriginalSecrets] = useState<Record<string, string>>({})
  const [originalData, setOriginalData] = useState<any>(null)
  const [currentCategory, setCurrentCategory] = useState<string>('General')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showConfigDialog, setShowConfigDialog] = useState(false)
  
  // Snackbar state for notifications
  const [snackbar, setSnackbar] = useState<{
    open: boolean
    message: string
    severity: 'success' | 'error' | 'warning' | 'info'
    details?: string[]
  }>({
    open: false,
    message: '',
    severity: 'info'
  })
  
  // Revert confirmation dialog state
  const [showRevertDialog, setShowRevertDialog] = useState(false)

  useEffect(() => {
    // Load schemas, config, and secrets
    Promise.all([
      fetch('/api/v2/config/uischema').then(r => r.json()),
      fetch('/api/v2/config/schema').then(r => r.json()),
      fetch('/api/v2/config').then(r => r.json()),
      fetch('/api/v2/secrets').then(r => r.json()).catch(() => ({}))
    ])
      .then(([uischemaData, schemaData, configData, secretsData]) => {
        // Add Secrets category to UISchema
        const enhancedUISchema = {
          ...uischemaData,
          elements: [
            ...(uischemaData.elements || []),
            {
              type: 'Category',
              label: 'Secrets',
              elements: [
                {
                  type: 'VerticalLayout',
                  elements: [] // Empty but required for proper rendering
                }
              ]
            }
          ]
        }
        setUISchema(enhancedUISchema)
        setSchema(schemaData)
        setData(configData)
        setOriginalData(configData)
        setSecrets(secretsData)
        setOriginalSecrets(secretsData)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  // Style the Secrets tab with background color and track tab changes
  useEffect(() => {
    const styleSecretsTab = () => {
      const tabs = document.querySelectorAll('.MuiTab-root')
      tabs.forEach(tab => {
        if (tab.textContent === 'Secrets' && tab instanceof HTMLElement) {
          tab.style.backgroundColor = 'rgba(244, 67, 54, 0.1)' // Light red background
          tab.style.borderRadius = '4px'
          tab.style.margin = '0 2px'
        }
      })
    }
    
    // Track tab changes
    const trackTabChange = () => {
      const activeTab = document.querySelector('.MuiTab-root.Mui-selected')
      if (activeTab) {
        const categoryLabel = activeTab.textContent || ''
        if (categoryLabel && currentCategory !== categoryLabel) {
          setCurrentCategory(categoryLabel)
        }
      }
    }
    
    const timer = setTimeout(() => {
      styleSecretsTab()
      trackTabChange()
    }, 100)
    
    const interval = setInterval(() => {
      styleSecretsTab()
      trackTabChange()
    }, 300)
    
    // Add click listeners to tabs
    const tabs = document.querySelectorAll('.MuiTab-root')
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        setTimeout(trackTabChange, 50)
      })
    })
    
    return () => {
      clearTimeout(timer)
      clearInterval(interval)
    }
  }, [uischema, currentCategory])

  const secretsChanged = JSON.stringify(secrets) !== JSON.stringify(originalSecrets)
  const configChanged = originalData ? JSON.stringify(data) !== JSON.stringify(originalData) : false
  const hasUnsavedChanges = secretsChanged || configChanged

  // Warn user before navigating away with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault()
        // Modern browsers require returnValue to be set
        e.returnValue = ''
        return ''
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [hasUnsavedChanges])

  const handleConfigChange = (state: { data: any }) => {
    setData(state.data)
  }

  const handleSecretsChange = (newSecrets: Record<string, string>) => {
    setSecrets(newSecrets)
  }
  
  // Helper function to show snackbar notifications
  const showNotification = (message: string, severity: 'success' | 'error' | 'warning' | 'info', details?: string[]) => {
    setSnackbar({ open: true, message, severity, details })
  }
  
  const closeSnackbar = () => {
    setSnackbar({ ...snackbar, open: false })
  }
  
  // Show revert confirmation dialog
  const handleRevert = () => {
    setShowRevertDialog(true)
  }
  
  // Execute revert after confirmation
  const handleRevertConfirmed = async () => {
    setShowRevertDialog(false)
    
    // Reload config and secrets from disk (discard unsaved changes)
    try {
      const [configResponse, secretsResponse] = await Promise.all([
        fetch('/api/v2/config'),
        fetch('/api/v2/secrets')
      ])
      
      if (configResponse.ok) {
        const freshConfig = await configResponse.json()
        setData(freshConfig)
        setOriginalData(freshConfig)
      }
      
      if (secretsResponse.ok) {
        const freshSecrets = await secretsResponse.json()
        setSecrets(freshSecrets)
        setOriginalSecrets(freshSecrets)
      }
      
      console.log('Reverted to saved config')
      showNotification('Reverted to saved configuration', 'info')
    } catch (err) {
      console.error('Failed to revert:', err)
      showNotification(
        'Failed to revert changes: ' + (err instanceof Error ? err.message : 'Unknown error'),
        'error'
      )
    }
  }
  
  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      const response = await fetch('/api/v2/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      })
      
      if (!response.ok) {
        const error = await response.json()
        console.error('Failed to save config:', error)
        showNotification(
          error.error || 'Failed to save configuration',
          'error',
          error.details || []
        )
        return
      }
      
      // Update original data after successful save
      setOriginalData(data)
      showNotification('Configuration saved successfully', 'success')
    } catch (err) {
      console.error('Failed to save config:', err)
      showNotification(
        'Failed to save configuration: ' + (err instanceof Error ? err.message : 'Unknown error'),
        'error'
      )
    } finally {
      setSaving(false)
    }
  }

  const handleSaveSecrets = async () => {
    setSaving(true)
    try {
      // Save secrets to backend
      const saveResponse = await fetch('/api/v2/secrets', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(secrets),
      })
      
      if (!saveResponse.ok) {
        const error = await saveResponse.json()
        console.error('Failed to save secrets:', error)
        showNotification(
          error.error || 'Failed to save secrets',
          'error',
          error.details || []
        )
        return
      }
      
      // Reload secrets to ensure we have latest
      const response = await fetch('/api/v2/secrets')
      if (response.ok) {
        const freshSecrets = await response.json()
        setSecrets(freshSecrets)
        setOriginalSecrets(freshSecrets)
      }
      
      showNotification('Secrets saved successfully', 'success')
    } catch (err) {
      console.error('Failed to save/reload secrets:', err)
      showNotification(
        'Failed to save secrets: ' + (err instanceof Error ? err.message : 'Unknown error'),
        'error'
      )
    } finally {
      setSaving(false)
    }
  }

  const handleCloseConfigDialog = () => {
    setShowConfigDialog(false)
  }

  const handleCopyConfig = () => {
    const jsonString = JSON.stringify(data, null, 2)
    
    navigator.clipboard.writeText(jsonString)
      .then(() => {
        console.log(`${type} copied to clipboard`)
      })
      .catch(err => {
        console.error('Failed to copy:', err)
      })
  }

  if (loading) {
    return (
      <Container maxWidth="md" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography sx={{ mt: 2 }}>Loading configuration...</Typography>
      </Container>
    )
  }

  if (error) {
    return (
      <Container maxWidth="md" sx={{ mt: 4 }}>
        <Paper sx={{ p: 3, bgcolor: 'error.light' }}>
          <Typography color="error">Error loading configuration: {error}</Typography>
        </Paper>
      </Container>
    )
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top toolbar with action buttons */}
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar sx={{ justifyContent: 'space-between', gap: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Tooltip title={isSystemDefault ? 'Theme: System Default' : mode === 'dark' ? 'Theme: Dark' : 'Theme: Light'}>
              <IconButton onClick={toggleTheme} color="inherit" size="small">
                {isSystemDefault ? (
                  <BrightnessAutoIcon />
                ) : mode === 'dark' ? (
                  <Brightness4Icon />
                ) : (
                  <Brightness7Icon />
                )}
              </IconButton>
            </Tooltip>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              startIcon={<UndoIcon />}
              onClick={handleRevert}
              variant="outlined"
              size="small"
              disabled={saving}
            >
              Revert
            </Button>
            <Button
              startIcon={<CodeIcon />}
              onClick={() => setShowConfigDialog(true)}
              variant="outlined"
              size="small"
            >
              Show Configuration
            </Button>
            {currentCategory === 'Secrets' && secretsChanged ? (
              <Button
                startIcon={<LockIcon />}
                onClick={handleSaveSecrets}
                variant="contained"
                size="small"
                color="warning"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Secrets'}
              </Button>
            ) : (
              <Button
                startIcon={<SaveIcon />}
                onClick={handleSaveConfig}
                variant="contained"
                size="small"
                color="primary"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Configuration'}
              </Button>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      {/* Form content */}
      <Box sx={{ flex: 1, overflow: 'auto', position: 'relative' }}>
        <SecretsContext.Provider value={{ secrets }}>
          <HAContext.Provider value={{
            config: {
              host: data.homeassistant?.host || data.homeassistant?.ip_address || null,
              port: data.homeassistant?.ip_port || null,
              token: data.homeassistant?.token || data.homeassistant?.hasstoken || null,
              protocol: data.homeassistant?.protocol_api || null
            },
            secrets
          }}>
            {uischema && schema && (
              <Box 
                className="jsonforms-wrapper"
                sx={{ 
                  position: 'relative',
                  '& > div > .MuiPaper-root:first-of-type, & > div > .MuiAppBar-root:first-of-type': {
                    position: 'sticky',
                    top: 0,
                    zIndex: 1100,
                    backgroundColor: 'background.paper',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                  }
                }}
              >
                <JsonForms
                  schema={schema}
                  uischema={uischema}
                  data={data}
                  renderers={allRenderers}
                  cells={materialCells}
                  onChange={(state) => {
                    handleConfigChange(state)
                    // Track category changes
                    const activeTab = document.querySelector('.MuiTab-root.Mui-selected')
                    if (activeTab) {
                      const categoryLabel = activeTab.textContent || ''
                      if (categoryLabel && currentCategory !== categoryLabel) {
                        setCurrentCategory(categoryLabel)
                      }
                    }
                  }}
                  ajv={createAjv()}
                />
                {/* Render Secrets Editor when Secrets tab is active */}
                {currentCategory === 'Secrets' && (
                  <Container maxWidth="md" sx={{ mt: 4, mb: 4 }}>
                    <Alert 
                      severity="info" 
                      icon={<LockIcon />}
                      sx={{ mb: 3 }}
                    >
                      <Typography variant="body2" fontWeight="medium">
                        Secrets are stored separately in <code>secrets.json</code>
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Changes to secrets require saving before they can be used in configuration fields.
                        Use the "Save Secrets" button above when you have made changes.
                      </Typography>
                    </Alert>
                    <Paper sx={{ p: 3 }}>
                      <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LockIcon color="warning" />
                        Secrets Management
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                        Manage secret values referenced in your configuration using !secret key_name.
                      </Typography>
                      <SecretsEditor 
                        secrets={secrets}
                        onChange={handleSecretsChange}
                      />
                    </Paper>
                  </Container>
                )}
              </Box>
            )}
          </HAContext.Provider>
        </SecretsContext.Provider>
      </Box>

      {/* Revert confirmation dialog */}
      <Dialog 
        open={showRevertDialog} 
        onClose={() => setShowRevertDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Confirm Revert</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This will discard all unsaved changes and reload the configuration from disk.
          </Alert>
          <Typography>
            Are you sure you want to revert to the last saved configuration?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowRevertDialog(false)} variant="outlined">
            Cancel
          </Button>
          <Button onClick={handleRevertConfirmed} variant="contained" color="warning">
            Revert Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Show Configuration dialog */}
      <Dialog 
        open={showConfigDialog} 
        onClose={handleCloseConfigDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Configuration JSON
          <IconButton
            aria-label="close"
            onClick={handleCloseConfigDialog}
            sx={{
              position: 'absolute',
              right: 8,
              top: 8,
            }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Paper 
            sx={{ 
              p: 2, 
              bgcolor: mode === 'dark' ? 'background.default' : 'grey.100',
              maxHeight: '60vh',
              overflow: 'auto'
            }}
          >
            <pre style={{ margin: 0, fontSize: '0.875rem', fontFamily: 'monospace' }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          </Paper>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCopyConfig} variant="outlined">
            Copy to Clipboard
          </Button>
          <Button onClick={handleCloseConfigDialog} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* Snackbar for notifications */}
      <Snackbar 
        open={snackbar.open} 
        autoHideDuration={6000} 
        onClose={closeSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={closeSnackbar} 
          severity={snackbar.severity} 
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.details && snackbar.details.length > 0 ? (
            <>
              <AlertTitle>{snackbar.message}</AlertTitle>
              <List dense>
                {snackbar.details.map((detail, index) => (
                  <ListItem key={index} disableGutters>
                    <ListItemText 
                      primary={detail} 
                      primaryTypographyProps={{ variant: 'body2' }}
                    />
                  </ListItem>
                ))}
              </List>
            </>
          ) : (
            snackbar.message
          )}
        </Alert>
      </Snackbar>
    </Box>
  )
}

export default App
