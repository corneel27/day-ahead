import { rankWith, schemaMatches } from '@jsonforms/core';
import SecretControl from './SecretControl';

// Tester function to check if the field has the custom haSecret property
export const secretTester = rankWith(
  10, // High priority to override default renderer
  schemaMatches((schema) => {
    // Check if the schema has the custom haSecret property
    return schema.haSecret === true;
  })
);

export const secretRendererEntry = {
  tester: secretTester,
  renderer: SecretControl,
};
