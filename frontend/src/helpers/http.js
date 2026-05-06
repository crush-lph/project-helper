export function errorMessage(err, fallback) {
  return err instanceof Error ? err.message : fallback
}

export async function responseDetail(response, fallback) {
  try {
    const data = await response.json()
    return data.detail || fallback
  } catch {
    return fallback
  }
}
