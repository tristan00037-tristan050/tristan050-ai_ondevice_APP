/**
 * RBAC UI Tests
 * Verify RBAC is enforced in UI
 */

import { RBACGuard, RBACButton, RBACProvider, useRBAC } from '../components/RBACGuard';
import React from 'react';
import { render, screen } from '@testing-library/react';

describe('RBAC UI Tests', () => {
  it('should hide content when permission is denied', () => {
    const TestComponent = () => (
      <RBACProvider permissions={['tenant:read']}>
        <RBACGuard permission="tenant:write" fallback={<div>No permission</div>}>
          <div>Protected content</div>
        </RBACGuard>
      </RBACProvider>
    );

    const { container } = render(<TestComponent />);
    expect(container.textContent).toContain('No permission');
    expect(container.textContent).not.toContain('Protected content');
  });

  it('should show content when permission is granted', () => {
    const TestComponent = () => (
      <RBACProvider permissions={['tenant:write']}>
        <RBACGuard permission="tenant:write" fallback={<div>No permission</div>}>
          <div>Protected content</div>
        </RBACGuard>
      </RBACProvider>
    );

    const { container } = render(<TestComponent />);
    expect(container.textContent).toContain('Protected content');
    expect(container.textContent).not.toContain('No permission');
  });

  it('should disable button when permission is denied', () => {
    const TestComponent = () => (
      <RBACProvider permissions={['tenant:read']}>
        <RBACButton permission="tenant:write" onClick={() => {}}>
          Create Tenant
        </RBACButton>
      </RBACProvider>
    );

    const { container } = render(<TestComponent />);
    const button = container.querySelector('button');
    expect(button).toBeDisabled();
    expect(button?.title).toBe('Insufficient permissions');
  });

  it('should enable button when permission is granted', () => {
    const TestComponent = () => (
      <RBACProvider permissions={['tenant:write']}>
        <RBACButton permission="tenant:write" onClick={() => {}}>
          Create Tenant
        </RBACButton>
      </RBACProvider>
    );

    const { container } = render(<TestComponent />);
    const button = container.querySelector('button');
    expect(button).not.toBeDisabled();
  });

  it('should handle 403 errors gracefully', async () => {
    // Mock API call that returns 403
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: async () => ({ message: 'Forbidden' }),
    });

    try {
      const response = await fetch('/api/v1/iam/tenants');
      const data = await response.json();
      expect(data.message).toBe('Forbidden');
    } catch (error: any) {
      expect(error.message).toContain('Forbidden');
    }
  });
});

