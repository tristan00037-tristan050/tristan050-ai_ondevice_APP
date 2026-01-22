module.exports = {
  testEnvironment: "jsdom",
  preset: "ts-jest/presets/default",
  testMatch: ["<rootDir>/tests/**/*.test.ts", "<rootDir>/tests/**/*.test.tsx"],
  testPathIgnorePatterns: [],
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { 
      tsconfig: "<rootDir>/tsconfig.json",
      isolatedModules: true,
    }],
  },
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  roots: ["<rootDir>"],
  setupFilesAfterEnv: ["<rootDir>/../../packages/ops-console/node_modules/@testing-library/jest-dom"],
};

