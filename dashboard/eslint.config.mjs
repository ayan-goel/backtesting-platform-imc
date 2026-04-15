// ESLint flat config. Uses the next-core-web-vitals preset via next/core-web-vitals.
import next from "eslint-config-next";

export default [
  {
    ignores: [".next/**", "node_modules/**"],
  },
  ...next,
];
