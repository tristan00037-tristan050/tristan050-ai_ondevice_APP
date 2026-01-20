module.exports = {
  testEnvironment: "node",
  preset: "ts-jest",
  testMatch: ["<rootDir>/tests/**/*.test.ts"],
  testPathIgnorePatterns: ["<rootDir>/tests/model_registry.test.ts"], // SVR-03-B scope (signing/delivery)
  transform: {
    "^.+\\.ts$": ["ts-jest", { tsconfig: "<rootDir>/tsconfig.json" }],
  },
  moduleFileExtensions: ["ts", "js", "json"],
};

