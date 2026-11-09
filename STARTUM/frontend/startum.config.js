const startumIsLocalFrontend =
  ["127.0.0.1", "localhost"].includes(window.location.hostname) &&
  window.location.port === "5500";
window.STARTUM_CONFIG = Object.freeze({
  apiBaseUrl: startumIsLocalFrontend ? "http://127.0.0.1:8000/api" : "/api",

  contactPhone: "+998 93 248 34 41",
});
