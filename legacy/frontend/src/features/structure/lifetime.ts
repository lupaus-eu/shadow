// Graph element lifetimes use ISO YYYY-MM-DD dates, which compare correctly as strings.

export function nextOrgStateTargetDate(
  orgStates: ReadonlyArray<{ targetDate: string }>,
  targetDate: string
): string | null {
  let next: string | null = null;
  for (const orgState of orgStates) {
    if (orgState.targetDate > targetDate && (next === null || orgState.targetDate < next)) {
      next = orgState.targetDate;
    }
  }
  return next;
}

/**
 * Whether an element visible at `targetDate` is not visible in the next org state.
 * `nextTargetDate` is null when there is no later org state and undefined when the
 * org states are unknown; then only an element ending exactly on `targetDate` counts.
 */
export function endsInOrgState(
  deleteDate: string | null,
  targetDate: string,
  nextTargetDate: string | null | undefined
): boolean {
  if (deleteDate === null) return false;
  if (nextTargetDate === undefined) return deleteDate === targetDate;
  return nextTargetDate === null || deleteDate < nextTargetDate;
}
