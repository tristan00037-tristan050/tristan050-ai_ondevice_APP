import { invoke } from '@tauri-apps/api/core';

export type AccountingPrivilegedAction =
  | 'ASSIGNMENT_CREATE'
  | 'RULE_FUTURE_CREATE'
  | 'RULE_DEACTIVATE'
  | 'RULE_APPLICATION_REVERT'
  | 'QUARANTINE_ROW_RECOMPILE'
  | 'CONFLICT_RESOLVE';

interface NativeResponse {
  status: number;
  content_type: string;
  body: string;
}

type NativeRouteSelector =
  | 'ACTION_NONCE_THIS_ONLY'
  | 'ACTION_NONCE_FUTURE'
  | 'ASSIGNMENT_MUTATION'
  | 'RULE_DEACTIVATE'
  | 'RULE_APPLICATION_REVERT'
  | 'QUARANTINE_ROW_RECOMPILE'
  | 'CONFLICT_RESOLVE';

interface NativeIntent {
  action: AccountingPrivilegedAction;
  route_selector: NativeRouteSelector;
  resource_id: string;
  parent_resource_id: string | null;
  body_json: string | null;
  idempotency_key: string | null;
  if_match_version: number | null;
}

function isNativeDesktop(): boolean {
  return typeof window !== 'undefined'
    && '__TAURI_INTERNALS__' in (window as unknown as Record<string, unknown>);
}

function typedBusinessHeaders(headers?: HeadersInit): Pick<NativeIntent, 'idempotency_key' | 'if_match_version'> {
  let idempotencyKey: string | null = null;
  let ifMatchVersion: number | null = null;
  new Headers(headers).forEach((value, key) => {
    const lowered = key.toLowerCase();
    if (lowered === 'authorization' || lowered === 'butler-user-authorization') {
      throw new Error('RENDERER_AUTHORIZATION_HEADER_FORBIDDEN');
    }
    if (lowered === 'content-type') {
      if (value.toLowerCase() !== 'application/json') throw new Error('BOX5_CONTENT_TYPE_INVALID');
      return;
    }
    if (lowered === 'idempotency-key') {
      if (!/^[A-Za-z0-9._:-]{8,128}$/.test(value)) throw new Error('BOX5_IDEMPOTENCY_KEY_INVALID');
      idempotencyKey = value;
      return;
    }
    if (lowered === 'if-match') {
      const matched = /^W\/"([1-9][0-9]*)"$/.exec(value);
      if (!matched) throw new Error('BOX5_IF_MATCH_INVALID');
      const parsed = Number(matched[1]);
      if (!Number.isSafeInteger(parsed)) throw new Error('BOX5_IF_MATCH_INVALID');
      ifMatchVersion = parsed;
      return;
    }
    throw new Error('BOX5_RENDERER_HEADER_FORBIDDEN');
  });
  return { idempotency_key: idempotencyKey, if_match_version: ifMatchVersion };
}

function compileNativeIntent(
  action: AccountingPrivilegedAction,
  resourceType: string,
  resourceId: string,
  path: string,
  init: RequestInit,
): NativeIntent {
  if (!/^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$/.test(resourceId)) throw new Error('BOX5_RESOURCE_ID_INVALID');
  if ((init.method ?? 'POST').toUpperCase() !== 'POST') throw new Error('BOX5_METHOD_INVALID');
  const encoded = encodeURIComponent(resourceId);
  let routeSelector: NativeRouteSelector;
  let parentResourceId: string | null = null;
  if (action === 'ASSIGNMENT_CREATE'
      && resourceType === 'ACCOUNTING_TRANSACTION'
      && path === `/v1/accounting/unaccounted/${encoded}/action-nonce?scope=THIS_ONLY`) {
    routeSelector = 'ACTION_NONCE_THIS_ONLY';
  } else if (action === 'RULE_FUTURE_CREATE'
      && resourceType === 'ACCOUNTING_TRANSACTION'
      && path === `/v1/accounting/unaccounted/${encoded}/action-nonce?scope=SAME_VENDOR_FUTURE`) {
    routeSelector = 'ACTION_NONCE_FUTURE';
  } else if ((action === 'ASSIGNMENT_CREATE' || action === 'RULE_FUTURE_CREATE')
      && resourceType === 'ACCOUNTING_TRANSACTION'
      && path === `/v1/accounting/unaccounted/${encoded}/assign`) {
    routeSelector = 'ASSIGNMENT_MUTATION';
  } else if (action === 'RULE_DEACTIVATE' && resourceType === 'LEARNED_RULE'
      && path === `/v1/accounting/learned-rules/${encoded}/deactivate`) {
    routeSelector = 'RULE_DEACTIVATE';
  } else if (action === 'RULE_APPLICATION_REVERT' && resourceType === 'ACCOUNTING_TRANSACTION'
      && path === `/v1/accounting/review/transactions/${encoded}/rule-application/revert`) {
    routeSelector = 'RULE_APPLICATION_REVERT';
  } else if (action === 'CONFLICT_RESOLVE' && resourceType === 'RULE_CONFLICT'
      && path === `/v1/accounting/rule-conflicts/${encoded}/resolve`) {
    routeSelector = 'CONFLICT_RESOLVE';
  } else if (action === 'QUARANTINE_ROW_RECOMPILE' && resourceType === 'QUARANTINED_ROW') {
    const matched = /^\/v1\/accounting\/review\/batches\/([A-Za-z0-9._-]{1,128})\/quarantine\/([A-Za-z0-9._-]{1,128})\/recompile$/.exec(path);
    if (!matched || matched[2] !== resourceId) throw new Error('BOX5_RESOURCE_BINDING_INVALID');
    routeSelector = 'QUARANTINE_ROW_RECOMPILE';
    parentResourceId = matched[1];
  } else {
    throw new Error('BOX5_RESOURCE_BINDING_INVALID');
  }
  const bodyJson = typeof init.body === 'string' ? init.body : null;
  if (bodyJson !== null && new TextEncoder().encode(bodyJson).length > 1_048_576) {
    throw new Error('BOX5_BODY_SIZE_INVALID');
  }
  return {
    action,
    route_selector: routeSelector,
    resource_id: resourceId,
    parent_resource_id: parentResourceId,
    body_json: bodyJson,
    ...typedBusinessHeaders(init.headers),
  };
}

/**
 * Product Desktop mutations cross one native command. The renderer passes only
 * a typed business intent; URL, method and all HTTP headers are recompiled by
 * Rust. No user assertion is ever returned to JavaScript. Until an approved
 * human authority is provisioned, the native command fails closed.
 */
export async function nativeAuthorizedAccountingRequest(
  action: AccountingPrivilegedAction,
  resourceType: string,
  resourceId: string,
  path: string,
  init: RequestInit,
): Promise<Response> {
  if (!isNativeDesktop()) {
    throw new Error('BOX5_NATIVE_AUTHORITY_REQUIRED');
  }
  const request = compileNativeIntent(action, resourceType, resourceId, path, init);
  const native = await invoke<NativeResponse>('box5_authorized_request', {
    request,
  });
  return new Response(native.body, {
    status: native.status,
    headers: { 'Content-Type': native.content_type },
  });
}
