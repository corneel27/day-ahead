import React, { Component, ReactNode } from 'react'
import { Box, Container, Typography, Paper, Button, Alert } from '@mui/material'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import RefreshIcon from '@mui/icons-material/Refresh'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: React.ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    this.setState({
      error,
      errorInfo
    })
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <Container maxWidth="md" sx={{ mt: 8 }}>
          <Paper elevation={3} sx={{ p: 4 }}>
            <Box display="flex" flexDirection="column" alignItems="center" gap={3}>
              <ErrorOutlineIcon sx={{ fontSize: 64, color: 'error.main' }} />
              
              <Typography variant="h4" component="h1" gutterBottom>
                Something went wrong
              </Typography>
              
              <Typography variant="body1" color="text.secondary" align="center">
                An unexpected error occurred in the configuration interface. 
                Please try reloading the page.
              </Typography>

              {this.state.error && (
                <Alert severity="error" sx={{ width: '100%', mt: 2 }}>
                  <Typography variant="body2" component="pre" sx={{ 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-word',
                    fontFamily: 'monospace',
                    fontSize: '0.875rem'
                  }}>
                    {this.state.error.toString()}
                  </Typography>
                </Alert>
              )}

              {process.env.NODE_ENV === 'development' && this.state.errorInfo && (
                <Alert severity="info" sx={{ width: '100%', mt: 1 }}>
                  <Typography variant="caption" component="pre" sx={{ 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-word',
                    fontFamily: 'monospace',
                    fontSize: '0.75rem',
                    maxHeight: '200px',
                    overflow: 'auto'
                  }}>
                    {this.state.errorInfo.componentStack}
                  </Typography>
                </Alert>
              )}

              <Button
                variant="contained"
                color="primary"
                size="large"
                startIcon={<RefreshIcon />}
                onClick={this.handleReload}
                sx={{ mt: 2 }}
              >
                Reload Page
              </Button>
            </Box>
          </Paper>
        </Container>
      )
    }

    return this.props.children
  }
}
