import { rankWith, uiTypeIs } from '@jsonforms/core'
import { withJsonFormsLabelProps } from '@jsonforms/react'
import { Typography, Box } from '@mui/material'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Custom Label renderer that renders markdown content.
 * 
 * Replaces the default JSONForms Label renderer to support rich markdown
 * formatting in help text and documentation.
 */
const MarkdownLabelRenderer = ({ text, visible }: { text?: string; visible?: boolean }) => {
  if (!visible) return null
  if (!text) return null

  return (
    <Box sx={{ 
      mb: 2,
      color: 'text.primary',
      '& h1': { fontSize: '1.5rem', fontWeight: 600, mt: 2, mb: 1.5, color: 'text.primary' },
      '& h2': { fontSize: '1.25rem', fontWeight: 600, mt: 2, mb: 1, color: 'text.primary' },
      '& h3': { fontSize: '1.1rem', fontWeight: 600, mt: 1.5, mb: 0.75, color: 'text.primary' },
      '& p': { mb: 1, lineHeight: 1.6, color: 'text.primary' },
      '& ul, & ol': { pl: 3, mb: 1 },
      '& li': { mb: 0.5, color: 'text.primary' },
      '& code': { 
        bgcolor: (theme) => theme.palette.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.05)'
          : 'grey.100',
        px: 0.75, 
        py: 0.25, 
        borderRadius: 0.5,
        fontSize: '0.875em',
        fontFamily: 'monospace',
        color: 'text.primary'
      },
      '& pre': { 
        bgcolor: (theme) => theme.palette.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.05)'
          : 'grey.100',
        p: 2, 
        borderRadius: 1,
        overflow: 'auto',
        mb: 1
      },
      '& pre code': {
        bgcolor: 'transparent',
        p: 0
      },
      '& strong': { fontWeight: 600, color: 'text.primary' },
      '& a': { color: 'primary.main', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } },
      '& blockquote': { 
        borderLeft: '4px solid',
        borderColor: (theme) => theme.palette.mode === 'dark'
          ? 'rgba(144, 202, 249, 0.3)'
          : 'grey.300',
        pl: 2,
        ml: 0,
        fontStyle: 'italic',
        color: 'text.secondary'
      }
    }}>
      <Typography component="div" variant="body2" color="text.secondary">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {text}
        </ReactMarkdown>
      </Typography>
    </Box>
  )
}

export default withJsonFormsLabelProps(MarkdownLabelRenderer)

// Tester: match all Label elements
export const markdownLabelTester = rankWith(5, uiTypeIs('Label'))
