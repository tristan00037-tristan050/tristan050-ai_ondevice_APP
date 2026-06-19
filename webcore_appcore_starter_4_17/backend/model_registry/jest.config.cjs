module.exports = {
  testEnvironment: "node",
  preset: "ts-jest",
  testMatch: ["<rootDir>/tests/**/*.test.ts"],
  // 모든 스위트가 단일 공유 데이터 디렉터리(../data)에 영속화하고, 일부 테스트는 ../data 를 직접 하드코딩해
  // fs 직접 쓰기와 persist 함수를 혼용한다. 병렬 워커에서는 다른 스위트의 clearAll()/파일 쓰기가
  // 진행 중인 테스트의 상태(예: update_states.json)를 덮어써 restart-safe 영속 테스트를 비결정적으로
  // 실패시킨다(단독 실행은 통과). 직렬 실행으로 파일시스템 경쟁을 제거한다.
  maxWorkers: 1,
  transform: {
    "^.+\\.ts$": ["ts-jest", { tsconfig: "<rootDir>/tsconfig.json" }],
  },
  moduleFileExtensions: ["ts", "js", "json"],
  moduleNameMapper: {
    "^express$": "<rootDir>/node_modules/express",
  },
};

