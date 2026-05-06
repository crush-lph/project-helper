export function parseSse(frame) {
  const lines = frame.split('\n').filter(Boolean)
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
  const dataText = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n') || '{}'
  return { event, data: JSON.parse(dataText) }
}
