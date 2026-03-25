import React from 'react'
import {
  ControlProps,
  rankWith,
  schemaMatches,
} from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  TextField,
  Button,
  Box,
  Typography,
  Tooltip,
  Link,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import AddIcon from '@mui/icons-material/Add'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'

interface DateDictRendererProps extends ControlProps {
  data: { [key: string]: number } | undefined
}

const DateDictRenderer: React.FC<DateDictRendererProps> = ({
  data,
  handleChange,
  path,
  label,
  description,
  uischema,
}) => {
  const entries = Object.entries(data || {})
  const unit = uischema?.options?.unit || ''
  const help = uischema?.options?.help || description
  const docsUrl = uischema?.options?.docsUrl

  const handleDateChange = (oldDate: string, newDate: string) => {
    if (!data) return
    const newData = { ...data }
    if (oldDate !== newDate) {
      newData[newDate] = newData[oldDate]
      delete newData[oldDate]
    }
    handleChange(path, newData)
  }

  const handleValueChange = (date: string, value: string) => {
    const numValue = parseFloat(value)
    if (isNaN(numValue)) return
    handleChange(path, { ...data, [date]: numValue })
  }

  const handleAdd = () => {
    const today = new Date().toISOString().split('T')[0]
    handleChange(path, { ...data, [today]: 0 })
  }

  const handleDelete = (date: string) => {
    if (!data) return
    const newData = { ...data }
    delete newData[date]
    handleChange(path, newData)
  }

  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
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
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      )}
      
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Date (YYYY-MM-DD)</TableCell>
              <TableCell>Value {unit && `(${unit})`}</TableCell>
              <TableCell width={60}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {entries.map(([date, value]) => (
              <TableRow key={date}>
                <TableCell>
                  <TextField
                    type="date"
                    value={date}
                    onChange={(e) => handleDateChange(date, e.target.value)}
                    size="small"
                    fullWidth
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    type="number"
                    value={value}
                    onChange={(e) => handleValueChange(date, e.target.value)}
                    size="small"
                    fullWidth
                    inputProps={{ step: 0.01 }}
                  />
                </TableCell>
                <TableCell>
                  <IconButton
                    size="small"
                    onClick={() => handleDelete(date)}
                    color="error"
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {entries.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} align="center">
                  <Typography variant="body2" color="text.secondary">
                    No entries. Click "Add Entry" to start.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      
      <Button
        startIcon={<AddIcon />}
        onClick={handleAdd}
        sx={{ mt: 1 }}
        variant="outlined"
        size="small"
      >
        Add Entry
      </Button>
    </Box>
  )
}

// Tester that matches object types with string keys and number values
export const dateDictTester = rankWith(
  5,
  schemaMatches((schema) => {
    return (
      schema.type === 'object' &&
      schema.additionalProperties !== false &&
      !schema.properties // No fixed properties, just key-value pairs
    )
  })
)

export default withJsonFormsControlProps(DateDictRenderer)
