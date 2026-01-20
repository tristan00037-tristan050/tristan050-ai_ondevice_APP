/**
 * Model Registry - Artifact Data Model
 * Multi-tenant: scoped by model_version_id (which is scoped by model_id -> tenant_id)
 */

export interface Artifact {
  id: string;
  model_version_id: string;
  platform: string; // e.g., 'android', 'ios', 'linux', 'windows'
  runtime: string; // e.g., 'tflite', 'onnx', 'coreml'
  sha256: string;
  size_bytes: number;
  storage_ref: string; // Reference to storage location (e.g., S3 key, file path)
  status: 'uploading' | 'ready' | 'failed';
  created_at: Date;
  metadata?: Record<string, unknown>;
}

export interface CreateArtifactRequest {
  platform: string;
  runtime: string;
  sha256: string;
  size_bytes: number;
  storage_ref: string;
  metadata?: Record<string, unknown>;
}

