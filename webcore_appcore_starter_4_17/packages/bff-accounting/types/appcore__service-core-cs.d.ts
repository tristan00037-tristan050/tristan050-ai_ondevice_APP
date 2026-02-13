declare module "@appcore/service-core-cs" {
  // ESM-only stub (NodeNext compatible)
  export type CsTicketStatus = string;

  export interface CsTicket {
    id: string;
    status: CsTicketStatus;
    [k: string]: unknown;
  }

  export interface ListTicketsParams {
    tenant?: string;
    status?: CsTicketStatus;
    limit?: number;
    offset?: number;
    [k: string]: unknown;
  }

  export function listTickets(params?: ListTicketsParams): Promise<CsTicket[]>;
}
