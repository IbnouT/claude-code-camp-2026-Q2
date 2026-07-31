const lifecyclePort = "8792";

export function lifecycleApiUrl(
  path: string,
  servedOrigin = window.location.origin,
): string {
  const lifecycleOrigin = new URL(servedOrigin);
  lifecycleOrigin.port = lifecyclePort;
  return new URL(path, lifecycleOrigin).toString();
}
