# Day Ahead Optimizer - JSONForms Configuration UI

This is a modern, user-friendly configuration interface for the Day Ahead Optimizer, built with React and JSONForms.

## Features

- **Organized Layout**: Configuration options are organized into logical categories (Basic Settings, Connections, Weather & Prices, Solar & Battery, etc.)
- **Validation**: Real-time validation based on the JSON Schema
- **Auto-complete**: Input suggestions and validation help prevent configuration errors
- **Import/Export**: Download and upload configuration files
- **Responsive Design**: Works on desktop and mobile devices
- **Material UI**: Modern, clean interface using Material-UI components

## Development

### Prerequisites

- Node.js 18+ and npm
- The Day Ahead Optimizer backend running on port 5000

### Installation

```bash
cd dao/webserver/jsonforms-config
npm install
```

### Development Server

```bash
npm run dev
```

This starts a development server at `http://localhost:3000` with hot-reload enabled.

### Building for Production

```bash
npm run build
```

This builds the application and places the output in `../app/static/config/`, making it automatically available to Flask at `/config-jsonforms`.

This creates optimized production files in the `dist` directory.

## Architecture

### Components

- **App.jsx**: Main application component
  - Handles data loading and saving
  - Manages UI state and notifications
  - Integrates JSONForms with Material-UI

- **uiSchema.js**: Defines the layout and organization
  - Categories for different configuration sections
  - Groups within categories
  - Conditional rendering rules

- **options_schema.json**: JSON Schema defining the data structure
  - Type definitions
  - Validation rules
  - Default values
  - Descriptions

### API Integration

The UI communicates with the Flask backend via these endpoints:

- `GET /api/config/options` - Load current configuration
- `POST /api/config/options` - Save configuration
- `GET /static/../options_schema.json` - Load JSON schema

### Categorization

The UI is organized into these categories:

1. **Basic Settings** - Logging, display, strategy
2. **Connections** - Home Assistant and database connections
3. **Weather & Prices** - Meteoserver and energy pricing
4. **Baseload** - Base load configuration
5. **Solar & Battery** - PV systems and batteries
6. **Heating** - Heat pump and boiler
7. **Electric Vehicles** - EV charging configuration
8. **Appliances** - Household machines
9. **System** - Grid, notifications, dashboard
10. **Reporting** - Report entities and Tibber
11. **Scheduler** - Task scheduling

## JSONForms Features Used

- **Categorization**: Tab-based navigation for different sections
- **Vertical Layouts**: Organize fields vertically within categories
- **Groups**: Visual grouping of related fields
- **Rules**: Conditional display (e.g., baseload fields based on use_calc_baseload)
- **Material Renderers**: Pre-built Material-UI components

## Customization

### Adding Custom Renderers

You can create custom renderers for specific fields:

```javascript
import { rankWith, scopeEndsWith } from '@jsonforms/core';

const MyCustomRenderer = ({ data, handleChange, path }) => {
  // Custom rendering logic
};

const myCustomRendererTester = rankWith(
  3, // priority
  scopeEndsWith('fieldname')
);

// Add to renderers array in App.jsx
const renderers = [
  ...materialRenderers,
  { tester: myCustomRendererTester, renderer: MyCustomRenderer }
];
```

### Styling

- Modify `App.css` for global styles
- Adjust Material-UI theme in `App.jsx`
- Override JSONForms styles by targeting specific classes

## Troubleshooting

### Schema Validation Errors

If you see validation errors:
1. Check the JSON Schema for correct type definitions
2. Ensure required fields are present
3. Verify enum values match the schema

### API Connection Issues

If the UI can't connect to the backend:
1. Ensure the Flask server is running on port 5000
2. Check browser console for CORS errors
3. Verify API endpoints are accessible

### Build Issues

If build fails:
1. Clear node_modules and reinstall: `rm -rf node_modules && npm install`
2. Check Node.js version: `node --version` (should be 18+)
3. Clear Vite cache: `rm -rf node_modules/.vite`

## Future Enhancements

- [ ] Add custom renderer for scheduler configuration
- [ ] Implement drag-and-drop for array items
- [ ] Add visual editor for baseload (24-hour graph)
- [ ] Integrate Home Assistant entity picker
- [ ] Add validation for secrets references
- [ ] Implement diff viewer for configuration changes
- [ ] Add preset configurations
- [ ] Support for multi-language interface

## Resources

- [JSONForms Documentation](https://jsonforms.io/docs/)
- [Material-UI Documentation](https://mui.com/)
- [Vite Documentation](https://vitejs.dev/)
- [JSON Schema Reference](https://json-schema.org/)
