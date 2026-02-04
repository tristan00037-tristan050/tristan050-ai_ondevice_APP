/**
 * 알림 시스템
 * 에러 알림, 성능 저하 알림, 용량 임계값 알림
 * 
 * @module utils/notifications
 */

interface NotificationConfig {
  slackWebhookUrl?: string;
  emailRecipients?: string[];
  pagerDutyIntegrationKey?: string;
}

interface Notification {
  level: 'info' | 'warning' | 'error' | 'critical';
  title: string;
  message: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

// 알림 설정 (환경 변수에서 읽기)
const config: NotificationConfig = {
  slackWebhookUrl: process.env.SLACK_WEBHOOK_URL,
  emailRecipients: process.env.EMAIL_RECIPIENTS?.split(','),
  pagerDutyIntegrationKey: process.env.PAGERDUTY_INTEGRATION_KEY,
};

/**
 * Slack 알림 전송
 */
async function sendSlackNotification(notification: Notification): Promise<void> {
  if (!config.slackWebhookUrl) {
    return;
  }

  const color = {
    info: '#36a64f',
    warning: '#ffa500',
    error: '#ff0000',
    critical: '#8b0000',
  }[notification.level];

  const payload = {
    attachments: [
      {
        color,
        title: notification.title,
        text: notification.message,
        fields: notification.metadata
          ? Object.entries(notification.metadata).map(([key, value]) => ({
              title: key,
              value: String(value),
              short: true,
            }))
          : [],
        footer: 'Collector Service',
        ts: Math.floor(notification.timestamp / 1000),
      },
    ],
  };

  try {
    const response = await fetch(config.slackWebhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error('Failed to send Slack notification:', response.statusText);
    }
  } catch (error) {
    console.error('Error sending Slack notification:', error);
  }
}

/**
 * PagerDuty 알림 전송
 */
async function sendPagerDutyNotification(notification: Notification): Promise<void> {
  if (!config.pagerDutyIntegrationKey || notification.level !== 'critical') {
    return;
  }

  const severity = {
    error: 'error',
    critical: 'critical',
  }[notification.level] || 'warning';

  const payload = {
    routing_key: config.pagerDutyIntegrationKey,
    event_action: 'trigger',
    payload: {
      summary: notification.title,
      source: 'collector-service',
      severity,
      custom_details: {
        message: notification.message,
        ...notification.metadata,
      },
    },
  };

  try {
    const response = await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error('Failed to send PagerDuty notification:', response.statusText);
    }
  } catch (error) {
    console.error('Error sending PagerDuty notification:', error);
  }
}

/**
 * 알림 전송
 */
export async function sendNotification(notification: Notification): Promise<void> {
  console.log(`[NOTIFICATION] ${notification.level.toUpperCase()}: ${notification.title} - ${notification.message}`);

  // Slack 알림
  await sendSlackNotification(notification);

  // PagerDuty 알림 (critical만)
  if (notification.level === 'critical') {
    await sendPagerDutyNotification(notification);
  }
}

/**
 * 에러 알림
 */
export async function notifyError(
  title: string,
  message: string,
  metadata?: Record<string, unknown>
): Promise<void> {
  await sendNotification({
    level: 'error',
    title,
    message,
    timestamp: Date.now(),
    metadata,
  });
}

/**
 * 성능 저하 알림
 */
export async function notifyPerformanceDegradation(
  metric: string,
  threshold: number,
  currentValue: number
): Promise<void> {
  await sendNotification({
    level: 'warning',
    title: 'Performance Degradation Detected',
    message: `${metric} exceeded threshold: ${currentValue} > ${threshold}`,
    timestamp: Date.now(),
    metadata: {
      metric,
      threshold,
      currentValue,
    },
  });
}

/**
 * 용량 임계값 알림
 */
export async function notifyCapacityThreshold(
  resource: string,
  usage: number,
  threshold: number
): Promise<void> {
  const level = usage >= threshold * 0.9 ? 'critical' : 'warning';
  await sendNotification({
    level,
    title: 'Capacity Threshold Alert',
    message: `${resource} usage: ${(usage * 100).toFixed(1)}% (threshold: ${(threshold * 100).toFixed(1)}%)`,
    timestamp: Date.now(),
    metadata: {
      resource,
      usage,
      threshold,
    },
  });
}

/**
 * 데이터베이스 연결 실패 알림
 */
export async function notifyDatabaseConnectionFailure(error: Error): Promise<void> {
  await sendNotification({
    level: 'critical',
    title: 'Database Connection Failure',
    message: `Failed to connect to database: ${error.message}`,
    timestamp: Date.now(),
    metadata: {
      error: error.message,
      stack: error.stack,
    },
  });
}

/**
 * Rate Limit 초과 알림
 */
export async function notifyRateLimitExceeded(
  tenantId: string,
  endpoint: string,
  limit: number
): Promise<void> {
  await sendNotification({
    level: 'warning',
    title: 'Rate Limit Exceeded',
    message: `Tenant ${tenantId} exceeded rate limit on ${endpoint}`,
    timestamp: Date.now(),
    metadata: {
      tenantId,
      endpoint,
      limit,
    },
  });
}

/**
 * 회계 Block 스파이크 알림
 * 서버사이드 dedup 키: tenant + accounting_block_spike + window
 */
export async function notifyAccountingBlockSpike(
  tenantId: string,
  threshold: number,
  currentRate: number,
  window: string = '24h'
): Promise<void> {
  await sendNotification({
    level: 'critical',
    title: 'Accounting Block Spike Detected',
    message: `Tenant ${tenantId} accounting block spike: ${currentRate} (threshold: ${threshold}) in ${window}`,
    timestamp: Date.now(),
    metadata: {
      tenantId,
      ruleId: 'accounting_block_spike',
      threshold,
      currentRate,
      window,
      dedupKey: `${tenantId}:accounting_block_spike:${window}`,
    },
  });
}

