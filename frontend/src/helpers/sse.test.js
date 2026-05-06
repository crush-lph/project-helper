import { describe, expect, it } from 'vitest'
import { parseSse } from './sse'

describe('parseSse', () => {
  it('parses event names and multi-line JSON payloads', () => {
    const event = parseSse('event: token\ndata: {"text":"hello"}\n')

    expect(event).toEqual({ event: 'token', data: { text: 'hello' } })
  })

  it('defaults to an empty payload when data is missing', () => {
    const event = parseSse('event: done\n')

    expect(event).toEqual({ event: 'done', data: {} })
  })
})
