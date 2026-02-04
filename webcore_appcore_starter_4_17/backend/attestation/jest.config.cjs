module.exports = {
  testEnvironment: "node",
  preset: "ts-jest",
  testMatch: [
    "<rootDir>/tests/attestation.test.ts",
    "<rootDir>/tests/attestation_http_e2e.test.ts"
  ],
  transform: {
    "^.+\\.ts$": ["ts-jest", { tsconfig: "<rootDir>/tsconfig.json" }],
  },
  moduleFileExtensions: ["ts", "js", "json"],
  moduleNameMapper: {
    "^express$": "<rootDir>/node_modules/express",
  },
};

