const ABSOLUTE_USER_HOME_PATTERNS = [
  /(?:^|[^A-Za-z0-9._-])\/Users\/[^/\s"'<>]+/u,
  /(?:^|[^A-Za-z0-9._-])\/home\/(?!runner(?:\/|$))[^/\s"'<>]+/u,
];

export function containsPrivateHomePath(text) {
  return ABSOLUTE_USER_HOME_PATTERNS.some(pattern => pattern.test(text));
}
