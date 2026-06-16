import React from "react";
import ReactDOM from "react-dom/client";
import App from "@/App";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { I18nProvider } from "@/i18n/provider";
import { ThemeProvider, bootstrapStoredAppearance } from "@/theme/provider";
import "@/styles/globals.css";

bootstrapStoredAppearance();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error('Root element "#root" was not found in index.html');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <I18nProvider>
          <App />
        </I18nProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
