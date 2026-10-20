import { Typography } from '@mantine/core'
import type { ReactNode } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

const CITATION = /\[(KB-\d{3})\](?!\()/g
const CITATION_HREF = '#KB-'

interface MarkdownTextProps {
  children: string
  /** Renders each `[KB-042]` citation. Without it, citations stay plain text. */
  renderCitation?: (recordId: string) => ReactNode
}

/**
 * Markdown with GFM tables, which scroll sideways when they don't fit. Links open in
 * a new tab, and raw HTML is not rendered.
 */
export function MarkdownText({ children, renderCitation }: MarkdownTextProps) {
  const components: Components = {
    table: ({ node: _node, ...props }) => (
      <div style={{ overflowX: 'auto' }}>
        <table {...props} />
      </div>
    ),
    a: ({ node: _node, href, children: label, ...props }) => {
      if (renderCitation && href?.startsWith(CITATION_HREF)) {
        return renderCitation(href.slice(1))
      }
      return (
        <a {...props} href={href} target="_blank" rel="noreferrer">
          {label}
        </a>
      )
    },
  }
  const text = renderCitation
    ? children.replace(CITATION, '[$1](#$1)')
    : children

  return (
    <Typography>
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </Markdown>
    </Typography>
  )
}
