declare module "@appcore/service-core-cs" {
  // ESM-only stub (NodeNext compatible)
  export type CsTicketStatus = string;

  export interface CsTicket {
    id: string;
    status: CsTicketStatus;
    [k: string]: unknown;
  }

  export interface ListTicketsParams {
    [k: string]: unknown;
  }

  export interface ListTicketsResult {
    tickets: CsTicket[];
    [k: string]: unknown;
  }

  export function listTickets(params?: ListTicketsParams): Promise<ListTicketsResult>;
}
