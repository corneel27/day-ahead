import React, { useState } from 'react'
import {
  Box,
  TextField,
  IconButton,
  Button,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  InputAdornment,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import AddIcon from '@mui/icons-material/Add'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'

interface SecretsEditorProps {
  secrets: Record<string, string>
  onChange: (secrets: Record<string, string>) => void
}

export const SecretsEditor: React.FC<SecretsEditorProps> = ({ secrets, onChange }) => {
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [visibleSecrets, setVisibleSecrets] = useState<Set<string>>(new Set())

  const handleAdd = () => {
    if (newKey && newValue) {
      onChange({
        ...secrets,
        [newKey]: newValue
      })
      setNewKey('')
      setNewValue('')
    }
  }

  const handleDelete = (key: string) => {
    const newSecrets = { ...secrets }
    delete newSecrets[key]
    onChange(newSecrets)
  }

  const handleUpdate = (key: string, value: string) => {
    onChange({
      ...secrets,
      [key]: value
    })
  }

  const toggleVisibility = (key: string) => {
    const newVisible = new Set(visibleSecrets)
    if (newVisible.has(key)) {
      newVisible.delete(key)
    } else {
      newVisible.add(key)
    }
    setVisibleSecrets(newVisible)
  }

  const secretEntries = Object.entries(secrets)

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {secretEntries.length === 0 
          ? 'No secrets defined. Add your first secret below.'
          : `${secretEntries.length} secret${secretEntries.length !== 1 ? 's' : ''} defined`
        }
      </Typography>

      {secretEntries.length > 0 && (
        <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Key</TableCell>
                <TableCell>Value</TableCell>
                <TableCell width={100}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {secretEntries.map(([key, value]) => (
                <TableRow key={key}>
                  <TableCell>
                    <Typography variant="body2" fontFamily="monospace">
                      {key}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <TextField
                      type={visibleSecrets.has(key) ? 'text' : 'password'}
                      value={value}
                      onChange={(e) => handleUpdate(key, e.target.value)}
                      size="small"
                      fullWidth
                      InputProps={{
                        endAdornment: (
                          <InputAdornment position="end">
                            <IconButton
                              size="small"
                              onClick={() => toggleVisibility(key)}
                              edge="end"
                            >
                              {visibleSecrets.has(key) ? <VisibilityOffIcon /> : <VisibilityIcon />}
                            </IconButton>
                          </InputAdornment>
                        ),
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => handleDelete(key)}
                    >
                      <DeleteIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
        <Typography variant="subtitle2" gutterBottom>
          Add New Secret
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
          <TextField
            label="Key"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            size="small"
            placeholder="e.g., ha_token"
            sx={{ flex: 1 }}
          />
          <TextField
            label="Value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            size="small"
            type="password"
            placeholder="Secret value"
            sx={{ flex: 2 }}
          />
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
            disabled={!newKey || !newValue}
          >
            Add
          </Button>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Keys should be descriptive (e.g., tibber_api_key, db_password). Use in config as: !secret key_name
        </Typography>
      </Paper>
    </Box>
  )
}
