export function getToken() {
  return localStorage.getItem("mf_token");
}

export function setToken(token) {
  if (token) {
    localStorage.setItem("mf_token", token);
  } else {
    localStorage.removeItem("mf_token");
  }
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
