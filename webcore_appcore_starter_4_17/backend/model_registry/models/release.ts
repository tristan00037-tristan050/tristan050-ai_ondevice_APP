/**
 * Model Registry - Release Pointer Data Model
 * Points to the currently released artifact for a platform/runtime combination
 */

export interface ReleasePointer {
  id: string;
  model_id: string;
  tenant_id: string;
  platform: string;
  runtime: string;
  model_version_id: string;
  artifact_id: string;
  created_at: Date;
  updated_at?: Date;
  created_by: string;
}

