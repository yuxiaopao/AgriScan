export function validCoordinates(latitude: string | number | null | undefined, longitude: string | number | null | undefined): [number, number] | null {
  if (latitude == null || longitude == null || String(latitude).trim() === '' || String(longitude).trim() === '') return null
  const lat = Number(latitude), lng = Number(longitude)
  return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? [lat, lng] : null
}
