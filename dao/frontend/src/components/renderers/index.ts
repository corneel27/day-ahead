import DateDictRenderer, { dateDictTester } from './DateDictRenderer'
import BoolOrStringRenderer, { boolOrStringTester } from './BoolOrStringRenderer'
import OptionalStringRenderer, { optionalStringTester } from './OptionalStringRenderer'
import EnumRenderer, { enumTester } from './EnumRenderer'
import StringRenderer, { stringTester } from './StringRenderer'
import NumberRenderer, { numberTester } from './NumberRenderer'
import EntityPickerOrNumberRenderer, { entityPickerOrNumberTester } from './EntityPickerOrNumberRenderer'
import EntityPickerRenderer, { entityPickerTester } from './EntityPickerRenderer'
import EntityListPickerRenderer, { entityListPickerTester } from './EntityListPickerRenderer'
import EntityPickerOrBooleanRenderer, { entityPickerOrBooleanTester } from './EntityPickerOrBooleanRenderer'
import EntityPickerOrStringRenderer, { entityPickerOrStringTester } from './EntityPickerOrStringRenderer'
import EntityPickerOrEnumRenderer, { entityPickerOrEnumTester } from './EntityPickerOrEnumRenderer'
import SecretPickerRenderer, { secretPickerTester } from './SecretPickerRenderer'
import MarkdownLabelRenderer, { markdownLabelTester } from './MarkdownLabelRenderer'
import HelpButtonRenderer, { helpButtonTester } from './HelpButtonRenderer'
import BooleanToggleRenderer, { booleanToggleTester } from './BooleanToggleRenderer'
import { materialRenderers } from '@jsonforms/material-renderers'

export const customRenderers = [
  { tester: booleanToggleTester, renderer: BooleanToggleRenderer },
  { tester: helpButtonTester, renderer: HelpButtonRenderer },
  { tester: markdownLabelTester, renderer: MarkdownLabelRenderer },
  { tester: entityPickerOrNumberTester, renderer: EntityPickerOrNumberRenderer },
  { tester: entityPickerTester, renderer: EntityPickerRenderer },
  { tester: entityListPickerTester, renderer: EntityListPickerRenderer },
  { tester: entityPickerOrBooleanTester, renderer: EntityPickerOrBooleanRenderer },
  { tester: entityPickerOrStringTester, renderer: EntityPickerOrStringRenderer },
  { tester: entityPickerOrEnumTester, renderer: EntityPickerOrEnumRenderer },
  { tester: secretPickerTester, renderer: SecretPickerRenderer },
  { tester: optionalStringTester, renderer: OptionalStringRenderer },
  { tester: boolOrStringTester, renderer: BoolOrStringRenderer },
  { tester: dateDictTester, renderer: DateDictRenderer },
  { tester: enumTester, renderer: EnumRenderer },
  { tester: numberTester, renderer: NumberRenderer },
  { tester: stringTester, renderer: StringRenderer },
]

export const allRenderers = [...customRenderers, ...materialRenderers]
