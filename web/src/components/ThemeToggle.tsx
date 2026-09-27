"use client";

import { useEffect, useState } from "react";

type Theme = "dark" | "light";

function stored(): Theme | null {
  try {
    const value = window.localStorage.getItem("ledger-theme");
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const initial = stored() ?? (document.documentElement.dataset.theme as Theme | undefined) ?? "dark";
    setTheme(initial);
    document.documentElement.dataset.theme = initial;
  }, []);

  const flip = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("ledger-theme", next);
    } catch {
      // A private window or blocked storage: the choice lasts for this page only.
    }
  };

  return (
    <button
      type="button"
      onClick={flip}
      className="text-xs px-2 py-1 border border-hairline rounded text-ink2 hover:text-ink shrink-0"
      aria-label={`Switch to the ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}
