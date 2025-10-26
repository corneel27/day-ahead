# JSONForms Configuration UI - Setup Guide

This guide will help you set up and use the new JSONForms-based configuration interface for the Day Ahead Optimizer.

## Overview

The JSONForms UI provides a modern, user-friendly interface for configuring the Day Ahead Optimizer with:
- ✅ Real-time validation
- ✅ Organized categorization
- ✅ Auto-completion and type checking
- ✅ Import/Export functionality
- ✅ Responsive design

## Quick Start

### 1. Install Dependencies

Navigate to the jsonforms-config directory:

```bash
cd dao/webserver/jsonforms-config
npm install
```

### 2. Development Mode

For development with hot-reload:

```bash
# Terminal 1: Start the Flask backend (if not already running)
cd dao
python -m dao.webserver.da_server

# Terminal 2: Start the React dev server
cd dao/webserver/jsonforms-config
npm run dev
```

Then open: `http://localhost:3000`

**Note**: If your Flask server runs on a different port than 5000, you have two options:

**Option 1: Use environment variables**
```bash
FLASK_PORT=8080 npm run dev
```

**Option 2: Create a `.env` file**
```bash
# Copy the example file
cp .env.example .env

# Edit .env and set your port
# FLASK_PORT=8080
# FLASK_HOST=localhost
```

### 3. Production Build

Build the production version:

```bash
cd dao/webserver/jsonforms-config
npm run build
```

The built files will be automatically placed in `dao/webserver/app/static/config/` and can be served by Flask at:
`http://localhost:5000/config-jsonforms`

**Note**: After building, restart your Flask server to serve the updated files.

## Features

### Categorized Navigation

The configuration is organized into logical categories:

1. **Basic Settings** - Core settings like logging level, interval, strategy
2. **Connections** - Home Assistant and database connections
3. **Weather & Prices** - Meteoserver API and energy pricing
4. **Baseload** - Base consumption configuration
5. **Solar & Battery** - PV installations and battery systems
6. **Heating** - Heat pump and boiler settings
7. **Electric Vehicles** - EV charging configuration
8. **Appliances** - Household machines (washing machine, dishwasher, etc.)
9. **System** - Grid, notifications, dashboard settings
10. **Reporting** - Report entity configuration
11. **Scheduler** - Task scheduling

### Validation

The interface provides real-time validation:
- **Type checking**: Ensures values match expected types (string, number, boolean)
- **Range validation**: Checks min/max values
- **Required fields**: Highlights missing required fields
- **Pattern matching**: Validates dates, times, and other patterns
- **Enum validation**: Restricts values to allowed choices

### Conditional Display

Fields are shown/hidden based on other settings:
- Baseload configuration appears based on `use_calc_baseload` setting
- Database connection fields adjust based on engine type (MySQL, PostgreSQL, SQLite)

### Import/Export

- **Download**: Export current configuration as JSON file
- **Upload**: Import configuration from JSON file
- **Save**: Save configuration to server
- **Reload**: Reload configuration from server

## API Endpoints

The UI uses these Flask API endpoints:

### GET /api/config/options
Load the current options.json configuration

**Response:**
```json
{
  "homeassistant": {},
  "database ha": {...},
  ...
}
```

### POST /api/config/options
Save the options.json configuration

**Request Body:**
```json
{
  "homeassistant": {},
  "database ha": {...},
  ...
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration saved successfully"
}
```

### GET /api/config/secrets
Load the current secrets.json configuration

### POST /api/config/secrets
Save the secrets.json configuration

## File Structure

```
jsonforms-config/
├── package.json              # Dependencies and scripts
├── vite.config.js           # Vite build configuration
├── index.html               # HTML entry point
├── README.md                # Documentation
├── .gitignore              # Git ignore rules
└── src/
    ├── main.jsx            # Application entry point
    ├── App.jsx             # Main application component
    ├── App.css             # Application styles
    ├── index.css           # Global styles
    └── uiSchema.js         # UI Schema (layout definition)
```

