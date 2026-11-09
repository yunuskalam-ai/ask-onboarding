// Apply the saved colour theme before the page draws, so there is no flash of
// the wrong theme (see src/theme.ts). A separate file, not an inline script,
// so the Content-Security-Policy can forbid inline scripts entirely.
try {
  var theme = localStorage.getItem("ask-onboarding:theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  // storage blocked: follow the system theme
}
