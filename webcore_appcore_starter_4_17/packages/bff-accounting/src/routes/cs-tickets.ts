/**
 * CS Tickets API 라우트
 * R9-S1: CS 티켓 목록 조회 API
 * 
 * @module bff-accounting/routes/cs-tickets
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { listTickets, type CsTicketStatus } from '@appcore/service-core-cs';

const router = Router();

/**
 * GET /v1/cs/tickets
 * CS 티켓 목록 조회
 */
router.get(
  '/tickets',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      // 테넌트: 가드에서 설정된 tenantId 사용
      const tenant = req.tenantId || req.headers['x-tenant'] as string;
      if (!tenant) {
        return res.status(400).json({
          error_code: 'MISSING_TENANT',
          message: 'Tenant ID is required',
        });
      }

      // 쿼리 파라미터 파싱
      const statusParam = req.query.status as string | undefined;
      const limitParam = req.query.limit ? parseInt(req.query.limit as string, 10) : undefined;
      const offsetParam = req.query.offset ? parseInt(req.query.offset as string, 10) : undefined;

      // status 유효성 검사
      let status: CsTicketStatus | undefined;
      if (statusParam) {
        if (statusParam !== 'open' && statusParam !== 'pending' && statusParam !== 'closed') {
          return res.status(400).json({
            error_code: 'INVALID_STATUS',
            message: 'status must be one of: open, pending, closed',
          });
        }
        status = statusParam as CsTicketStatus;
      }

      // limit/offset 유효성 검사
      const limit = limitParam !== undefined ? limitParam : 20;
      const offset = offsetParam !== undefined ? offsetParam : 0;

      if (limit < 1 || limit > 100) {
        return res.status(400).json({
          error_code: 'INVALID_LIMIT',
          message: 'limit must be between 1 and 100',
        });
      }

      if (offset < 0) {
        return res.status(400).json({
          error_code: 'INVALID_OFFSET',
          message: 'offset must be non-negative',
        });
      }

      // service-core-cs의 listTickets 호출
      const tickets = await listTickets({
        tenant,
        status,
        limit,
        offset,
      });

      // 응답 형식: { items: CsTicket[] }
      // createdAt은 ISO 문자열로 변환
      res.json({
        items: tickets.map((ticket: any) => ({
          id: ticket.id,
          tenant: ticket.tenant,
          subject: ticket.subject,
          status: ticket.status,
          createdAt: ticket.createdAt instanceof Date 
            ? ticket.createdAt.toISOString() 
            : (typeof ticket.createdAt === 'string' 
              ? ticket.createdAt 
              : new Date(ticket.createdAt).toISOString()),
        })),
      });
    } catch (e: any) {
      console.error('[CS Tickets] Error:', e);
      console.error('[CS Tickets] Stack:', e?.stack);
      console.error('[CS Tickets] Error message:', e?.message);
      console.error('[CS Tickets] Error code:', e?.code);
      console.error('[CS Tickets] DATABASE_URL:', process.env.DATABASE_URL ? 'set' : 'not set');
      
      // DB 연결 에러인 경우 명확한 메시지
      if (e?.code === 'ECONNREFUSED' || e?.code === 'ENOTFOUND') {
        return res.status(503).json({
          error_code: 'DATABASE_UNAVAILABLE',
          message: 'Database connection failed',
        });
      }
      
      // SASL 인증 에러 (DATABASE_URL 파싱 문제)
      if (e?.message?.includes('client password must be a string') || e?.message?.includes('SASL')) {
        return res.status(500).json({
          error_code: 'DATABASE_CONFIG_ERROR',
          message: 'Database connection string configuration error. Please check DATABASE_URL format.',
        });
      }
      
      // 테이블이 없는 경우
      if (e?.code === '42P01' || e?.message?.includes('does not exist')) {
        return res.status(500).json({
          error_code: 'TABLE_NOT_FOUND',
          message: 'cs_tickets table does not exist. Please run migrations.',
        });
      }
      
      next(e);
    }
  }
);

export default router;

