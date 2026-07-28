const PINNED_ACTION_USE =
  /^\s*(?:-\s+)?uses:\s*(actions\/[A-Za-z0-9_.-]+)@([0-9a-f]{40})\b/gmu;

export function collectPinnedActions(workflowSource) {
  const observed = new Map();
  for (const match of workflowSource.matchAll(PINNED_ACTION_USE)) {
    const [, repository, commit] = match;
    const existing = observed.get(repository);
    if (existing && existing !== commit) {
      throw new Error('ACTION_PIN_AMBIGUOUS');
    }
    observed.set(repository, commit);
  }
  return observed;
}
