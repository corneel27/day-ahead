import { rankWith, schemaMatches } from '@jsonforms/core';
import HaEntityControl from './HaEntityControl';

// Tester function to check if the field has the custom HA entity property
export const haEntityTester = rankWith(
  10, // High priority to override default renderer
  schemaMatches((schema) => {
    // Check if the schema has the custom haEntityDomains property
    // Now supports all field types: enum, boolean, number, string
    return schema.haEntityDomains !== undefined;
  })
);

export const haEntityRendererEntry = {
  tester: haEntityTester,
  renderer: HaEntityControl,
};
