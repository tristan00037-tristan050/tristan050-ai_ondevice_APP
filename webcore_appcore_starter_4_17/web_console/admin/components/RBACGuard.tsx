/**
 * RBAC Guard Component
 * Gracefully handles denied actions (RBAC enforced)
 */

import React, { ReactNode } from 'react';

interface RBACGuardProps {
  permission: string;
  fallback?: ReactNode;
  children: ReactNode;
}

interface RBACContextType {
  permissions: string[];
  hasPermission: (permission: string) => boolean;
}

const RBACContext = React.createContext<RBACContextType>({
  permissions: [],
  hasPermission: () => false,
});

export const RBACProvider: React.FC<{ permissions: string[]; children: ReactNode }> = ({
  permissions,
  children,
}) => {
  const hasPermission = (permission: string): boolean => {
    return permissions.includes(permission);
  };

  return (
    <RBACContext.Provider value={{ permissions, hasPermission }}>
      {children}
    </RBACContext.Provider>
  );
};

export const useRBAC = () => {
  return React.useContext(RBACContext);
};

/**
 * RBAC Guard Component
 * Shows children only if user has permission, otherwise shows fallback
 */
export const RBACGuard: React.FC<RBACGuardProps> = ({
  permission,
  fallback = null,
  children,
}) => {
  const { hasPermission } = useRBAC();

  if (!hasPermission(permission)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
};

/**
 * RBAC Button Component
 * Disables button if user doesn't have permission
 */
export const RBACButton: React.FC<{
  permission: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
}> = ({ permission, onClick, children, disabled, className }) => {
  const { hasPermission } = useRBAC();
  const hasAccess = hasPermission(permission);

  return (
    <button
      onClick={onClick}
      disabled={!hasAccess || disabled}
      className={className}
      title={!hasAccess ? 'Insufficient permissions' : undefined}
    >
      {children}
    </button>
  );
};

