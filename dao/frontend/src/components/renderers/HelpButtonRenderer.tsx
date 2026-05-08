import { rankWith, uiTypeIs } from '@jsonforms/core'
import { withJsonFormsControlProps } from '@jsonforms/react'
import { Button, Collapse, Box, Paper, Link } from '@mui/material'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Custom renderer for help buttons that expand/collapse markdown content inline.
 * 
 * Renders a help icon button that toggles a collapsible panel with the help text.
 * If docsUrl is provided, adds an external documentation link at the bottom.
 */
const HelpButtonRenderer = ({ uischema, visible }: any) => {
  const [open, setOpen] = useState(false)
  
  if (!visible) return null
  
  const helpText = uischema.options?.helpText
  const title = uischema.options?.helpTitle || 'Help'
  const docsUrl = uischema.options?.docsUrl
  
  if (!helpText) return null

  return (
    <Box sx={{ mb: 2 }}>
      <Button
        startIcon={<HelpOutlineIcon />}
        endIcon={open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        onClick={() => setOpen(!open)}
        size="small"
        variant="outlined"
        color="info"
        sx={{ textTransform: 'none', mb: open ? 1 : 0 }}
      >
        {title}
      </Button>
      
      <Collapse in={open}>
        <Paper 
          elevation={0}
          sx={{ 
            p: 2,
            bgcolor: (theme) => theme.palette.mode === 'dark' 
              ? 'rgba(144, 202, 249, 0.08)' 
              : 'info.light',
            border: 1,
            borderColor: (theme) => theme.palette.mode === 'dark'
              ? 'rgba(144, 202, 249, 0.3)'
              : 'info.main',
            borderRadius: 1,
            color: 'text.primary',
            '& h1': { fontSize: '1.5rem', fontWeight: 600, mt: 2, mb: 1.5, '&:first-of-type': { mt: 0 }, color: 'text.primary' },
            '& h2': { fontSize: '1.25rem', fontWeight: 600, mt: 2, mb: 1, color: 'text.primary' },
            '& h3': { fontSize: '1.1rem', fontWeight: 600, mt: 1.5, mb: 0.75, color: 'text.primary' },
            '& p': { mb: 1, lineHeight: 1.6, color: 'text.primary' },
            '& ul, & ol': { pl: 3, mb: 1 },
            '& li': { mb: 0.5, color: 'text.primary' },
            '& code': { 
              bgcolor: (theme) => theme.palette.mode === 'dark'
                ? 'rgba(255, 255, 255, 0.05)'
                : 'background.paper',
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
                : 'background.paper',
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
                : 'info.main',
              pl: 2,
              ml: 0,
              fontStyle: 'italic',
              color: 'text.secondary'
            }
          }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {helpText}
          </ReactMarkdown>
          
          {docsUrl && (
            <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
              <Link
                href={docsUrl}
                target="_blank"
                rel="noopener noreferrer"
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  fontWeight: 500,
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' }
                }}
              >
                External Documentation
                <OpenInNewIcon fontSize="small" />
              </Link>
            </Box>
          )}
        </Paper>
      </Collapse>
    </Box>
  )
}

export default withJsonFormsControlProps(HelpButtonRenderer)

// Tester: match controls with type "HelpButton"
export const helpButtonTester = rankWith(10, uiTypeIs('HelpButton'))
