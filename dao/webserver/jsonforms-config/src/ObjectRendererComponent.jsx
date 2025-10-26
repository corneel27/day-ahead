import React from 'react';
import { withJsonFormsControlProps } from '@jsonforms/react';
import { JsonFormsDispatch, useJsonForms } from '@jsonforms/react';
import { Box, Typography } from '@mui/material';
import { createDefaultValue } from '@jsonforms/core';

const ObjectRenderer = (props) => {
  const { schema, path, renderers, cells, uischema, visible } = props;
  const ctx = useJsonForms();

  console.log('ObjectRenderer for:', path, 'schema:', schema);

  if (!visible) {
    return null;
  }

  const properties = schema.properties || {};
  const propertyNames = Object.keys(properties);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {propertyNames.map((propName) => {
        const propSchema = properties[propName];
        const propPath = path ? `${path}.${propName}` : propName;

        return (
          <JsonFormsDispatch
            key={propName}
            schema={propSchema}
            uischema={{
              type: 'Control',
              scope: `#/properties/${propName}`,
              label: propName,
            }}
            path={propPath}
            renderers={renderers || ctx.renderers}
            cells={cells || ctx.cells}
          />
        );
      })}
    </Box>
  );
};

export default withJsonFormsControlProps(ObjectRenderer);
