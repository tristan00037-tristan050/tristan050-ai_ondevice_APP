/**
 * CS Tickets Domain Tests
 * R9-S1: CS 티켓 도메인 로직 테스트
 * 
 * @module service-core-cs/test/csTickets
 */

import { describe, it, expect, beforeAll, afterAll } from '@jest/globals';
import { pool } from '@appcore/data-pg';
import { listTickets, summarizeTickets, type CsTicket } from '../src/domain/csTickets.js';

const TEST_TENANT = 'test-tenant';

describe('CS Tickets Domain', () => {
  beforeAll(async () => {
    // 테스트용 데이터 삽입
    await pool.query(`
      INSERT INTO cs_tickets (tenant, subject, status, created_at)
      VALUES
        ($1, 'Test Ticket 1', 'open', now() - interval '1 day'),
        ($1, 'Test Ticket 2', 'pending', now() - interval '2 days'),
        ($1, 'Test Ticket 3', 'closed', now() - interval '3 days'),
        ($1, 'Test Ticket 4', 'open', now() - interval '4 days'),
        ($1, 'Test Ticket 5', 'closed', now() - interval '5 days')
    `, [TEST_TENANT]);
  });

  afterAll(async () => {
    // 테스트 데이터 정리
    await pool.query('DELETE FROM cs_tickets WHERE tenant = $1', [TEST_TENANT]);
  });

  describe('listTickets', () => {
    it('returns limited tickets for tenant', async () => {
      const tickets = await listTickets({
        tenant: TEST_TENANT,
        limit: 3,
        offset: 0,
      });

      expect(tickets).toHaveLength(3);
      expect(tickets[0]).toHaveProperty('id');
      expect(tickets[0]).toHaveProperty('subject');
      expect(tickets[0]).toHaveProperty('status');
      expect(tickets[0]).toHaveProperty('createdAt');
      expect(tickets[0].tenant).toBe(TEST_TENANT);
    });

    it('filters by status', async () => {
      const openTickets = await listTickets({
        tenant: TEST_TENANT,
        status: 'open',
        limit: 10,
      });

      expect(openTickets.length).toBeGreaterThan(0);
      openTickets.forEach((ticket) => {
        expect(ticket.status).toBe('open');
      });
    });

    it('respects offset', async () => {
      const first = await listTickets({
        tenant: TEST_TENANT,
        limit: 2,
        offset: 0,
      });

      const second = await listTickets({
        tenant: TEST_TENANT,
        limit: 2,
        offset: 2,
      });

      expect(first.length).toBe(2);
      expect(second.length).toBeGreaterThanOrEqual(0);
      // 첫 번째와 두 번째 결과가 겹치지 않아야 함
      if (first.length > 0 && second.length > 0) {
        expect(first[0].id).not.toBe(second[0].id);
      }
    });
  });

  describe('summarizeTickets', () => {
    it('returns counts by status', async () => {
      const summary = await summarizeTickets({
        tenant: TEST_TENANT,
        windowDays: 30,
      });

      expect(summary).toHaveProperty('tenant', TEST_TENANT);
      expect(summary).toHaveProperty('total');
      expect(summary).toHaveProperty('byStatus');
      expect(summary.byStatus).toHaveProperty('open');
      expect(summary.byStatus).toHaveProperty('pending');
      expect(summary.byStatus).toHaveProperty('closed');
      expect(typeof summary.byStatus.open).toBe('number');
      expect(typeof summary.byStatus.pending).toBe('number');
      expect(typeof summary.byStatus.closed).toBe('number');
      expect(summary.total).toBe(
        summary.byStatus.open + summary.byStatus.pending + summary.byStatus.closed
      );
    });

    it('respects windowDays parameter', async () => {
      const summary30 = await summarizeTickets({
        tenant: TEST_TENANT,
        windowDays: 30,
      });

      const summary1 = await summarizeTickets({
        tenant: TEST_TENANT,
        windowDays: 1,
      });

      // 30일 윈도우가 1일 윈도우보다 같거나 많은 티켓을 포함해야 함
      expect(summary30.total).toBeGreaterThanOrEqual(summary1.total);
    });
  });
});

