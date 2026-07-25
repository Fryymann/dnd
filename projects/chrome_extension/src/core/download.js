// Encoding is chunked because a ~500KB payload spread into one
// String.fromCharCode call overflows the argument stack.
const CHUNK_SIZE = 0x8000;

export function toJsonDataUrl(value) {
  const json = JSON.stringify(value, null, 2);
  const bytes = new TextEncoder().encode(json);

  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += CHUNK_SIZE) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + CHUNK_SIZE));
  }
  return `data:application/json;base64,${btoa(binary)}`;
}
