// UTF-8 safe base64 encoding/decoding
export function encodeB64(text) {
  return btoa(unescape(encodeURIComponent(text)));
}

export function decodeB64(b64) {
  return decodeURIComponent(escape(atob(b64.replace(/\s/g, ""))));
}
