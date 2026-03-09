'use strict';

// P23-P2-04: MERKLE_ARTIFACT_TREE_V1

import { typedDigest } from '../crypto/digest_v1';

export interface MerkleLeaf {
  artifact_id: string;
  artifact_digest_sha256: string;
}

export interface MerkleNode {
  left_digest: string;
  right_digest: string;
}

export interface MerkleTree {
  leaves: MerkleLeaf[];
  root_digest: string;
  tree_schema_version: 1;
}

/**
 * Hash a single Merkle leaf using typedDigest for domain separation.
 */
export function hashLeaf(leaf: MerkleLeaf): string {
  return typedDigest('merkle-leaf', 'v1', leaf);
}

/**
 * Hash two Merkle child digests into a parent node digest.
 */
export function hashNode(left_digest: string, right_digest: string): string {
  return typedDigest('merkle-node', 'v1', { left_digest, right_digest });
}

/**
 * Build a Merkle tree from an ordered list of leaves.
 * Odd number of leaves: last leaf is duplicated (standard padding).
 * Returns the root digest.
 *
 * @throws Error('MERKLE_EMPTY_LEAVES') if leaves array is empty.
 */
export function buildMerkleTree(leaves: MerkleLeaf[]): MerkleTree {
  if (leaves.length === 0) {
    throw new Error('MERKLE_EMPTY_LEAVES');
  }

  let currentLevel: string[] = leaves.map(hashLeaf);

  while (currentLevel.length > 1) {
    const nextLevel: string[] = [];
    for (let i = 0; i < currentLevel.length; i += 2) {
      const left = currentLevel[i];
      const right = i + 1 < currentLevel.length ? currentLevel[i + 1] : currentLevel[i]; // duplicate last if odd
      nextLevel.push(hashNode(left, right));
    }
    currentLevel = nextLevel;
  }

  return {
    leaves,
    root_digest: currentLevel[0],
    tree_schema_version: 1,
  };
}

/**
 * Get the root digest of a Merkle tree.
 */
export function getMerkleRoot(tree: MerkleTree): string {
  return tree.root_digest;
}

/**
 * Verify that a given leaf is present in the tree by recomputing the root.
 * Simple linear scan — for audit, not performance-critical path.
 */
export function verifyMerkleLeaf(tree: MerkleTree, leaf: MerkleLeaf): boolean {
  const leafDigest = hashLeaf(leaf);
  const leafFound = tree.leaves.some(
    l => l.artifact_id === leaf.artifact_id && l.artifact_digest_sha256 === leaf.artifact_digest_sha256
  );
  if (!leafFound) return false;

  // Recompute root from current leaves and compare
  const recomputed = buildMerkleTree(tree.leaves);
  return recomputed.root_digest === tree.root_digest;
}
