import React, { useState, useEffect } from 'react';
import { JsonForms } from '@jsonforms/react';
import {
  materialRenderers,
  materialCells,
} from '@jsonforms/material-renderers';
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  Container,
  Paper,
  AppBar,
  Toolbar,
  Typography,
  Button,
  Box,
  Alert,
  Snackbar,
  CircularProgress,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import RefreshIcon from '@mui/icons-material/Refresh';
import { uiSchema } from './uiSchema';
import { haEntityRendererEntry } from './haEntityRenderer';
import { secretRendererEntry } from './secretRenderer';
import './App.css';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

function App() {
  const [schema, setSchema] = useState(null);
  const [data, setData] = useState({});
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });

  // Load schema and data on mount
  useEffect(() => {
    loadConfiguration();
  }, []);

  const loadConfiguration = async () => {
    setLoading(true);
    try {
      // Load schema via API endpoint
      const schemaResponse = await fetch('/api/schema');
      
      if (!schemaResponse.ok) {
        throw new Error(`Failed to load schema: ${schemaResponse.status} ${schemaResponse.statusText}`);
      }
      
      const schemaData = await schemaResponse.json();
      setSchema(schemaData);

      // Load current configuration
      const configResponse = await fetch('/api/settings/options.json');
      if (configResponse.ok) {
        const configData = await configResponse.json();
        setData(configData);
      } else {
        showNotification('Failed to load configuration', 'error');
      }
    } catch (error) {
      console.error('Error loading configuration:', error);
      showNotification('Error loading configuration: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch('/api/settings/options.json', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      if (response.ok) {
        showNotification('Configuration saved successfully', 'success');
      } else {
        const errorData = await response.json();
        showNotification('Failed to save: ' + (errorData.error || 'Unknown error'), 'error');
      }
    } catch (error) {
      console.error('Error saving configuration:', error);
      showNotification('Error saving configuration: ' + error.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = () => {
    const dataStr = JSON.stringify(data, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'options.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showNotification('Configuration downloaded', 'success');
  };

  const handleUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const uploadedData = JSON.parse(e.target.result);
        setData(uploadedData);
        showNotification('Configuration loaded from file', 'success');
      } catch (error) {
        showNotification('Invalid JSON file: ' + error.message, 'error');
      }
    };
    reader.readAsText(file);
    event.target.value = ''; // Reset input
  };

  const showNotification = (message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  };

  const handleCloseNotification = () => {
    setNotification({ ...notification, open: false });
  };

  if (loading || !schema) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
          <CircularProgress />
        </Box>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Day Ahead Optimizer - Configuration
            </Typography>
            <Button
              color="inherit"
              startIcon={<RefreshIcon />}
              onClick={loadConfiguration}
              disabled={loading}
            >
              Reload
            </Button>
            <input
              accept=".json"
              style={{ display: 'none' }}
              id="upload-button"
              type="file"
              onChange={handleUpload}
            />
            <label htmlFor="upload-button">
              <Button
                color="inherit"
                component="span"
                startIcon={<UploadIcon />}
              >
                Upload
              </Button>
            </label>
            <Button
              color="inherit"
              startIcon={<DownloadIcon />}
              onClick={handleDownload}
            >
              Download
            </Button>
            <Button
              color="inherit"
              startIcon={<SaveIcon />}
              onClick={handleSave}
              disabled={saving || errors.length > 0}
            >
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </Toolbar>
        </AppBar>

        <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
          {errors.length > 0 && (
            <Alert severity="error" sx={{ mb: 2 }}>
              <Typography variant="h6">Validation Errors:</Typography>
              <ul>
                {errors.map((error, index) => (
                  <li key={index}>{error.message}</li>
                ))}
              </ul>
            </Alert>
          )}

          <Paper sx={{ p: 3 }}>
            <JsonForms
              schema={schema}
              uischema={uiSchema}
              data={data}
              renderers={[
                haEntityRendererEntry,
                secretRendererEntry,
                ...materialRenderers
              ]}
              cells={materialCells}
              onChange={({ data, errors }) => {
                setData(data);
                setErrors(errors || []);
              }}
            />
          </Paper>
        </Container>

        <Snackbar
          open={notification.open}
          autoHideDuration={6000}
          onClose={handleCloseNotification}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert
            onClose={handleCloseNotification}
            severity={notification.severity}
            sx={{ width: '100%' }}
          >
            {notification.message}
          </Alert>
        </Snackbar>
      </Box>
    </ThemeProvider>
  );
}

export default App;
