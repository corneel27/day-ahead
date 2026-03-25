import React, { createContext, useContext, useState, useMemo } from 'react'
import { ThemeProvider, createTheme, useMediaQuery, CssBaseline } from '@mui/material'
import type { PaletteMode } from '@mui/material'

interface ThemeContextType {
  mode: PaletteMode
  toggleTheme: () => void
  isSystemDefault: boolean
}

const ThemeContext = createContext<ThemeContextType>({
  mode: 'light',
  toggleTheme: () => {},
  isSystemDefault: true
})

export const useThemeMode = () => useContext(ThemeContext)

const THEME_STORAGE_KEY = 'config-editor-theme-preference'

interface AppThemeProviderProps {
  children: React.ReactNode
}

export const AppThemeProvider: React.FC<AppThemeProviderProps> = ({ children }) => {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)')
  
  // Get stored preference (null means follow system)
  const [themePreference, setThemePreference] = useState<PaletteMode | null>(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : null
  })

  // Determine actual mode: use preference if set, otherwise follow system
  const mode: PaletteMode = themePreference ?? (prefersDarkMode ? 'dark' : 'light')
  const isSystemDefault = themePreference === null

  const toggleTheme = () => {
    if (isSystemDefault) {
      // First toggle: explicitly set opposite of current system preference
      const newMode: PaletteMode = prefersDarkMode ? 'light' : 'dark'
      setThemePreference(newMode)
      localStorage.setItem(THEME_STORAGE_KEY, newMode)
    } else if (themePreference === 'dark') {
      // Dark → Light
      setThemePreference('light')
      localStorage.setItem(THEME_STORAGE_KEY, 'light')
    } else {
      // Light → System default
      setThemePreference(null)
      localStorage.removeItem(THEME_STORAGE_KEY)
    }
  }

  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode,
          ...(mode === 'dark'
            ? {
                // Dark mode colors
                primary: {
                  main: '#90caf9',
                },
                secondary: {
                  main: '#f48fb1',
                },
                background: {
                  default: '#121212',
                  paper: '#1e1e1e',
                },
              }
            : {
                // Light mode colors
                primary: {
                  main: '#1976d2',
                },
                secondary: {
                  main: '#dc004e',
                },
                background: {
                  default: '#fafafa',
                  paper: '#ffffff',
                },
              }),
        },
        components: {
          MuiAppBar: {
            styleOverrides: {
              root: {
                backgroundColor: mode === 'dark' ? '#1e1e1e' : '#ffffff',
              },
            },
          },
          MuiPaper: {
            styleOverrides: {
              root: {
                backgroundImage: 'none', // Remove MUI's default gradient in dark mode
              },
            },
          },
        },
      }),
    [mode]
  )

  return (
    <ThemeContext.Provider value={{ mode, toggleTheme, isSystemDefault }}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeContext.Provider>
  )
}