## Customization

### Adding Custom Renderers

Create custom renderers for specific fields or types:

```javascript
// src/renderers/SchedulerRenderer.jsx
import React from 'react';
import { withJsonFormsControlProps } from '@jsonforms/react';

const SchedulerRenderer = ({ data, handleChange, path }) => {
  return (
    <div>
      {/* Custom scheduler UI */}
    </div>
  );
};

export default withJsonFormsControlProps(SchedulerRenderer);
```

Register the renderer:

```javascript
// src/App.jsx
import { rankWith, scopeEndsWith } from '@jsonforms/core';
import SchedulerRenderer from './renderers/SchedulerRenderer';

const schedulerTester = rankWith(5, scopeEndsWith('scheduler'));

const renderers = [
  ...materialRenderers,
  { tester: schedulerTester, renderer: SchedulerRenderer }
];
```

### Modifying the UI Schema

Edit `src/uiSchema.js` to change the layout:

```javascript
// Add a new category
{
  "type": "Category",
  "label": "My New Category",
  "elements": [
    {
      "type": "VerticalLayout",
      "elements": [
        {
          "type": "Control",
          "scope": "#/properties/myField"
        }
      ]
    }
  ]
}
```

### Styling

Customize the theme in `src/App.jsx`:

```javascript
const theme = createTheme({
  palette: {
    mode: 'dark', // Switch to dark mode
    primary: {
      main: '#2196f3',
    },
    secondary: {
      main: '#f50057',
    },
  },
});
```

## Troubleshooting

### Port Already in Use

If port 3000 is already in use:

```bash
# Edit vite.config.js and change the port
server: {
  port: 3001, // Use a different port
  ...
}
```

### CORS Issues

If you encounter CORS errors in development:

1. The Vite proxy should handle this automatically
2. If issues persist, add CORS headers to Flask:

```python
# In routes.py
from flask_cors import CORS
CORS(app)
```

### Schema Not Loading

If the schema doesn't load:

1. Check that `options_schema.json` exists in `/dao/` directory
2. Verify the Flask server is running
3. Check browser console for error messages

### Build Errors

If the build fails:

```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install

# Try building again
npm run build
```

## Development Tips

### Hot Reload

Both Vite and Flask support hot reload:
- **Vite**: Automatically reloads on file changes
- **Flask**: Use `FLASK_ENV=development` for auto-reload

### Debugging

Enable React DevTools in Chrome/Firefox for component inspection:
- Install React Developer Tools extension
- Open DevTools and look for "Components" and "Profiler" tabs

### Testing Changes

1. Make changes to the code
2. Save the file (Vite will auto-reload)
3. Check the browser for updates
4. Use browser console for any errors

## Integration with Existing UI

The JSONForms UI can coexist with the existing configuration interface:

- **Old UI**: `/config` - Current JSON editor
- **New UI**: `/config-jsonforms` - JSONForms interface

Users can choose which interface they prefer, or you can eventually migrate fully to JSONForms.

## Performance

The JSONForms UI is optimized for performance:
- **Lazy loading**: Only loads visible components
- **Memoization**: Prevents unnecessary re-renders
- **Code splitting**: Vite automatically splits code for faster loading

## Browser Support

The UI supports all modern browsers:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

## Next Steps

1. **Install dependencies**: `npm install`
2. **Start development**: `npm run dev`
3. **Test the interface**: Make configuration changes
4. **Build for production**: `npm run build`
5. **Deploy**: Copy `dist` files or serve via Flask

## Support

For issues or questions:
- Check the [JSONForms Documentation](https://jsonforms.io/docs/)
- Review the [Material-UI Documentation](https://mui.com/)
- Open an issue on GitHub

## Contributing

To contribute improvements:
1. Make changes in a feature branch
2. Test thoroughly in development mode
3. Build for production and test
4. Submit a pull request with description

Happy configuring! 🎉
