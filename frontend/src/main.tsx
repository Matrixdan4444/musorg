import React from "react";
import ReactDOM from "react-dom/client";
import App from "@/App";
import { I18nProvider } from "@/i18n/provider";
import { ThemeProvider, bootstrapStoredAppearance } from "@/theme/provider";
import "@fontsource/quicksand/600.css";
import "@fontsource/quicksand/700.css";
import "@/styles/globals.css";

bootstrapStoredAppearance();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <App />
      </I18nProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
