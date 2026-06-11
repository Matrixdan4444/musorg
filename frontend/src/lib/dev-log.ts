export function devLog(enabled: boolean, message: string, payload?: unknown) {
  if (!enabled) {
    return;
  }

  if (payload === undefined) {
    console.info(`[DEV MODE] ${message}`);
    return;
  }

  console.info(`[DEV MODE] ${message}`, payload);
}
