import { marked } from 'marked'
import DOMPurify from 'dompurify'

export function renderMarkdown(markdown) {
  return DOMPurify.sanitize(marked.parse(markdown || ''))
}
