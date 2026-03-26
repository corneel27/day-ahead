# Day Ahead Config UI - Developer Guide

This guide covers development setup, workflow, and troubleshooting for the Day Ahead Optimizer configuration UI frontend.

## Overview

The configuration UI is a React + TypeScript application built with:
- **React 18.3** - UI framework
- **Material-UI (MUI) v7** - Component library
- **JSONForms 3.4** - Dynamic form generation from JSON Schema
- **Vite 7** - Build tool and development server
- **TypeScript 5.5** - Type safety

## Prerequisites

### Required Software

1. **Node.js 24 LTS** (or later)
   ```bash
   # Check version
   node --version  # Should be v24.x or later
   ```
   
   Installation:
   - macOS: `brew install node@24`
   - Linux: Follow [NodeSource instructions](https://github.com/nodesource/distributions)
   - Windows: Download from [nodejs.org](https://nodejs.org/)

2. **pnpm 10.x** (package manager)
   ```bash
   # Install globally
   npm install -g pnpm
   
   # Check version
   pnpm --version  # Should be 10.x
   ```

3. **Python 3.11+** with venv (for backend)
   ```bash
   python3 --version  # Should be 3.11 or later
   ```

## Initial Setup

### 1. Clone Repository and Navigate to Frontend

```bash
cd /path/to/day-ahead/dao/frontend
```

### 2. Install Dependencies

```bash
# Install all Node dependencies
pnpm install
```

This installs all packages from `package.json` using the locked versions in `pnpm-lock.yaml`.

### 3. Set Up Backend (Required for Development)

The frontend requires the Flask backend to be running for API calls:

```bash
# Open a new terminal
cd /path/to/day-ahead

# Create Python virtual environment (first time only)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate  # Windows

# Install Python dependencies
pip install -r dao/requirements.txt

# Generate schemas (required for config UI)
python scripts/generate_uischema.py

# Start Flask backend
cd dao/webserver
python da_server.py
```

The backend will start on `http://localhost:5000`.

**Important:** Keep the backend running while developing the frontend.

## Development Workflow

### Start Development Server

```bash
cd dao/frontend
pnpm dev
```

This starts Vite dev server with:
- **URL:** `http://localhost:5173` (default Vite port)
- **Hot Module Replacement (HMR):** Changes auto-reload in browser
- **API Proxy:** `/api/v2/*` requests proxied to `http://localhost:5000`
- **Source Maps:** Enabled for debugging

### Development Flow

1. **Start backend** (in terminal 1): `cd dao/webserver && python da_server.py`
2. **Start frontend** (in terminal 2): `cd dao/frontend && pnpm dev`
3. **Open browser**: Navigate to `http://localhost:5173`
4. **Make changes**: Edit files in `src/`
5. **Auto-reload**: Browser updates automatically on save

### Key Files and Directories

```
dao/frontend/
├── src/
│   ├── App.tsx              # Main application component
│   ├── App.css              # Global styles
│   ├── main.tsx             # Entry point, React root
│   ├── theme.tsx            # MUI theme configuration (dark/light)
│   ├── components/
│   │   ├── SecretsEditor.tsx       # Secrets management UI
│   │   ├── ErrorBoundary.tsx       # Error handling wrapper
│   │   └── renderers/              # Custom JSONForms renderers
│   │       ├── EntityRenderer.tsx  # HA entity picker
│   │       └── ...
│   └── services/
│       └── homeassistant.ts        # HA API integration
├── index.html           # HTML template
├── package.json         # Dependencies and scripts
├── vite.config.ts       # Vite configuration
├── tsconfig.json        # TypeScript configuration
└── DEVELOPER_GUIDE.md   # This file
```

## Build Process

### Production Build

```bash
pnpm build
```

This creates an optimized production build in `dist/`:

1. **TypeScript compilation** - Type checking and compilation
2. **Vite build** - Bundling, minification, optimization
3. **Output**: `dist/` directory with static assets

**Build outputs:**
- `dist/index.html` - Entry point
- `dist/assets/` - JS, CSS, and other assets

### Build Configuration

Key settings in `vite.config.ts`:
- **Base path**: `/config/` (for serving from Flask subdirectory)
- **No code splitting**: Single bundle to avoid loading order issues
- **Minification**: ESBuild (fast production builds)
- **Source maps**: Disabled in production

### Deploy Built Frontend

After building, copy to backend static directory:

```bash
cd dao/frontend
pnpm build
rsync -av dist/ ../webserver/app/static/config-ui/
```

The backend serves the frontend at `http://localhost:5000/config`.

## API Integration

### Backend API Endpoints

The frontend communicates with Flask backend via REST API:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2/config` | GET | Load configuration |
| `/api/v2/config` | POST | Save configuration |
| `/api/v2/secrets` | GET | Load secrets |
| `/api/v2/secrets` | POST | Save secrets |
| `/api/v2/config/schema` | GET | Get JSON schema |
| `/api/v2/config/uischema` | GET | Get UI schema |
| `/api/v2/ha-proxy/*` | ALL | Proxy to Home Assistant API |

### HA Proxy Configuration

The HA proxy endpoint forwards requests to Home Assistant. Connection details are sent via headers:

```typescript
// In src/services/homeassistant.ts
headers: {
  'X-HA-Host': 'homeassistant.local',
  'X-HA-Port': '8123',
  'X-HA-Protocol': 'http',
  'X-HA-Token': 'your-long-lived-token'
}
```

During development, Vite proxies `/api/v2/*` to the Flask backend.

## Environment Variables

### Vite Environment Detection

```typescript
import.meta.env.DEV   // true in development
import.meta.env.PROD  // true in production
```

### No Configuration Required

The frontend uses **relative URLs** for all API calls (e.g., `/api/v2/config`), which work in both:
- **Development**: Vite proxy forwards to `http://localhost:5000`
- **Production**: Same-origin requests to Flask backend

## Testing

### Run TypeScript Type Checking

```bash
pnpm run build
```

The build process includes full TypeScript compilation with strict type checking.

### UI Schema Validation

Validate that the generated UI schema is correct:

```bash
pnpm run validate-uischema
```

This runs `validate-uischema.ts` to check schema structure.

## Troubleshooting

### Common Issues

#### 1. "Cannot find module 'vite'" or similar

**Cause:** Dependencies not installed  
**Solution:**
```bash
rm -rf node_modules pnpm-lock.yaml
pnpm install
```

#### 2. API calls failing with 404

**Cause:** Backend not running  
**Solution:**
```bash
# Check if backend is running
curl http://localhost:5000/api/v2/config/schema

# If not, start backend
cd dao/webserver
source ../../.venv/bin/activate
python da_server.py
```

#### 3. "Failed to fetch schema" error on load

**Cause:** Schemas not generated  
**Solution:**
```bash
cd /path/to/day-ahead
source .venv/bin/activate
python scripts/generate_uischema.py
```

#### 4. TypeScript errors in IDE

**Cause:** VS Code using wrong TypeScript version  
**Solution:**
1. Open Command Palette (Cmd+Shift+P / Ctrl+Shift+P)
2. Type "TypeScript: Select TypeScript Version"
3. Choose "Use Workspace Version"

#### 5. Hot Module Replacement not working

**Cause:** File watcher limits on Linux  
**Solution:**
```bash
# Increase file watcher limit
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

#### 6. Build succeeds but frontend shows white screen

**Cause:** Base path mismatch or missing assets  
**Solution:**
1. Check browser console for 404 errors
2. Verify `vite.config.ts` has `base: '/config/'`
3. Ensure assets copied to `dao/webserver/app/static/config-ui/`
4. Check Flask serves files at `/config` route

#### 7. Entity picker not loading HA entities

**Cause:** HA connection settings incorrect or HA proxy failing  
**Solution:**
1. Check browser Network tab for failed `/api/v2/ha-proxy/states` call
2. Verify HA connection settings in UI (hostname, port, token)
3. Test HA connectivity: `curl -H "Authorization: Bearer YOUR_TOKEN" http://YOUR_HA_IP:8123/api/states`
4. Check backend logs for proxy errors

### Debug Mode

Enable verbose logging in the browser console:

**Chrome/Edge:**
1. Open DevTools (F12)
2. Go to Console tab
3. Check "Verbose" level

**Firefox:**
1. Open DevTools (F12)
2. Go to Console tab
3. Click gear icon → Enable all log levels

### Clean Rebuild

If experiencing strange issues, try a clean rebuild:

```bash
# Clean all build artifacts
rm -rf node_modules dist .vite

# Reinstall and rebuild
pnpm install
pnpm build
```

## Code Style and Best Practices

### TypeScript Guidelines

1. **Use strict typing** - Avoid `any` types
2. **Define interfaces** - For all props and data structures
3. **Use const assertions** - For immutable objects
4. **Null safety** - Handle `null`/`undefined` explicitly

### React Guidelines

1. **Functional components only** - No class components
2. **Hooks** - Use React hooks for state and effects
3. **Component composition** - Break down large components
4. **Memoization** - Use `useMemo`/`useCallback` for expensive operations

### File Organization

```typescript
// Standard import order
import React, { useState, useEffect } from 'react';  // React
import { Box, Button } from '@mui/material';         // UI libraries
import { MyComponent } from './components';          // Local components
import { fetchData } from './services';              // Local services
import './styles.css';                               // Styles
```

## Performance Considerations

### Bundle Size

Current bundle size: ~500-600 KB (gzipped)

Large dependencies:
- Material-UI (~200 KB)
- JSONForms (~150 KB)
- React (~100 KB)

### Optimization Strategies

1. **Single bundle**: Avoids chunk loading order issues
2. **Tree shaking**: Unused code eliminated automatically
3. **Minification**: ESBuild for fast compression
4. **Lazy loading**: Consider code splitting if bundle grows >1 MB

## Additional Resources

### Documentation

- [React Documentation](https://react.dev/)
- [Material-UI Documentation](https://mui.com/material-ui/getting-started/)
- [JSONForms Documentation](https://jsonforms.io/)
- [Vite Documentation](https://vite.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)

### Project-Specific Documentation

- [API V2 Documentation](../../API-V2.md) - Backend API reference
- [TODO List](../../TODO-config-gui-integration.md) - Implementation progress
- [Design Document](../../DESIGN-react-frontend.md) - Architecture decisions

## Getting Help

1. **Check this guide** for common issues
2. **Review browser console** for errors
3. **Check backend logs** for API issues
4. **Inspect Network tab** for failed requests
5. **Create GitHub issue** with error logs and reproduction steps
