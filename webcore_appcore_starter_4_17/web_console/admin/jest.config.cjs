module.exports = {
  testEnvironment: "jsdom",
  preset: "ts-jest/presets/default",
  testMatch: ["<rootDir>/tests/**/*.test.ts", "<rootDir>/tests/**/*.test.tsx"],
  transform: {
    "^.+\\.tsx?$": ["ts-jest", { 
      tsconfig: {
        jsx: "react-jsx",
        esModuleInterop: true,
        module: "CommonJS",
      }
    }],
  },
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  roots: ["<rootDir>"],
};

