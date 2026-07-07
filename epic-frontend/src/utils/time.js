export function formatUtcDateTime(value) {
  if (!value) return "";

  if (value instanceof Date) {
    return value.toLocaleString();
  }

  const hasTimezone = /([zZ]|[+-]\d\d:\d\d)$/.test(value);
  const parsed = new Date(hasTimezone ? value : `${value}Z`);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
}
