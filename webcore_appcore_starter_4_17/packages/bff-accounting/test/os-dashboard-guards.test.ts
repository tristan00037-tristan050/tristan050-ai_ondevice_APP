/**
 * BFF OS Dashboard API 가드 테스트
 * R8-S1 Phase 3: OS Dashboard API 가드 검증
 */

import { describe, test, expect, beforeAll, afterAll } from '@jest/globals';
import request from 'supertest';
import { app } from '../src/index.js';

// Jest가 없으면 Node.js fetch로 대체하는 간단한 테스트
const USE_SUPERTEST = typeof request !== 'undefined';

describe('OS Dashboard API Guards', () => {
  const BASE_URL = process.env.BFF_URL || 'http://localhost:8081';
  const TEST_HEADERS = {
    'X-Tenant': 'default',
    'X-User-Id': 'test-user',
    'X-User-Role': 'operator',
    'X-Api-Key': 'collector-key:operator',
  };

  test('기본 호출 테스트 - 200 OK 및 응답 스키마 검증', async () => {
    if (USE_SUPERTEST) {
      const res = await request(app)
        .get('/v1/accounting/os/dashboard')
        .set(TEST_HEADERS);

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('pilot');
      expect(res.body).toHaveProperty('health');
      expect(res.body).toHaveProperty('manual_review');
      expect(typeof res.body.pilot).toBe('object');
      expect(typeof res.body.health).toBe('object');
    } else {
      // Node.js fetch로 대체
      const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
        method: 'GET',
        headers: TEST_HEADERS,
      });

      expect(response.status).toBe(200);
      const body = await response.json();
      expect(body).toHaveProperty('pilot');
      expect(body).toHaveProperty('health');
      expect(body).toHaveProperty('manual_review');
      expect(typeof body.pilot).toBe('object');
      expect(typeof body.health).toBe('object');
    }
  });

  test('기간 상한 테스트 - 과도한 기간 요청에도 500 에러를 내지 않아야 함', async () => {
    const from = '2020-01-01';
    const to = '2030-01-01';

    if (USE_SUPERTEST) {
      const res = await request(app)
        .get(`/v1/accounting/os/dashboard?from=${from}&to=${to}`)
        .set(TEST_HEADERS);

      expect(res.status).not.toBe(500);
      // 2xx 또는 4xx 중 하나여야 함
      expect(res.status).toBeGreaterThanOrEqual(200);
      expect(res.status).toBeLessThan(500);
    } else {
      // Node.js fetch로 대체
      const response = await fetch(
        `${BASE_URL}/v1/accounting/os/dashboard?from=${from}&to=${to}`,
        {
          method: 'GET',
          headers: TEST_HEADERS,
        }
      );

      expect(response.status).not.toBe(500);
      expect(response.status).toBeGreaterThanOrEqual(200);
      expect(response.status).toBeLessThan(500);
    }
  });

  test('응답 스키마 회귀 테스트 - pilot, health, manual_review 키 존재 확인', async () => {
    if (USE_SUPERTEST) {
      const res = await request(app)
        .get('/v1/accounting/os/dashboard')
        .set(TEST_HEADERS);

      expect(res.status).toBe(200);
      const keys = Object.keys(res.body).sort();
      expect(keys).toEqual(expect.arrayContaining(['pilot', 'health', 'manual_review']));
    } else {
      // Node.js fetch로 대체
      const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
        method: 'GET',
        headers: TEST_HEADERS,
      });

      expect(response.status).toBe(200);
      const body = await response.json();
      const keys = Object.keys(body).sort();
      expect(keys).toEqual(expect.arrayContaining(['pilot', 'health', 'manual_review']));
    }
  });

  test('인증 없이 호출 시 403 Forbidden', async () => {
    if (USE_SUPERTEST) {
      const res = await request(app).get('/v1/accounting/os/dashboard');

      expect(res.status).toBe(403);
    } else {
      // Node.js fetch로 대체
      const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
        method: 'GET',
      });

      expect(response.status).toBe(403);
    }
  });
});

