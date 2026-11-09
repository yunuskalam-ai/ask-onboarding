// Light, dark, or follow the system setting. The choice is stored in the
// browser and applied as <html data-theme="...">; "system" removes the
// attribute so the CSS media query decides. public/theme-init.js applies the
// saved choice before the page draws, so there is no flash of the wrong theme.

export type Theme = "light" | "dark" | "system";

export const THEMES: Theme[] = ["light", "dark", "system"];

const KEY = "ask-onboarding:theme";

export function savedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // storage can be blocked, e.g. in private windows
  }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // remembering the choice is only a convenience
  }
}
