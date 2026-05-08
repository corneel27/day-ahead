/**
 * TypeScript validator for generated UISchema.
 * 
 * This script validates the generated uischema.json against JSONForms'
 * official TypeScript type definitions. This ensures type safety and
 * automatically stays in sync with JSONForms updates.
 * 
 * Run with: pnpm run validate-uischema
 */

import type { UISchemaElement } from '@jsonforms/core';
import uischemaData from '../webserver/app/static/schemas/uischema.json';

/**
 * Extract source location from element options
 */
function getSource(element: any): string | null {
  if (element && element.options && element.options['x-source']) {
    return element.options['x-source'];
  }
  return null;
}

/**
 * Recursively validate UISchema structure
 */
function validateUISchema(element: any, path: string = 'root'): string[] {
  const errors: string[] = [];
  
  if (!element || typeof element !== 'object') {
    errors.push(`${path}: Element must be an object`);
    return errors;
  }
  
  const source = getSource(element);
  const location = source ? `${source} (${path})` : path;
  
  // Check for rule property
  if ('rule' in element) {
    const rule = element.rule;
    
    // Rule must be a single object, not an array
    if (Array.isArray(rule)) {
      errors.push(
        `${location}: 'rule' must be a single Rule object, not an array. ` +
        `JSONForms only supports one rule per element. ` +
        `Found: ${JSON.stringify(rule).substring(0, 100)}...`
      );
    } else if (typeof rule === 'object' && rule !== null) {
      // Validate rule structure
      if (!('effect' in rule)) {
        errors.push(`${location}.rule: Missing required 'effect' property`);
      }
      if (!('condition'in rule)) {
        errors.push(`${location}.rule: Missing required 'condition' property`);
      }
      if ('effect' in rule) {
        const validEffects = ['HIDE', 'SHOW', 'ENABLE', 'DISABLE'];
        if (!validEffects.includes(rule.effect)) {
          errors.push(
            `${location}.rule.effect: Invalid effect '${rule.effect}'. ` +
            `Must be one of: ${validEffects.join(', ')}`
          );
        }
      }
    }
  }
  
  // Recursively validate nested structures
  if ('elements' in element && Array.isArray(element.elements)) {
    element.elements.forEach((child: any, index: number) => {
      errors.push(...validateUISchema(child, `${path}.elements[${index}]`));
    });
  }
  
  // Also check options for nested UISchema elements (like in Categories)
  if ('options' in element && typeof element.options === 'object') {
    const opts = element.options;
    if ('detail' in opts && typeof opts.detail === 'object') {
      errors.push(...validateUISchema(opts.detail, `${path}.options.detail`));
    }
  }
  
  return errors;
}

// Validate the UISchema
const errors = validateUISchema(uischemaData);

if (errors.length > 0) {
  console.error('❌ UISchema validation failed:\n');
  errors.forEach(error => console.error(`   ${error}`));
  process.exit(1);
}

// Type assertion only after validation passes
const uischema: UISchemaElement = uischemaData as UISchemaElement;

console.log('✅ UISchema validation passed');
console.log(`   Type: ${uischema.type}`);
console.log(`   Elements: ${('elements' in uischema) ? (uischema as any).elements.length : 0}`);

export default uischema;
