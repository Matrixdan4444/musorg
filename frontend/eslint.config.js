import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Allow intentionally-discarded bindings via a leading underscore.
      // Kept as a warning for the initial gate (a little pre-existing dead code
      // remains); ratchet to "error" once that is cleaned up.
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      // Surface these but don't block: they flag legitimate existing patterns
      // (state sync in effects, a few intentional `any`s at the webview bridge).
      // Kept as warnings so CI catches regressions without a mass refactor.
      "@typescript-eslint/no-explicit-any": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/static-components": "warn",
      // Control-character class is intentional in string-sanitization regexes.
      "no-control-regex": "off",
    },
  },
  // Keep ESLint focused on correctness; Prettier owns formatting.
  prettier,
);
