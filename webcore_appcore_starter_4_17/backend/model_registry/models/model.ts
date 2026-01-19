/**
 * Model Registry Data Models
 * Immutable released artifacts with signed delivery
 */

export interface Model {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'deprecated';
  created_at: Date;
  updated_at: Date;
  created_by: string;
  metadata?: Record<string, any>;
}

export interface ModelVersion {
  id: string;
  model_id: string;
  tenant_id: string;
  version: string; // Semantic version: e.g., "1.0.0"
  status: 'draft' | 'released' | 'deprecated';
  created_at: Date;
  updated_at: Date;
  created_by: string;
  metadata?: Record<string, any>;
}

export interface Artifact {
  id: string;
  model_version_id: string;
  tenant_id: string;
  platform: string; // e.g., "android", "ios", "linux", "windows"
  runtime: string; // e.g., "onnx", "tflite", "coreml"
  file_path: string; // Storage path
  file_size: number; // Bytes
  sha256: string; // SHA256 hash of artifact
  signature: string; // Ed25519 signature (base64)
  key_id: string; // Signing key identifier (for rotation)
  created_at: Date;
  created_by: string;
}

export interface ReleasePointer {
  id: string;
  model_id: string;
  tenant_id: string;
  platform: string;
  runtime: string;
  model_version_id: string; // Points to released version
  artifact_id: string; // Points to artifact
  created_at: Date;
  created_by: string;
  metadata?: Record<string, any>;
}

export interface CreateModelRequest {
  name: string;
  description?: string;
  metadata?: Record<string, any>;
}

export interface CreateModelVersionRequest {
  version: string;
  metadata?: Record<string, any>;
}

export interface DeliveryResponse {
  model_id: string;
  version: string;
  platform: string;
  runtime: string;
  download_url: string;
  sha256: string;
  signature: string;
  key_id: string;
  apply_failclosed?: boolean; // If true, client must not apply
  reason_code?: string; // If apply_failclosed=true, reason
}

