const path = require("path");
const OPS_NODE_MODULES = path.join(__dirname, "../../packages/ops-console/node_modules");

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
  
  // 모듈 검색 순서를 ops-console node_modules 우선으로 강제
  moduleDirectories: [OPS_NODE_MODULES, "node_modules"],
  
  // react/react-dom은 ops-console 것을 쓰도록 고정
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
    "^react$": path.join(OPS_NODE_MODULES, "react"),
    "^react-dom$": path.join(OPS_NODE_MODULES, "react-dom"),
  },
  
  roots: ["<rootDir>"],
  setupFilesAfterEnv: ["<rootDir>/tests/setupTests.ts"],
};

