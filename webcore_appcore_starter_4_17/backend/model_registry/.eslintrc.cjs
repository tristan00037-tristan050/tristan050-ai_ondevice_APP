module.exports = {
  root: true,
  env: { node: true, es2022: true, jest: true },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    tsconfigRootDir: __dirname,
    project: ["./tsconfig.json"]
  },
  plugins: ["@typescript-eslint", "import"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:import/recommended",
    "plugin:import/typescript"
  ],
  rules: {
    // 재발 방지 핵심: undefined/unused를 조기 차단
    "no-undef": "off", // TS가 담당
    "@typescript-eslint/no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
    "@typescript-eslint/no-floating-promises": "off",
    "import/no-unresolved": "off" // tsconfig path를 TS가 잡도록(중복 경고 방지)
  },
  ignorePatterns: ["dist/**", "node_modules/**", "*.cjs"]
};
